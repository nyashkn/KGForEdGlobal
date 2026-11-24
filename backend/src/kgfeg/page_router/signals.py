"""This module extracts the cheap, model-free cues of one PDF page: heading words,
standard codes, table density, and table-of-contents shape.
"""

# Standard Library
import re

from dataclasses import dataclass

# Table-of-contents lines end in a run of dots or ellipsis characters.
_LEADER_RE = re.compile(r"(?:\.{5,}|…{2,})")
# Codes with 3+ numeric parts (1.1.2, B4.1.1.1). Two-part numbers are decimals or
# section numbers and are ignored.
_CODE_RE = re.compile(r"\b[A-Z]{0,2}\d{1,2}(?:\.\d{1,2}){2,4}\b")
_HEADER_RE = re.compile(
    r"learning outcomes?|specific outcomes?|learning objectives?|performance "
    r"objectives?|key unit competence|content standards?|indicators? and exemplars|"
    r"performance indicators?|learning indicators?|skills objective|"
    r"knowledge and understanding|sub-?strand|requirements per term",
    re.IGNORECASE,
)
_SUMMARY_RE = re.compile(
    r"scope and sequence|overview of|key competences|summary of|at the end of",
    re.IGNORECASE,
)
_ASSESS_RE = re.compile(
    r"assessment criteria|suggestions for (?:informal )?assessment|rubric|"
    r"teaching/ ?learning aids|links to other subjects",
    re.IGNORECASE,
)
_FRONT_RE = re.compile(
    r"table of contents|foreword|acknowledg|preface|abbreviations|"
    r"copyright|all rights reserved|list of tables",
    re.IGNORECASE,
)
_BACK_RE = re.compile(
    r"references|bibliography|glossary|appendix|appendices|annex|panel members|"
    r"list of contributors|reviewers",
    re.IGNORECASE,
)
_HEADING_CHARS = 400  # Heading cues only count near the top of a page.
_MIN_TEXT_CHARS = 20  # Fewer characters than this means "no text layer".
_SHORT_LINE_WORDS = 3  # Table cells wrap into lines of at most this many words.


@dataclass(frozen=True)
class PageSignals:
    """Cues read from one page. Counts, not scores: the router weighs them."""

    back_heading: bool
    chars: int
    codes: int
    front_heading: bool
    has_assessment_cue: bool
    has_summary_cue: bool
    headers: int
    lines: int
    short_line_share: float
    toc_leaders: int


def read_signals(text: str) -> PageSignals:
    """Count the router's cues in the text of one page.

    Parameters
    ----------
    text
        Text layer of the page.

    Returns
    -------
    PageSignals
        The cues found on the page.
    """

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    flat = " ".join(text.split())  # Cells wrap, so a heading can span two lines.
    short = sum(1 for line in lines if len(line.split()) <= _SHORT_LINE_WORDS)
    top = flat[:_HEADING_CHARS]

    return PageSignals(
        back_heading=bool(_BACK_RE.search(top)),
        chars=len(text.strip()),
        codes=len(set(_CODE_RE.findall(flat))),
        front_heading=bool(_FRONT_RE.search(top)),
        has_assessment_cue=bool(_ASSESS_RE.search(flat)),
        has_summary_cue=bool(_SUMMARY_RE.search(top)),
        headers=len(_HEADER_RE.findall(flat)),
        lines=len(lines),
        short_line_share=short / len(lines) if lines else 0.0,
        toc_leaders=sum(1 for line in lines if _LEADER_RE.search(line)),
    )


def has_text_layer(signals: PageSignals) -> bool:
    """Tell whether a page has a usable text layer.

    Parameters
    ----------
    signals
        Cues of the page.

    Returns
    -------
    bool
        False for a page with (almost) no text, e.g. a scan.
    """

    return signals.chars >= _MIN_TEXT_CHARS


def is_toc_page(signals: PageSignals) -> bool:
    """Tell whether a page looks like a table of contents.

    Parameters
    ----------
    signals
        Cues of the page.

    Returns
    -------
    bool
        True if the page has many dot-leader lines, or a contents heading and a few.
    """

    return signals.toc_leaders >= 5 or (
        signals.front_heading and signals.toc_leaders >= 2
    )
