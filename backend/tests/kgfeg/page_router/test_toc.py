"""This is the main module for testing page_router/toc.py."""

# Package Library
from kgfeg.page_router import toc


def test_parse_toc_lines_reads_title_and_page() -> None:
    """Test that dot-leader lines give title and printed page number."""

    text = "FOREWORD......iii\n6. SYLLABUS UNITS ........ 17\nno leader here 5\n"

    assert toc.parse_toc_lines([text]) == [("6. SYLLABUS UNITS", 17)]


def test_resolve_offset_takes_the_majority_vote() -> None:
    """Test that printed numbers are mapped to PDF indexes by title matching."""

    texts = ["cover", "contents", "Introduction\nbody", "x", "Syllabus units\n", "y"]
    entries = [("Introduction", 1), ("Syllabus units", 3), ("Nowhere to be found", 9)]

    assert toc.resolve_offset(entries=entries, page_texts=texts, skip={1}) == 1


def test_resolve_offset_needs_two_agreeing_entries() -> None:
    """Test that a single match is not trusted."""

    texts = ["cover", "Introduction\nbody"]

    assert (
        toc.resolve_offset(entries=[("Introduction", 1)], page_texts=texts, skip=set())
        is None
    )


def test_body_span_runs_from_units_to_references() -> None:
    """Test that the body starts at the units entry and ends at the back matter."""

    entries = [
        ("Foreword", 2),
        ("Syllabus units", 10),
        ("Grade R", 11),
        ("References", 90),
    ]

    assert toc.body_span(entries) == (10, 90)


def test_body_span_without_back_matter_is_open_ended() -> None:
    """Test that a missing back-matter entry gives an end of -1."""

    assert toc.body_span([("Foreword", 2), ("Strand 1", 9)]) == (9, -1)


def test_body_span_none_without_a_body_entry() -> None:
    """Test that unrelated entries give no span."""

    assert toc.body_span([("Foreword", 2), ("Rationale", 5)]) is None
