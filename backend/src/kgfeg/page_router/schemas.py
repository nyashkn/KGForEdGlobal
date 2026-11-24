"""This module contains the schemas of the model-free page router."""

# Standard Library
from typing import Literal

# Third Party Library
from pydantic import Field

# Package Library
from kgfeg.schemas import BaseSchema

PageLabel = Literal[
    "standards_detail",
    "standards_summary",
    "front_matter",
    "assessment_rubric",
    "appendix",
    "other",
    "unknown",
]

# Labels whose pages are kept. `unknown` is kept on purpose: the router fails open.
INCLUDED_LABELS: frozenset[str] = frozenset(
    {"standards_detail", "standards_summary", "unknown"}
)


class RouterParams(BaseSchema):
    """Thresholds and weights of the page router.

    Defaults were tuned on three public curriculum PDFs: Rwanda, Nigeria and Ghana
    maths.
    """

    code_weight: float = Field(0.2, description="Score weight of standard codes.")
    header_weight: float = Field(0.2, description="Score weight of heading cues.")
    include_below: float = Field(
        0.15,
        description="Pages scoring from this value up (below `standards_at`) are 'unknown'.",
    )
    min_table_lines: int = Field(
        25, description="Line count at which table density reaches full weight."
    )
    padding: int = Field(
        1, ge=0, description="Pages added on each side of a kept page."
    )
    penalty: float = Field(
        0.3, description="Score removed for table-of-contents or front/back headings."
    )
    standards_at: float = Field(
        0.4, description="Pages scoring from this value up are standards pages."
    )
    table_frag_floor: float = Field(
        0.3, description="Share of short lines at which table density starts."
    )
    table_frag_span: float = Field(
        0.3, description="Extra share of short lines for full table density."
    )
    table_weight: float = Field(0.5, description="Score weight of table density.")


class RoutedPage(BaseSchema):
    """Routing result of one PDF page."""

    decision: Literal["include", "exclude"] = Field(
        description="Whether the page goes on to extraction."
    )
    label: PageLabel = Field(description="What the router thinks the page is.")
    page_index: int = Field(description="0-based PDF page index.")
    padded: bool = Field(
        False,
        description="True if the page is kept only as a neighbour of a kept page.",
    )
    score: float = Field(description="Standards score of the page itself (0 to 1).")
    signals: list[str] = Field(
        default_factory=list, description="The cues that produced the score and label."
    )


class PageRoute(BaseSchema):
    """Routing result of a whole PDF."""

    pages: list[RoutedPage] = Field(description="One entry per PDF page, in order.")
    page_count: int = Field(description="Number of pages in the PDF.")
    router: str = Field("heuristic-v1", description="Router name and version.")

    @property
    def included(self) -> list[int]:
        """0-based indexes of the pages to extract, in order.

        Returns
        -------
        list[int]
            Page indexes whose decision is `include`.
        """

        return [p.page_index for p in self.pages if p.decision == "include"]
