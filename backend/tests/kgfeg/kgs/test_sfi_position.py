"""Tests for sibling position and statement code in the Learning Commons export."""

# Future Library
from __future__ import annotations

# Standard Library
from typing import Any
from uuid import UUID

# Third Party Library
import pytest

# Package Library
from kgfeg.kgs import sfi_export
from kgfeg.kgs.schemas import (
    SFIFinalContext,
    SFIHasChildEdge,
    StandardsFramework,
    StandardsFrameworkItem,
)
from kgfeg.schemas import CreateKGConfig

_FRAMEWORK = UUID(int=1)


def _context(*, number: int, order: int) -> SFIFinalContext:
    """Build a minimal final context for one item."""

    return SFIFinalContext(
        description=f"Item {number}.",
        final_sfi_uuid=UUID(int=number),
        normalized_statement_type="Standard",
        source_context_labels=["Synthetic"],
        source_order=order,
        statement_type="Performance Objective",
    )


def _edge(*, child: int, parent: int | None) -> SFIHasChildEdge:
    """Build one hasChild edge; `parent=None` is a root edge from the framework."""

    parent_uuid = _FRAMEWORK if parent is None else UUID(int=parent)
    return SFIHasChildEdge(
        child_final_sfi_uuid=UUID(int=child),
        is_root_edge=parent is None,
        llm_reason="Synthetic.",
        parent_endpoint_id=str(parent_uuid),
        parent_final_sfi_uuid=None if parent is None else parent_uuid,
        relationship_id=UUID(int=1000 + child * 10 + (parent or 0)),
        source_entity=(
            "StandardsFramework" if parent is None else "StandardsFrameworkItem"
        ),
        source_entity_uuid=parent_uuid,
        target_sfi_uuid=UUID(int=child),
    )


def _item(*, number: int, **overrides: Any) -> StandardsFrameworkItem:
    """Build one schema-valid exported item."""

    return StandardsFrameworkItem(
        academic_subject="Synthetic subject",
        attribution_statement="Synthetic attribution",
        author="Synthetic authority",
        case_identifier_uri=f"urn:uuid:{UUID(int=number)}",
        case_identifier_uuid=UUID(int=number),
        description=f"Item {number}.",
        identifier=UUID(int=number),
        in_language="en",
        jurisdiction="Synthetic jurisdiction",
        license="Synthetic license",
        normalized_statement_type="Standard",
        provider="Synthetic provider",
        **overrides,
    )


def _framework() -> StandardsFramework:
    """Build the schema-valid framework root."""

    return StandardsFramework(
        academic_subject="Synthetic subject",
        adoption_status="Adopted",
        attribution_statement="Synthetic attribution",
        author="Synthetic authority",
        case_identifier_uri=f"urn:uuid:{_FRAMEWORK}",
        case_identifier_uuid=_FRAMEWORK,
        identifier=_FRAMEWORK,
        in_language="en",
        jurisdiction="Synthetic jurisdiction",
        license="Synthetic license",
        name="Synthetic framework",
        provider="Synthetic provider",
    )


def test_positions_follow_source_order_not_list_order() -> None:
    """Siblings are numbered from zero in source order, per parent."""

    # Item 2 is the root; 5, 3, 4 are its children, in source order 3 < 4 < 5.
    contexts = [
        _context(number=2, order=0),
        _context(number=5, order=1),
        _context(number=3, order=2),
        _context(number=4, order=3),
    ]
    edges = [
        _edge(child=2, parent=None),
        _edge(child=4, parent=2),
        _edge(child=3, parent=2),
        _edge(child=5, parent=2),
    ]

    positions = sfi_export._build_sibling_positions(
        contexts=contexts, has_child_edges=edges
    )

    assert positions == {
        UUID(int=2): 0,
        UUID(int=5): 0,
        UUID(int=3): 1,
        UUID(int=4): 2,
    }


def test_multi_parent_child_is_numbered_under_one_parent_only() -> None:
    """A child reachable from two parents gets one position, under the earlier parent."""

    contexts = [
        _context(number=2, order=0),
        _context(number=3, order=1),
        _context(number=4, order=2),
        _context(number=5, order=3),
    ]
    edges = [
        _edge(child=2, parent=None),
        _edge(child=3, parent=2),
        _edge(child=4, parent=2),
        _edge(child=5, parent=4),
        _edge(child=5, parent=3),
    ]

    positions = sfi_export._build_sibling_positions(
        contexts=contexts, has_child_edges=edges
    )

    assert positions[UUID(int=5)] == 0
    assert positions[UUID(int=3)] == 0
    assert positions[UUID(int=4)] == 1


def test_missing_context_is_rejected() -> None:
    """An edge whose child has no final context fails loudly."""

    with pytest.raises(ValueError, match="final context"):
        sfi_export._build_sibling_positions(
            contexts=[_context(number=2, order=0)],
            has_child_edges=[_edge(child=3, parent=None)],
        )


def test_position_and_statement_code_reach_the_wire_as_strings() -> None:
    """Both properties are serialized as strings and omitted when unset."""

    coded = _item(number=2, position=3, statement_code="1.1")
    plain = _item(number=3)

    nodes = sfi_export._build_learning_commons_nodes(
        grade_level_mapping={}, sf=_framework(), sfis=[coded, plain]
    )
    wire = [
        node.model_dump(by_alias=True, exclude_none=True, mode="json")["properties"]
        for node in nodes[1:]
    ]

    assert wire[0]["position"] == "3"
    assert wire[0]["statementCode"] == "1.1"
    assert "position" not in wire[1]
    assert "statementCode" not in wire[1]


def test_validator_flags_a_dropped_position_or_code() -> None:
    """The export validator fails when a node loses position or statementCode."""

    item = _item(number=2, position=0, statement_code="a)")
    nodes = sfi_export._build_learning_commons_nodes(
        grade_level_mapping={}, sf=_framework(), sfis=[item]
    )
    node = nodes[1]
    clean = sfi_export._validate_learning_commons_item_payload(
        grade_level_mapping={}, item=item, item_node=node
    )
    node.properties.position = None
    node.properties.statement_code = None
    broken = sfi_export._validate_learning_commons_item_payload(
        grade_level_mapping={}, item=item, item_node=node
    )

    assert clean == []
    assert any("position" in error for error in broken)
    assert any("statementCode" in error for error in broken)


def test_sibling_position_is_off_by_default() -> None:
    """The flag defaults to off so existing exports stay byte-identical."""

    field = CreateKGConfig.model_fields["academic_standards"].annotation
    assert field.model_fields["emit_sibling_position"].default is False
