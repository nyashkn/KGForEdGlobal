"""SFI dedup: groups that resolve to one final identity key end in one merge group."""

# Standard Library
import json

from pathlib import Path
from types import SimpleNamespace
from typing import Any

# Third Party Library
import pytest

# Package Library
from kgfeg.document_ir.schemas import BlockSegment, TableSegment
from kgfeg.kgs.schemas import (
    SFIDedupDecisionGroup,
    SFIDedupReviewResponse,
    SFIMergeReport,
    SFIRegistryArtifact,
    SFIRegistryCandidate,
)
from kgfeg.kgs.sfi_dedup import (
    _build_current_merge_groups,
    _build_merge_report,
    _validate_complete_merge_artifacts,
    _write_merge_artifacts,
)
from kgfeg.kgs.sfi_finalization import uncoded_identity_keys
from kgfeg.schemas import CreateKGConfig
from tests.constants import PACKAGE_PATH

_HEADING_ID = "w0000:cand-1:aaaa"
_CELL_ID = "w0002:cand-1:bbbb"
_OTHER_ID = "w0002:cand-2:cccc"


def _config(
    example: str = "nigeria/config_math_curriculum_1_3.json",
) -> CreateKGConfig:
    """Load a shipped example profile (default: Nigeria, Theme is controlled)."""

    payload = json.loads((PACKAGE_PATH / "examples" / example).read_text())
    return CreateKGConfig.model_validate(payload["kgs"])


def _candidate(
    *,
    candidate_id: str,
    segment_id: str,
    source_text: str,
    value: str,
    window: int,
    statement_type: str = "Theme",
    scope: dict[str, str] | None = None,
) -> SFIRegistryCandidate:
    """Build an uncoded registry candidate with one description anchor."""

    anchor = {"occurrence_index": 0, "source_text": source_text, "source_unit_id": "u"}
    payload: dict[str, Any] = {
        "candidate_id": candidate_id.split(":")[1],
        "code_scope_values": {},
        "code_source_anchors": [],
        "confidence": 0.99,
        "description": source_text,
        "description_source_anchors": [anchor],
        "identity_scope_values": scope or {},
        "language": "en",
        "normalized_statement_type": "Standard Grouping",
        "source_text": source_text,
        "statement_code": None,
        "statement_type": statement_type,
        "table_header_indexes": [],
        "table_row_indexes": [],
    }
    normalized = source_text.lower()
    return SFIRegistryCandidate.model_validate(
        {
            **{k: v for k, v in payload.items() if k != "candidate_id"},
            "applicable_code_type": None,
            "candidate_payload": payload,
            "canonical_statement_value": value,
            "canonical_statement_value_key": value.lower(),
            "code_bucket_key": None,
            "code_scope_key": None,
            "identity_scope_key": "|".join(
                f"{k.lower()}={v.lower()}" for k, v in (scope or {}).items()
            )
            or None,
            "normalized_description": normalized,
            "normalized_source_text": normalized,
            "normalized_statement_code": None,
            "registry_candidate_id": candidate_id,
            "resolved_code_type": None,
            "source_context_key": f"ctx-{segment_id}",
            "source_context_labels": [f"label {segment_id}"],
            "source_occurrence_location_key": f"loc-{candidate_id}",
            "source_segment_ids": [segment_id],
            "source_text_bucket_key": f"theme|{segment_id}|{normalized}",
            "source_window_candidate_id": payload["candidate_id"],
            "source_window_candidate_index": 0,
            "text_bucket_key": f"theme|{segment_id}|{normalized}",
            "window_id": f"window-{window}",
            "window_index": window,
        }
    )


