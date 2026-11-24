"""This module is the model-free page router. It scores every page of a curriculum
PDF from its text layer, outline, and table of contents, and returns the list of
pages to extract. It never reads gold labels and never calls a model.

The router favours recall: a page with no text layer, or with a middling score, is
labelled `unknown` and kept, and every kept page pads its neighbours.
"""

# Standard Library
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

# Third Party Library
import pymupdf

# Package Library
from kgfeg.page_router.schemas import (
    INCLUDED_LABELS,
    PageLabel,
    PageRoute,
    RoutedPage,
    RouterParams,
)
from kgfeg.page_router.signals import (
    PageSignals,
    has_text_layer,
    is_toc_page,
    read_signals,
)
from kgfeg.page_router.toc import Entry, body_span, parse_toc_lines, resolve_offset

_BODY_BONUS = 0.15  # Score added to pages inside the span the contents page names.
_ANCHOR_REACH = 3  # A standards page counts as an anchor if another is this close.


@dataclass(frozen=True)
class PageInput:
    """What the router needs to know about one PDF page."""

    has_graphics: bool
    text: str


@dataclass(frozen=True)
class _Scored:
    """A page after scoring, before document-level decisions."""

    hard_exclude: bool
    label: PageLabel
    score: float
    signals: list[str]


def _score_page(
    *, in_body: bool, params: RouterParams, sig: PageSignals
) -> tuple[float, list[str]]:
    """Score how much a page looks like a standards page.

    Parameters
    ----------
    in_body
        Whether the contents page puts this page inside the curriculum body.
    params
        Router weights.
    sig
        Cues of the page.

    Returns
    -------
    tuple[float, list[str]]
        The score in [0, 1] and the cues that moved it.
    """

    density = max(
        0.0,
        min(
            1.0,
            (sig.short_line_share - params.table_frag_floor) / params.table_frag_span,
        ),
    ) * min(1.0, sig.lines / params.min_table_lines)
    parts = {
        "table": params.table_weight * density,
        "headers": params.header_weight * min(sig.headers, 2) / 2,
        "codes": params.code_weight * min(sig.codes, 2) / 2,
        "body": _BODY_BONUS if in_body else 0.0,
        "front_or_back_heading": (
            -params.penalty if sig.front_heading or sig.back_heading else 0.0
        ),
    }
    used = [f"{name}:{value:+.2f}" for name, value in parts.items() if value]

    return max(0.0, min(1.0, sum(parts.values()))), used


def _label(
    *, hard: bool, params: RouterParams, score: float, sig: PageSignals
) -> PageLabel:
    """Pick a page label from its score and cues.

    Parameters
    ----------
    hard
        Whether the page is clearly a contents page or a front/back heading page.
    params
        Router thresholds.
    score
        Score of the page.
    sig
        Cues of the page.

    Returns
    -------
    PageLabel
        The label, before document-level (position) decisions.
    """

    if is_toc_page(sig):
        return "front_matter"

    if score >= params.standards_at:
        return (
            "standards_summary"
            if sig.has_summary_cue and not sig.codes
            else "standards_detail"
        )

    if score >= params.include_below:
        return "unknown"

    if hard:
        return (
            "appendix" if sig.back_heading and not sig.front_heading else "front_matter"
        )

    return "assessment_rubric" if sig.has_assessment_cue else "other"


def _score_all(
    *,
    pages: list[PageInput],
    params: RouterParams,
    signals: list[PageSignals],
    span: Optional[tuple[int, int]],
) -> list[_Scored]:
    """Score and label every page on its own.

    A page with no text but some image or drawing is probably a scan: `unknown`, kept.
    A page with neither is blank: `other`.

    Parameters
    ----------
    pages
        Every page of the PDF.
    params
        Router weights and thresholds.
    signals
        Cues of every page.
    span
        Body span named by the contents page or outline, if any.

    Returns
    -------
    list[_Scored]
        One scored page per input page.
    """

    out = []

    for index, sig in enumerate(signals):
        if not has_text_layer(sig):
            blank = not pages[index].has_graphics
            out.append(
                _Scored(
                    False,
                    "other" if blank else "unknown",
                    0.0,
                    ["blank" if blank else "no_text_layer"],
                )
            )
            continue

        in_body = (
            span is not None and span[0] <= index and (span[1] < 0 or index < span[1])
        )
        score, used = _score_page(in_body=in_body, params=params, sig=sig)
        hard = is_toc_page(sig) or sig.front_heading or sig.back_heading
        label = _label(hard=hard, params=params, score=score, sig=sig)
        out.append(
            _Scored(hard and label in ("front_matter", "appendix"), label, score, used)
        )

    return out


def _anchor_span(scored: list[_Scored]) -> Optional[tuple[int, int]]:
    """Find the first and last page of the main run of standards pages.

    A standards page is an anchor only if another standards page lies within a few
    pages, so one stray page in the front or back matter cannot widen the span.

    Parameters
    ----------
    scored
        Every page, scored on its own.

    Returns
    -------
    Optional[tuple[int, int]]
        First and last anchor index, or None if there is no anchor.
    """

    marks = [i for i, s in enumerate(scored) if s.label.startswith("standards")]
    anchors = [i for i in marks if any(0 < abs(i - j) <= _ANCHOR_REACH for j in marks)]

    return (anchors[0], anchors[-1]) if anchors else None


