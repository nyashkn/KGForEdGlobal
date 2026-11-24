"""PDF table-cell line breaks: opt-in tolerant source-anchor matching."""

# Third Party Library
import pytest

# Package Library
from kgfeg.kgs.schemas import SFISourceAnchor
from kgfeg.kgs.sfi_source_anchors import SFISourceUnit, find_source_anchor_span

CELL = "– Compare two numbers less than or equal to 10 using comparison symbols"


def _unit(text: str = CELL) -> SFISourceUnit:
    """Build a table-cell source unit holding `text`."""

    return SFISourceUnit(
        language="en",
        source_locator={},
        source_order=(0, 0, 0, 0),
        source_text=text,
        source_unit_id="u1",
        source_unit_kind="table_body_cell",
    )


def _anchor(text: str, occurrence_index: int = 0) -> SFISourceAnchor:
    """Build an anchor on unit u1 for `text`."""

    return SFISourceAnchor.model_validate(
        {
            "occurrence_index": occurrence_index,
            "source_text": text,
            "source_unit_id": "u1",
        }
    )


@pytest.fixture(name="join_line_breaks")
def fixture_join_line_breaks(monkeypatch: pytest.MonkeyPatch) -> None:
    """Turn on the opt-in KGFEG_SFI_JOIN_LINE_BREAKS behaviour."""

    monkeypatch.setenv("KGFEG_SFI_JOIN_LINE_BREAKS", "1")


@pytest.mark.usefixtures("join_line_breaks")
def test_anchor_with_copied_line_breaks_resolves_to_source_span() -> None:
    """An anchor copied with line breaks still resolves to the source span."""

    start, end = find_source_anchor_span(
        anchor=_anchor("– Compare two\nnumbers less than\nor equal to 10"),
        source_unit=_unit(),
    )

    assert CELL[start:end] == "– Compare two numbers less than or equal to 10"


# From a public Rwanda P1-P3 syllabus table: the model re-wrapped the cell, so the
# anchor's line breaks fall in different places than the source's.
RWANDA_CELL = (
    "– Compare\n1/2, 1/4 and 1/8\nusing\ncomparison\nsymbols (<, >\nor =)\n\n"
    "– Apply fractions in daily life situations"
)
RWANDA_ANCHOR = "Compare\n1/2, 1/4 and 1/8\nusing\ncomparison\nsymbols (<, > or\n=)"


def test_rewrapped_anchor_misses_without_the_flag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Without the flag the recorded Rwanda anchor is rejected, as before."""

    monkeypatch.delenv("KGFEG_SFI_JOIN_LINE_BREAKS", raising=False)

    with pytest.raises(ValueError, match="does not have occurrence_index=0"):
        find_source_anchor_span(
            anchor=_anchor(RWANDA_ANCHOR), source_unit=_unit(RWANDA_CELL)
        )


@pytest.mark.usefixtures("join_line_breaks")
def test_rewrapped_anchor_resolves_to_the_source_lines() -> None:
    """With the flag the recorded anchor resolves to the source's own wrapping."""

    start, end = find_source_anchor_span(
        anchor=_anchor(RWANDA_ANCHOR), source_unit=_unit(RWANDA_CELL)
    )

    assert RWANDA_CELL[start:end] == (
        "Compare\n1/2, 1/4 and 1/8\nusing\ncomparison\nsymbols (<, >\nor =)"
    )


@pytest.mark.usefixtures("join_line_breaks")
def test_missing_space_is_not_a_line_break() -> None:
    """A dropped space ("1000Frw" for "1000 Frw") is outside this fallback."""

    with pytest.raises(ValueError):
        find_source_anchor_span(
            anchor=_anchor("Unit 8: Rwandan currency from 1Frw to 1000Frw."),
            source_unit=_unit("Unit 8: Rwandan currency from 1Frw to 1000 Frw."),
        )


@pytest.mark.usefixtures("join_line_breaks")
def test_anchor_that_is_not_in_source_still_fails() -> None:
    """Joining line breaks does not make an absent anchor match."""

    with pytest.raises(ValueError):
        find_source_anchor_span(anchor=_anchor("Compare three"), source_unit=_unit())


def test_flag_off_keeps_strict_anchors(monkeypatch: pytest.MonkeyPatch) -> None:
    """Without the flag, anchor matching behaves exactly as before."""

    monkeypatch.delenv("KGFEG_SFI_JOIN_LINE_BREAKS", raising=False)

    with pytest.raises(ValueError):
        find_source_anchor_span(
            anchor=_anchor("– Compare two\nnumbers less than"), source_unit=_unit()
        )