def _merge(
    candidates: list[SFIRegistryCandidate],
    decision: str,
    config: CreateKGConfig | None = None,
) -> list[Any]:
    """Run the merge step on one review set with the given checker decision."""

    config = config or _config()
    document_ir = SimpleNamespace(
        doc_key="doc",
        segments=[
            BlockSegment.model_construct(segment_id="seg-heading", section_path=[]),
            TableSegment.model_construct(segment_id="seg-table", section_path=[]),
        ],
    )
    registry = SFIRegistryArtifact.model_construct(candidates=candidates)
    by_id = {c.registry_candidate_id: c for c in candidates}
    response = SFIDedupReviewResponse(
        decision_groups=[
            SFIDedupDecisionGroup(
                candidate_ids=list(by_id),
                confidence=0.9,
                decision=decision,
                reason="Visible text differs after normalisation.",
            )
        ],
        review_set_id="dedupe_review_test",
    )
    groups, _ = _build_current_merge_groups(
        document_ir=document_ir,
        kg_config=config,
        review_responses=[response],
        sfi_candidate_registry=registry,
        sfi_candidates_by_id=by_id,
        unresolved_components=[],
    )
    keys = uncoded_identity_keys(
        document_ir=document_ir,
        kg_config=config,
        merge_groups=groups,
        sfi_candidates_by_id=by_id,
    )
    assert len(set(keys.values())) == len(keys), "final identity keys must be unique"
    return groups


def test_heading_and_cell_with_one_canonical_value_merge() -> None:
    """keep_separate from the checker cannot leave two groups with one identity."""

    groups = _merge(
        [
            _candidate(
                candidate_id=_HEADING_ID,
                segment_id="seg-heading",
                source_text="THEME: NUMBER AND NUMERATION",
                value="NUMBER AND NUMERATION",
                window=0,
            ),
            _candidate(
                candidate_id=_CELL_ID,
                segment_id="seg-table",
                source_text="NUMBER AND NUMERATION",
                value="NUMBER AND NUMERATION",
                window=2,
            ),
        ],
        "keep_separate",
    )

    assert len(groups) == 1
    (group,) = groups
    assert group.merge_decision == "merged"
    assert group.registry_candidate_ids == [_HEADING_ID, _CELL_ID]
    assert group.representative_candidate_id == _HEADING_ID
    assert group.audit_flags == ["identity_key_forced_merge"]
    assert "keep_separate" in group.merge_reason
    assert [ref["source_segment_ids"] for ref in group.candidate_source_refs] == [
        ["seg-heading"],
        ["seg-table"],
    ]


def test_rwanda_topic_area_repeats_with_line_break_merge() -> None:
    """Rwanda P1 maths: a Topic Area heading repeated with and without a line break.

    Both texts come from the REB P1-P3 syllabus table; when the checker keeps them
    apart they would otherwise mint the same final SFI.
    """

    scope = {"Grade": "P1"}
    groups = _merge(
        [
            _candidate(
                candidate_id=_HEADING_ID,
                segment_id="seg-heading",
                source_text="TOPIC AREA: NUMBERS AND\nOPERATIONS",
                value="Numbers and Operations",
                window=6,
                statement_type="Topic Area",
                scope=scope,
            ),
            _candidate(
                candidate_id=_CELL_ID,
                segment_id="seg-table",
                source_text="TOPIC AREA: NUMBERS AND OPERATIONS",
                value="Numbers and Operations",
                window=9,
                statement_type="Topic Area",
                scope=scope,
            ),
        ],
        "keep_separate",
        config=_config("rwanda/config_math_curriculum_p1_p3.json"),
    )

    assert [group.registry_candidate_ids for group in groups] == [
        [_HEADING_ID, _CELL_ID]
    ]
    assert groups[0].audit_flags == ["identity_key_forced_merge"]


