"""This is the main module for testing page_router/router.py."""

# Standard Library
from pathlib import Path

# Third Party Library
import pymupdf

# Package Library
from kgfeg.page_router import router
from kgfeg.page_router.schemas import RouterParams
from tests.constants import PARAM

PROSE = "This page explains how teachers should plan lessons and share results. " * 5
TABLE = (
    "Basic 4\nStrand 1\nSub-strand 1\nCONTENT STANDARDS\nB4.1.1.1\nCount\nobjects\n"
    + "\n".join("Add and\nsubtract\nnumbers" for _ in range(12))
)
TOC = "\n".join(f"Section {n} .................... {n}" for n in range(8))


def _page(text: str, *, graphics: bool = False) -> router.PageInput:
    """Build a router input page.

    Parameters
    ----------
    text
        Page text.
    graphics
        Whether the page has an image or drawing.

    Returns
    -------
    router.PageInput
        The page.
    """

    return router.PageInput(has_graphics=graphics, text=text)


def _route(texts: list[str], **kwargs: object) -> dict[int, tuple[str, str]]:
    """Route pages and summarise the result.

    Parameters
    ----------
    texts
        Page texts.
    **kwargs
        Passed on to `route_page_inputs`.

    Returns
    -------
    dict[int, tuple[str, str]]
        Page index to (decision, label).
    """

    result = router.route_page_inputs([_page(t) for t in texts], **kwargs)  # type: ignore[arg-type]

    return {p.page_index: (p.decision, p.label) for p in result.pages}


def test_table_run_is_kept_and_front_and_back_matter_dropped() -> None:
    """Test that a run of table pages is kept and far-away prose pages are not."""

    texts = [TOC, *[PROSE] * 4, *[TABLE] * 6, *[PROSE] * 4, "References\n" + PROSE]

    result = _route(texts)

    assert result[0] == ("exclude", "front_matter")
    assert {i for i, (d, _) in result.items() if d == "include"} == set(range(4, 12))
    assert result[6] == ("include", "standards_detail")
    assert result[15][0] == "exclude"


def test_padding_adds_one_page_each_side_but_not_into_front_matter() -> None:
    """Test that a kept page pads its neighbours, except contents pages."""

    result = router.route_page_inputs(
        [
            _page(t)
            for t in [PROSE, TOC, PROSE, TABLE, TABLE, TABLE, TABLE, PROSE, PROSE]
        ]
    )

    pages = {p.page_index: p for p in result.pages}

    assert result.included == [2, 3, 4, 5, 6, 7]
    assert pages[2].padded and pages[7].padded
    assert pages[1].decision == "exclude"  # a contents page is never padded in


def test_zero_padding_keeps_only_scored_pages() -> None:
    """Test that padding can be switched off."""

    texts = [PROSE, TABLE, TABLE, TABLE, TABLE, PROSE]

    result = router.route_page_inputs(
        [_page(t) for t in texts], params=RouterParams(padding=0)
    )

    assert result.included == [1, 2, 3, 4]


def test_page_without_text_layer_fails_open() -> None:
    """Test that a scanned page (image, no text) is `unknown` and kept."""

    pages = [_page(t) for t in [TABLE, TABLE, TABLE, TABLE, PROSE, PROSE, PROSE, PROSE]]
    pages[5] = _page("", graphics=True)
    pages[7] = _page("", graphics=False)

    result = router.route_page_inputs(pages)
    labels = {p.page_index: (p.decision, p.label) for p in result.pages}

    assert labels[5] == ("include", "unknown")
    assert labels[7][0] == "exclude"  # blank: no text and nothing drawn


def test_no_standards_anywhere_keeps_every_page() -> None:
    """Test that without any evidence the router drops nothing."""

    result = router.route_page_inputs([_page(PROSE), _page(PROSE), _page(PROSE)])

    assert result.included == [0, 1, 2]
    assert {p.label for p in result.pages} == {"unknown"}


def test_summary_page_is_labelled_apart_from_detail() -> None:
    """Test that a scope-and-sequence table is `standards_summary` and still kept."""

    summary = "SCOPE AND SEQUENCE\n" + TABLE.replace("B4.1.1.1", "")
    texts = [PROSE, summary, TABLE, TABLE, TABLE, PROSE]

    result = _route(texts)

    assert result[1] == ("include", "standards_summary")
    assert result[2] == ("include", "standards_detail")


def test_outline_span_lifts_pages_inside_the_body() -> None:
    """Test that bookmarks add a body prior: a weak page inside the body is kept."""

    weak = "Learning outcomes\n" + "\n".join(["Add and\nsubtract"] * 6)
    texts = [PROSE, TABLE, TABLE, weak, TABLE, TABLE, PROSE, PROSE, PROSE, PROSE]
    params = RouterParams(padding=0, include_below=0.4)

    without = router.route_page_inputs([_page(t) for t in texts], params=params)
    outline = [("Units", 1), ("References", 6)]
    with_outline = router.route_page_inputs(
        [_page(t) for t in texts], outline=outline, params=params
    )

    assert 3 not in without.included
    assert 3 in with_outline.included


def test_route_scores_are_in_range_and_explain_themselves() -> None:
    """Test that every page reports a score in [0, 1] and its signals."""

    result = router.route_page_inputs([_page(t) for t in [PROSE, TABLE, TABLE, TABLE]])

    assert all(0.0 <= p.score <= 1.0 for p in result.pages)
    assert any(s.startswith("table:") for s in result.pages[1].signals)
    assert result.page_count == 4


def test_route_pages_reads_a_real_pdf(tmp_path: Path) -> None:
    """Test the PDF entry point on a generated PDF with bookmarks and a blank page.

    Parameters
    ----------
    tmp_path
        The pytest temporary directory path fixture.
    """

    fp = tmp_path / "doc.pdf"
    doc = pymupdf.open()

    for text in [PROSE, TABLE, TABLE, TABLE, TABLE, PROSE, ""]:
        page = doc.new_page()
        if text:
            page.insert_textbox(pymupdf.Rect(20, 20, 580, 820), text, fontsize=6)

    doc.set_toc([[1, "Units", 2], [1, "References", 6]])
    doc.save(str(fp))
    doc.close()

    pages, outline = router.read_pdf(fp)
    result = router.route_pages(fp)

    assert outline == [("Units", 1), ("References", 5)]
    assert [p.has_graphics for p in pages][-1] is False
    assert result.page_count == 7
    assert {1, 2, 3, 4} <= set(result.included)
    assert 6 not in result.included


@PARAM("padding", [0, 1, 2])
def test_included_never_loses_a_scored_page(padding: int) -> None:
    """Test that more padding only ever adds pages.

    Parameters
    ----------
    padding
        Pages added on each side.
    """

    texts = [PROSE, TABLE, TABLE, TABLE, PROSE, PROSE, PROSE]
    base = router.route_page_inputs(
        [_page(t) for t in texts], params=RouterParams(padding=0)
    ).included
    padded = router.route_page_inputs(
        [_page(t) for t in texts], params=RouterParams(padding=padding)
    ).included

    assert set(base) <= set(padded)