def _apply_position(*, scored: list[_Scored], span: tuple[int, int]) -> list[_Scored]:
    """Name excluded pages outside the standards run as front or back matter.

    Only the label changes. A kept page (`unknown` included) stays kept wherever it
    lies, because dropping a page for its position alone could lose standards.

    Parameters
    ----------
    scored
        Every page, scored on its own.
    span
        First and last anchor index.

    Returns
    -------
    list[_Scored]
        The pages with their labels corrected by position.
    """

    out = []

    for index, page in enumerate(scored):
        outside = index < span[0] or index > span[1]

        if outside and page.label in ("other", "assessment_rubric"):
            label: PageLabel = "front_matter" if index < span[0] else "appendix"
            page = _Scored(
                page.hard_exclude, label, page.score, [*page.signals, "outside_run"]
            )

        out.append(page)

    return out


def _pad(*, padding: int, scored: list[_Scored]) -> list[RoutedPage]:
    """Keep the neighbours of every kept page, unless they are clearly not standards.

    Parameters
    ----------
    padding
        Pages added on each side of a kept page.
    scored
        Every page after document-level decisions.

    Returns
    -------
    list[RoutedPage]
        One routed page per input page.
    """

    kept = {i for i, s in enumerate(scored) if s.label in INCLUDED_LABELS}
    padded = {
        j
        for i in kept
        for j in range(max(0, i - padding), min(len(scored), i + padding + 1))
        if j not in kept and not scored[j].hard_exclude
    }

    return [
        RoutedPage(
            decision="include" if i in kept | padded else "exclude",
            label=s.label,
            page_index=i,
            padded=i in padded,
            score=round(s.score, 3),
            signals=[*s.signals, "padding"] if i in padded else s.signals,
        )
        for i, s in enumerate(scored)
    ]


def _toc_entries(
    *,
    outline: Optional[list[Entry]],
    pages: list[PageInput],
    signals: list[PageSignals],
) -> list[Entry]:
    """Get section entries from the PDF outline, else from the contents pages.

    Parameters
    ----------
    outline
        Title and 0-based page index of each PDF bookmark, if the PDF has any.
    pages
        Every page of the PDF.
    signals
        Cues of every page.

    Returns
    -------
    list[Entry]
        Title and 0-based page index of each section; empty if none were found.
    """

    if outline:
        return outline

    toc_pages = {i for i, sig in enumerate(signals) if is_toc_page(sig)}
    lines = parse_toc_lines([pages[i].text for i in sorted(toc_pages)])
    offset = resolve_offset(
        entries=lines, page_texts=[p.text for p in pages], skip=toc_pages
    )

    return [] if offset is None else [(title, n + offset) for title, n in lines]


def route_page_inputs(
    pages: list[PageInput],
    *,
    outline: Optional[list[Entry]] = None,
    params: Optional[RouterParams] = None,
) -> PageRoute:
    """Route pages given as text. This is the pure core of `route_pages`.

    If no page looks like a standards page, every page is `unknown` and kept: with
    no evidence, the router does not drop anything.

    Parameters
    ----------
    pages
        Text and graphics flag of every page, in order.
    outline
        Title and 0-based page index of each PDF bookmark, if any.
    params
        Router weights and thresholds. Defaults to the tuned values.

    Returns
    -------
    PageRoute
        One routed page per input page.
    """

    params = params or RouterParams()
    signals = [read_signals(p.text) for p in pages]
    entries = _toc_entries(outline=outline, pages=pages, signals=signals)
    scored = _score_all(
        pages=pages, params=params, signals=signals, span=body_span(entries)
    )
    span = _anchor_span(scored)

    if span is None:
        scored = [
            (
                s
                if s.hard_exclude
                else _Scored(False, "unknown", s.score, [*s.signals, "no_anchor"])
            )
            for s in scored
        ]
    else:
        scored = _apply_position(scored=scored, span=span)

    return PageRoute(
        pages=_pad(padding=params.padding, scored=scored), page_count=len(pages)
    )


def read_pdf(pdf_fp: Path | str) -> tuple[list[PageInput], list[Entry]]:
    """Read the text layer and the outline of a PDF.

    Parameters
    ----------
    pdf_fp
        Path to the PDF.

    Returns
    -------
    tuple[list[PageInput], list[Entry]]
        Every page as text plus graphics flag, and the bookmarks (title and 0-based
        page index; empty if the PDF has none).
    """

    with pymupdf.open(str(pdf_fp)) as doc:
        pages = [
            PageInput(
                has_graphics=bool(page.get_images() or page.get_drawings()),
                text=page.get_text(),
            )
            for page in doc
        ]
        outline = [(title, max(0, page - 1)) for _, title, page in doc.get_toc()]

    return pages, outline


def route_pages(
    pdf_fp: Path | str, *, params: Optional[RouterParams] = None
) -> PageRoute:
    """Route a curriculum PDF: decide which pages hold standards, without any model.

    Parameters
    ----------
    pdf_fp
        Path to the PDF.
    params
        Router weights and thresholds. Defaults to the tuned values.

    Returns
    -------
    PageRoute
        One routed page per PDF page; `PageRoute.included` lists the pages to extract.
    """

    pages, outline = read_pdf(pdf_fp)

    return route_page_inputs(pages, outline=outline, params=params)
