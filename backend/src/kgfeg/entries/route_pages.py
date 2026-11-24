"""This module contains the opt-in entry point that routes pages before step 1. It
decides, without any model, which PDF pages hold standards, and writes `route.json`.
It changes nothing unless it is run: the pipeline entries do not call it.

Invoke from the backend directory via:

python src/kgfeg/entries/route_pages.py ../examples/rwanda/config_math_curriculum_p1_p3.json

Add `--fill-config` to also write `start_page` / `end_page` into the config. The
pipeline reads one contiguous range, so the filled range spans the first to the last
routed page; `route.json` keeps the exact page list.
"""

# Standard Library
import sys

from pathlib import Path
from typing import Any

# Third Party Library
import typer

from loguru import logger

# Append the framework path. NB: This is required if this entry point is invoked from
# the command line. However, it is not necessary if it is imported from a pip install.
if __name__ == "__main__":
    PACKAGE_PATH = Path(__file__).resolve().parents[2]

    if PACKAGE_PATH not in sys.path:
        print(f"Appending '{PACKAGE_PATH}' to system path...")
        sys.path.append(str(PACKAGE_PATH))

# Package Library
from kgfeg.page_router.router import route_pages
from kgfeg.page_router.schemas import PageRoute
from kgfeg.schemas import RunConfig
from kgfeg.utils.general import open_json_type, write_to_json

# Instantiate typer apps for the command line interface.
cli = typer.Typer(no_args_is_help=True)


def fill_page_range(*, config: dict[str, Any], page_route: PageRoute) -> dict[str, Any]:
    """Write the routed page range into the extraction and verification configs.

    Parameters
    ----------
    config
        The raw run config.
    page_route
        The routing result.

    Returns
    -------
    dict[str, Any]
        A copy of the config with `start_page` (first routed page) and `end_page`
        (one past the last routed page) set in `page_ir_extraction` and
        `page_ir_verification`.

    Raises
    ------
    ValueError
        If the route keeps no page.
    """

    pages = page_route.included

    if not pages:
        raise ValueError("The route keeps no page; refusing to fill the config.")

    filled = {
        key: dict(value) if isinstance(value, dict) else value
        for key, value in config.items()
    }

    for section in ("page_ir_extraction", "page_ir_verification"):
        filled[section] = {
            **config[section],
            "end_page": pages[-1] + 1,
            "start_page": pages[0],
        }

    return filled


@cli.command()
def route(
    config_fp: Path = typer.Argument(
        ...,
        dir_okay=False,
        exists=True,
        file_okay=True,
        help="The file path to the global config file for the pipeline.",
        readable=True,
        resolve_path=True,
    ),
    fill_config: bool = typer.Option(
        False,
        "--fill-config",
        help=(
            "Rewrite the config file in place: set start_page and end_page (first to "
            "last routed page) in page_ir_extraction and page_ir_verification, "
            "replacing any range already there."
        ),
    ),
    out_fp: Path = typer.Option(
        None,
        "--out",
        dir_okay=False,
        help="Where to write route.json. Defaults to <output_dir>/route.json.",
    ),
) -> None:
    """Route the pages of the configured PDF and write `route.json`.

    Parameters
    ----------
    config_fp
        The file path to the global config file for the pipeline.
    fill_config
        Whether to write the routed page range into the config.
    out_fp
        Where to write route.json.
    """

    raw_config = open_json_type(config_fp)
    extraction = RunConfig.model_validate(raw_config).page_ir_extraction
    result = route_pages(extraction.pdf_fp)
    out_fp = out_fp or extraction.output_dir / "route.json"

    out_fp.parent.mkdir(parents=True, exist_ok=True)
    write_to_json(fp=out_fp, json_info=result)
    logger.info(
        f"Routed {len(result.included)} of {result.page_count} pages to {out_fp}."
    )

    if fill_config:
        write_to_json(
            fp=config_fp,
            json_info=fill_page_range(config=raw_config, page_route=result),
        )
        logger.info(f"Filled start_page/end_page in {config_fp}.")


if __name__ == "__main__":
    cli()
