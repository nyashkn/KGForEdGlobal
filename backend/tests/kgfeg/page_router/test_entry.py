"""This is the main module for testing entries/route_pages.py."""

# Standard Library
import json

from pathlib import Path
from typing import Any

# Third Party Library
import pymupdf
import pytest

from typer.testing import CliRunner

# Package Library
from kgfeg.entries import route_pages as entry
from kgfeg.page_router.schemas import PageRoute, RoutedPage

EXAMPLE_CONFIG = (
    Path(__file__).resolve().parents[4]
    / "examples"
    / "rwanda"
    / "config_math_curriculum_p1_p3.json"
)
TABLE = "Strand 1\nCONTENT STANDARDS\n" + "\n".join(
    "Add and\nsubtract\nnumbers" for _ in range(12)
)


def _route(kept: list[int], count: int = 10) -> PageRoute:
    """Build a route that keeps the given pages.

    Parameters
    ----------
    kept
        Indexes of the kept pages.
    count
        Page count.

    Returns
    -------
    PageRoute
        The route.
    """

    return PageRoute(
        page_count=count,
        pages=[
            RoutedPage(
                decision="include" if i in kept else "exclude",
                label="unknown",
                page_index=i,
                score=0.0,
            )
            for i in range(count)
        ],
    )


def test_fill_page_range_spans_first_to_last_and_keeps_the_rest() -> None:
    """Test that both configs get start_page and end_page, and nothing else changes."""

    config: dict[str, Any] = {
        "page_ir_extraction": {"start_page": 0, "end_page": None, "dpi": 250},
        "page_ir_verification": {"start_page": 0, "end_page": None},
        "kgs": {"overwrite": False},
    }

    filled = entry.fill_page_range(config=config, page_route=_route([3, 4, 7]))

    assert filled["page_ir_extraction"] == {"start_page": 3, "end_page": 8, "dpi": 250}
    assert filled["page_ir_verification"] == {"start_page": 3, "end_page": 8}
    assert filled["kgs"] == {"overwrite": False}
    assert config["page_ir_extraction"]["start_page"] == 0  # input is not mutated


def test_fill_page_range_refuses_an_empty_route() -> None:
    """Test that an empty route does not turn into a config."""

    with pytest.raises(ValueError, match="keeps no page"):
        entry.fill_page_range(config={}, page_route=_route([]))


def test_cli_writes_route_json_and_fills_config_only_when_asked(
    tmp_path: Path,
) -> None:
    """Test the command line entry end to end on a generated PDF.

    Parameters
    ----------
    tmp_path
        The pytest temporary directory path fixture.
    """

    pdf_fp = tmp_path / "doc.pdf"
    doc = pymupdf.open()

    for text in ["Some prose " * 30, TABLE, TABLE, TABLE, "More prose " * 30]:
        doc.new_page().insert_textbox(pymupdf.Rect(20, 20, 580, 820), text, fontsize=6)

    doc.save(str(pdf_fp))
    doc.close()

    config = json.loads(EXAMPLE_CONFIG.read_text(encoding="utf-8"))
    config["page_ir_extraction"]["pdf_fp"] = str(pdf_fp)
    config["page_ir_extraction"]["output_dir"] = str(tmp_path / "out")
    config_fp = tmp_path / "config.json"
    config_fp.write_text(json.dumps(config), encoding="utf-8")
    runner = CliRunner()

    result = runner.invoke(entry.cli, [str(config_fp)])

    assert result.exit_code == 0, result.output
    route = json.loads((tmp_path / "out" / "route.json").read_text(encoding="utf-8"))
    assert route["page_count"] == 5
    assert json.loads(config_fp.read_text(encoding="utf-8")) == config  # untouched

    result = runner.invoke(entry.cli, [str(config_fp), "--fill-config"])

    filled = json.loads(config_fp.read_text(encoding="utf-8"))
    assert result.exit_code == 0, result.output
    assert filled["page_ir_extraction"]["start_page"] <= 1
    assert filled["page_ir_extraction"]["end_page"] >= 4