def test_resume_accepts_report_with_forced_merge_group(tmp_path: Path) -> None:
    """A saved merge report holding a forced-merge group passes the resume check."""

    candidates = [
        _candidate(
            candidate_id=_HEADING_ID,
            segment_id="seg-heading",
            source_text="THEME: NUMBER AND NUMERATION",
            value="NUMBER AND NUMERATION",
            window=0,
        ),
        _candidate(
            candidate_id=_CELL_ID,
            segment_id="seg-table",
            source_text="NUMBER AND NUMERATION",
            value="NUMBER AND NUMERATION",
            window=2,
        ),
    ]
    document_ir = SimpleNamespace(
        doc_key="doc",
        segments=[
            BlockSegment.model_construct(segment_id="seg-heading", section_path=[]),
            TableSegment.model_construct(segment_id="seg-table", section_path=[]),
        ],
    )
    config = _config()
    registry = SFIRegistryArtifact.model_construct(candidates=candidates)
    by_id = {c.registry_candidate_id: c for c in candidates}
    groups, unreviewed = _build_current_merge_groups(
        document_ir=document_ir,
        kg_config=config,
        review_responses=[],
        sfi_candidate_registry=registry,
        sfi_candidates_by_id=by_id,
        unresolved_components=[],
    )
    report = _build_merge_report(
        merge_groups=groups,
        review_requests=[],
        review_responses=[],
        sfi_candidate_registry=registry,
        unreviewed_singleton_count=unreviewed,
    )
    paths = {
        name: tmp_path / f"{name}.json"
        for name in ("conflicts", "groups", "report", "needs_review")
    }
    _write_merge_artifacts(
        conflicts_fp=paths["conflicts"],
        merge_groups_fp=paths["groups"],
        merge_report=report,
        merge_report_fp=paths["report"],
        needs_review_fp=paths["needs_review"],
    )
    requests_fp = tmp_path / "requests.jsonl"
    responses_fp = tmp_path / "responses.jsonl"
    requests_fp.write_text("")
    responses_fp.write_text("")

    assert [g.audit_flags for g in report.merge_groups] == [
        ["identity_key_forced_merge"]
    ]
    _validate_complete_merge_artifacts(
        conflicts_fp=paths["conflicts"],
        document_ir=document_ir,
        kg_config=config,
        merge_groups_fp=paths["groups"],
        merge_report=SFIMergeReport.model_validate_json(paths["report"].read_text()),
        merge_report_fp=paths["report"],
        needs_review_fp=paths["needs_review"],
        planned_review_requests=[],
        review_requests_fp=requests_fp,
        review_responses_fp=responses_fp,
        sfi_candidate_registry=registry,
        sfi_candidates_by_id=by_id,
        unresolved_components=[],
    )


def test_distinct_items_stay_separate() -> None:
    """Different canonical values keep their own groups and no audit flag."""

    groups = _merge(
        [
            _candidate(
                candidate_id=_CELL_ID,
                segment_id="seg-table",
                source_text="NUMBER AND NUMERATION",
                value="NUMBER AND NUMERATION",
                window=2,
            ),
            _candidate(
                candidate_id=_OTHER_ID,
                segment_id="seg-table",
                source_text="GEOMETRY",
                value="GEOMETRY",
                window=2,
            ),
        ],
        "keep_separate",
    )

    assert [group.merge_decision for group in groups] == ["singleton", "singleton"]
    assert all(not group.audit_flags for group in groups)


def test_colliding_groups_with_mixed_types_fail_loudly() -> None:
    """A forced merge never picks a statement type the review did not select."""

    cell = _candidate(
        candidate_id=_CELL_ID,
        segment_id="seg-table",
        source_text="NUMBER AND NUMERATION",
        value="NUMBER AND NUMERATION",
        window=2,
    )
    other_type = cell.model_copy(
        update={"registry_candidate_id": _OTHER_ID, "statement_type": "Sub-Theme"}
    )
    config = _config()
    # identity without the type fields, so the two types collide on text alone
    config.academic_standards.synthetic_merge_key_fields = [
        "country",
        "normalized_text",
    ]

    with pytest.raises(ValueError, match="cannot be merged into one SFI"):
        _build_current_merge_groups(
            document_ir=SimpleNamespace(
                doc_key="doc",
                segments=[
                    TableSegment.model_construct(
                        segment_id="seg-table", section_path=[]
                    )
                ],
            ),
            kg_config=config,
            review_responses=[],
            sfi_candidate_registry=SFIRegistryArtifact.model_construct(
                candidates=[cell, other_type]
            ),
            sfi_candidates_by_id={_CELL_ID: cell, _OTHER_ID: other_type},
            unresolved_components=[],
        )
