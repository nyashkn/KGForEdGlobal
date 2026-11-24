"""This is the main module for testing page_router/signals.py."""

# Package Library
from kgfeg.page_router import signals
from tests.constants import PARAM


def _table_text(rows: int) -> str:
    """Build the text of a page whose table cells wrap into short lines.

    Parameters
    ----------
    rows
        Number of table rows.

    Returns
    -------
    str
        Page text with three short lines per row.
    """

    return "\n".join("Add and\nsubtract\nnumbers" for _ in range(rows))


def test_read_signals_counts_cues() -> None:
    """Test that headings, codes, and table density are read from page text."""

    text = (
        "Basic 4\nContent\nStandards\nB4.1.1.1 Count objects\nB4.1.1.2 Order them\n"
        "Learning outcomes\n" + _table_text(10)
    )

    sig = signals.read_signals(text)

    assert sig.codes == 2
    assert sig.headers == 2  # "Content Standards" wraps over two lines.
    assert sig.short_line_share > 0.8
    assert not signals.is_toc_page(sig)


def test_read_signals_ignores_two_part_numbers() -> None:
    """Test that decimals and section numbers are not read as standard codes."""

    assert signals.read_signals("Section 4.5 costs 0.25 each").codes == 0


@PARAM(
    ("text", "expected"),
    [
        ("", False),
        ("  \n ", False),
        ("Page 7", False),
        ("A page with a real sentence of text on it.", True),
    ],
)
def test_has_text_layer(text: str, expected: bool) -> None:
    """Test that near-empty text counts as no text layer.

    Parameters
    ----------
    text
        Page text.
    expected
        Expected result.
    """

    assert signals.has_text_layer(signals.read_signals(text)) is expected


def test_is_toc_page_needs_leaders() -> None:
    """Test that a table of contents is recognised by its dot-leader lines."""

    leaders = "\n".join(f"Unit {n} ........................ {n + 10}" for n in range(6))

    assert signals.is_toc_page(signals.read_signals(leaders))
    assert not signals.is_toc_page(signals.read_signals("Foreword\nDear educators"))


def test_front_heading_only_counts_near_the_top() -> None:
    """Test that a heading cue deep in the page is not a heading."""

    deep = "x " * 400 + "foreword"

    assert signals.read_signals("FOREWORD\nDear educators").front_heading
    assert not signals.read_signals(deep).front_heading
