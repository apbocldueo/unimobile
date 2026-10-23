"""Repository and application-service tests for Studio Agent revisions."""

from __future__ import annotations

import sqlite3
from copy import deepcopy

import pytest

from zhixing.studio import (
    AgentRevisionConflictError,
    SQLiteAgentDocumentRepository,
    StudioApplicationError,
    StudioApplicationService,
    build_studio_component_catalog,
    workspace_identity,
)

from .test_documents_catalog_compiler import _planner_document


def _service(database_path) -> StudioApplicationService:
    """Create a test application service over one explicit database.

    Args:
        database_path (Path): Temporary SQLite path.

    Raises:
        sqlite3.Error: Repository migration fails.

    Returns:
        StudioApplicationService: Configured service.
    """
    return StudioApplicationService(
        catalog=build_studio_component_catalog(),
        repository=SQLiteAgentDocumentRepository(database_path),
    )


def test_sqlite_revision_persists_and_detects_optimistic_conflict(tmp_path) -> None:
    """Persist immutable revisions across restart and reject a stale base."""
    database = tmp_path / "studio.sqlite3"
    service = _service(database)
    agent, first = service.create_agent(
        "Planner",
        initial_document=_planner_document(),
    )
    assert first.compile_snapshot.status == "valid"
    assert first.compile_snapshot.canonical_hash is not None

    changed = first.document.to_json_dict()
    changed["presentation"]["nodes"]["canvas-planner"]["x"] = 720
    _, second = service.save_revision(
        agent.agent_id,
        base_revision_id=first.revision_id,
        raw_document=changed,
    )
    assert second.ordinal == 2
    assert second.parent_revision_id == first.revision_id
    assert second.compile_snapshot.canonical_hash == first.compile_snapshot.canonical_hash

    with pytest.raises(AgentRevisionConflictError) as captured:
        service.save_revision(
            agent.agent_id,
            base_revision_id=first.revision_id,
            raw_document=changed,
        )
    assert captured.value.current_revision_id == second.revision_id

    restarted = _service(database)
    loaded_agent, loaded_revision = restarted.get_agent(agent.agent_id)
    assert loaded_agent.current_revision_id == second.revision_id
    assert loaded_revision is not None
    assert loaded_revision.document.to_json_dict() == second.document.to_json_dict()
    assert restarted.get_revision(
        agent.agent_id,
        first.revision_id,
    ).ordinal == 1


def test_rename_does_not_mutate_revision_and_list_is_bounded(tmp_path) -> None:
    """Keep Agent metadata separate from revision data and paginate safely."""
    service = _service(tmp_path / "studio.sqlite3")
    first_agent, first_revision = service.create_agent(
        "First",
        initial_document=_planner_document(),
    )
    service.create_agent("Second")
    renamed = service.rename_agent(first_agent.agent_id, "Renamed")
    assert renamed.name == "Renamed"
    assert service.get_revision(
        first_agent.agent_id,
        first_revision.revision_id,
    ).document.name == "First"

    first_page = service.list_agents(limit=1)
    assert len(first_page.items) == 1
    assert first_page.next_cursor is not None
    second_page = service.list_agents(limit=1, cursor=first_page.next_cursor)
    assert len(second_page.items) == 1
    assert second_page.items[0].agent_id != first_page.items[0].agent_id


def test_invalid_draft_is_saved_without_graph_or_hash(tmp_path) -> None:
    """Persist a structurally valid unfinished draft as explicitly invalid."""
    service = _service(tmp_path / "studio.sqlite3")
    _agent, revision = service.create_agent("Draft")
    assert revision.compile_snapshot.status == "invalid"
    assert revision.compile_snapshot.agent_graph is None
    assert revision.compile_snapshot.canonical_hash is None
    assert any(
        item.code == "graph.reachability.unreachable_node"
        for item in revision.compile_snapshot.diagnostics
    )


