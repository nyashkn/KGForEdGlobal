"""This module turns a table of contents (or the PDF outline) into the page span of
the curriculum body, so the router can tell front and back matter from standards.
"""

# Standard Library
import re

from collections import Counter
from typing import Optional

_TOC_LINE_RE = re.compile(
    r"^(?P<title>.{3,120}?)\s*(?:\.{4,}|…+)\s*(?P<page>\d{1,3})\s*$"
)
_BODY_TITLE_RE = re.compile(
    r"\bunits?\b|\bstrands?\b|learning outcomes|content standards|"
    r"\b(?:primary|grade|class|basic)\s*(?:\d|one|two|three|[rk]\b)",
    re.IGNORECASE,
)
_BACK_TITLE_RE = re.compile(
    r"references|bibliography|glossary|appendi|annex|panel|contributors|reviewers",
    re.IGNORECASE,
)
_HEADING_CHARS = 400
_MIN_TITLE_LETTERS = 6
_MIN_OFFSET_VOTES = 2

Entry = tuple[str, int]  # (title, 0-based PDF page index)


def _letters(text: str) -> str:
    """Lower-case a text and keep only its letters and digits.

    Parameters
    ----------
    text
        Any text.

    Returns
    -------
    str
        The text without case, spacing, or punctuation.
    """

    return re.sub(r"[^a-z0-9]", "", text.lower())


def parse_toc_lines(toc_texts: list[str]) -> list[tuple[str, int]]:
    """Read `title ..... page` lines from the text of table-of-contents pages.

    Parameters
    ----------
    toc_texts
        Text of each page recognised as a table of contents.

    Returns
    -------
    list[tuple[str, int]]
        Title and printed (arabic) page number of each entry, in reading order.
    """

    found = []

    for text in toc_texts:
        for line in text.splitlines():
            match = _TOC_LINE_RE.match(line.strip())

            if match:
                found.append((match["title"].strip(), int(match["page"])))

    return found


def resolve_offset(
    *, entries: list[tuple[str, int]], page_texts: list[str], skip: set[int]
) -> Optional[int]:
    """Find how far printed page numbers lie from PDF page indexes.

    An entry votes for `index - printed_number` when its title is among the first
    words of page `index`. The most common vote wins if at least two entries agree.

    Parameters
    ----------
    entries
        Title and printed page number of each table-of-contents entry.
    page_texts
        Text of every PDF page.
    skip
        Page indexes that must not vote (the table-of-contents pages themselves).

    Returns
    -------
    Optional[int]
        The offset, or None if no consistent offset was found.
    """

    tops = [_letters(text[:_HEADING_CHARS]) for text in page_texts]
    votes: Counter[int] = Counter()

    for title, number in entries:
        key = _letters(title)

        if len(key) < _MIN_TITLE_LETTERS:
            continue

        for index, top in enumerate(tops):
            if index not in skip and key in top:
                votes[index - number] += 1
                break

    if not votes:
        return None

    offset, count = votes.most_common(1)[0]

    return offset if count >= _MIN_OFFSET_VOTES else None


def body_span(entries: list[Entry]) -> Optional[tuple[int, int]]:
    """Find the page span of the curriculum body from section entries.

    The body starts at the first entry whose title names units, strands, outcomes, or
    a grade. It ends at the first later entry that names references, an appendix, a
    glossary, or the contributors.

    Parameters
    ----------
    entries
        Title and 0-based PDF page index of each section, in reading order.

    Returns
    -------
    Optional[tuple[int, int]]
        First page (inclusive) and end page (exclusive) of the body, or None if the
        entries name no body start. The end is `-1` if no back matter was found.
    """

    start = next(
        (page for title, page in entries if _BODY_TITLE_RE.search(title)), None
    )

    if start is None:
        return None

    end = next(
        (
            page
            for title, page in entries
            if page > start and _BACK_TITLE_RE.search(title)
        ),
        -1,
    )

    return start, end