def test_raw_secret_is_rejected_before_revision_transaction(tmp_path) -> None:
    """Prevent resolved secret material from reaching SQLite."""
    database = tmp_path / "studio.sqlite3"
    service = _service(database)
    agent, revision = service.create_agent(
        "Planner",
        initial_document=_planner_document(),
    )
    unsafe = revision.document.to_json_dict()
    unsafe["semantic"]["nodes"][1]["component"]["candidates"][0]["params"][
        "api_key"
    ] = "resolved-secret-value"
    with pytest.raises(StudioApplicationError) as captured:
        service.save_revision(
            agent.agent_id,
            base_revision_id=revision.revision_id,
            raw_document=unsafe,
        )
    assert captured.value.code == "studio.document.invalid"
    connection = sqlite3.connect(database)
    try:
        count = connection.execute(
            "SELECT COUNT(*) FROM studio_agent_revisions WHERE agent_id = ?",
            (agent.agent_id,),
        ).fetchone()[0]
        dump = "\n".join(connection.iterdump())
    finally:
        connection.close()
    assert count == 1
    assert "resolved-secret-value" not in dump


def test_unsafe_node_metadata_never_reaches_sqlite(tmp_path) -> None:
    """Reject raw secrets, live objects, and host paths in authoring metadata."""
    database = tmp_path / "studio.sqlite3"
    service = _service(database)
    agent, revision = service.create_agent(
        "Planner",
        initial_document=_planner_document(),
    )
    unsafe_values = (
        {"api_key": "resolved-secret-value"},
        {"runtime": object()},
        {"source_path": str(tmp_path / "private.py")},
    )
    for metadata in unsafe_values:
        document = revision.document.to_json_dict()
        document["semantic"]["nodes"][1]["metadata"] = metadata
        with pytest.raises(StudioApplicationError):
            service.save_revision(
                agent.agent_id,
                base_revision_id=revision.revision_id,
                raw_document=document,
            )
    connection = sqlite3.connect(database)
    try:
        dump = "\n".join(connection.iterdump())
    finally:
        connection.close()
    assert "resolved-secret-value" not in dump
    assert str(tmp_path) not in dump


def test_workspace_identity_is_opaque_and_stable(tmp_path) -> None:
    """Derive the same workspace key without returning its absolute path."""
    first = workspace_identity(tmp_path)
    second = workspace_identity(tmp_path)
    assert first == second
    assert first.startswith("sha256:")
    assert str(tmp_path) not in first


def test_failed_revision_serialization_rolls_back_initial_create(tmp_path) -> None:
    """Leave no partial Agent when SQLite rejects an inconsistent snapshot."""
    repository = SQLiteAgentDocumentRepository(tmp_path / "studio.sqlite3")
    document = _planner_document()
    document["agentId"] = "agent-rollback"
    from zhixing.studio import CompileSnapshot, StudioFlowDocument

    parsed = StudioFlowDocument.model_validate(document)
    with pytest.raises(ValueError):
        repository.create_agent(
            "Rollback",
            parsed,
            CompileSnapshot(
                status="invalid",
                agent_graph={"secret": "not-allowed"},
            ),
        )
    assert repository.list_agents().items == ()


def test_semantic_edit_changes_hash(tmp_path) -> None:
    """Change canonical identity when a semantic component parameter changes."""
    service = _service(tmp_path / "studio.sqlite3")
    agent, first = service.create_agent(
        "Planner",
        initial_document=_planner_document(),
    )
    changed = deepcopy(first.document.to_json_dict())
    changed["semantic"]["nodes"][1]["component"]["candidates"][0]["params"][
        "preset"
    ] = "mobimind_style"
    _, second = service.save_revision(
        agent.agent_id,
        base_revision_id=first.revision_id,
        raw_document=changed,
    )
    assert second.compile_snapshot.canonical_hash != first.compile_snapshot.canonical_hash
