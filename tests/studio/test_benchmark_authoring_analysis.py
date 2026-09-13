"""Revision-bound Studio Benchmark validation and dry-run contracts."""

from __future__ import annotations

from pathlib import Path
from io import BytesIO

import pytest

from zhixing.benchmark import BenchmarkDiagnostic
from zhixing.studio import (
    SQLiteAgentDocumentRepository,
    StudioApplicationService,
    build_studio_component_catalog,
)
from zhixing.studio.repository import CompileSnapshot
from zhixing.studio.benchmark_authoring_analysis import (
    StudioBenchmarkAuthoringAnalysisService,
    StudioBenchmarkValidationDryRunApplicationService,
)
from zhixing.studio.benchmark_authoring_analysis_models import (
    STUDIO_BENCHMARK_ANALYSIS_MAX_AGENTS,
    STUDIO_BENCHMARK_ANALYSIS_MAX_SCHEDULE_ENTRIES,
    STUDIO_BENCHMARK_ANALYSIS_MAX_TASKS,
    project_authoring_diagnostics,
)
from zhixing.studio.benchmark_authoring_errors import (
    StudioBenchmarkAuthoringCapacityError,
    StudioBenchmarkAuthoringNotFoundError,
    StudioBenchmarkAuthoringRevisionConflictError,
    StudioBenchmarkAuthoringStorageError,
    StudioBenchmarkAuthoringValidationError,
)
from zhixing.studio.benchmark_authoring_import import (
    StudioBenchmarkAuthoringPackageAdapter,
)
from zhixing.studio.benchmark_authoring_materializer import (
    StudioBenchmarkAuthoringPackageMaterializer,
)
from zhixing.studio.benchmark_authoring_repository import (
    SQLiteStudioBenchmarkAuthoringRepository,
)
from zhixing.studio.benchmark_authoring_service import (
    StudioBenchmarkAuthoringApplicationService,
)
from zhixing.studio.benchmark_authoring_storage import (
    LocalStudioBenchmarkManagedContent,
    default_studio_benchmark_authoring_root,
)
from zhixing.studio.benchmark_service import StudioBenchmarkCatalogService
from zhixing.studio.flow_template_loader import get_flow_template_document


def _analysis_fixture(tmp_path: Path) -> dict[str, object]:
    """Build one real draft, immutable Agent revision, and analysis service.

    Args:
        tmp_path: Pytest temporary persistence root.

    Raises:
        OSError: Local persistence cannot be prepared.

    Returns:
        Named test services and created revision facts.
    """
    database = tmp_path / "studio.sqlite3"
    repository = SQLiteStudioBenchmarkAuthoringRepository(database)
    content = LocalStudioBenchmarkManagedContent(
        default_studio_benchmark_authoring_root(database)
    )
    authoring = StudioBenchmarkAuthoringApplicationService(
        repository=repository,
        packages=StudioBenchmarkAuthoringPackageAdapter(
            content,
            staging_root=content.staging_root,
        ),
        catalog=StudioBenchmarkCatalogService(),
    )
    created = authoring.create_draft(
        {
            "schemaVersion": 1,
            "clientRequestId": "analysis-create",
            "name": "Analysis Draft",
            "source": {
                "kind": "template",
                "template": "minimal",
                "publisher": "tests",
                "packageName": "analysis",
                "version": "0.1.0",
            },
        }
    )
    agents = SQLiteAgentDocumentRepository(database)
    components = build_studio_component_catalog()
    agent_service = StudioApplicationService(
        catalog=components,
        repository=agents,
    )
    agent, agent_revision = agent_service.create_agent(
        "Analysis Agent",
        initial_document=get_flow_template_document("modular_baseline"),
    )
    analysis = StudioBenchmarkAuthoringAnalysisService(
        repository=repository,
        materializer=StudioBenchmarkAuthoringPackageMaterializer(
            content,
            staging_root=content.staging_root / "analysis",
        ),
        agents=agents,
        contract_catalog=components.node_contract_catalog(),
    )
    return {
        "repository": repository,
        "authoring": authoring,
        "analysis": analysis,
        "materializer": analysis._materializer,
        "agents": agents,
        "components": components,
        "content": content,
        "draft": created.draft,
        "revision": created.revision,
        "agent": agent,
        "agentRevision": agent_revision,
        "agentService": agent_service,
        "staging": content.staging_root / "analysis",
    }


def _validation_request(revision_id: str) -> dict[str, object]:
    """Build one exact validation request payload.

    Args:
        revision_id: Current authoring revision identity.

    Returns:
        JSON-compatible strict request.
    """
    return {"schemaVersion": 1, "revisionId": revision_id, "split": "test"}


def _dry_run_request(
    revision_id: str,
    agent_id: str,
    agent_revision_id: str,
) -> dict[str, object]:
    """Build one exact dry-run request payload.

    Args:
        revision_id: Current authoring revision identity.
        agent_id: Selected Agent identity.
        agent_revision_id: Selected immutable Agent revision identity.

    Returns:
        JSON-compatible strict request.
    """
    return {
        "schemaVersion": 1,
        "revisionId": revision_id,
        "split": "test",
        "taskIds": [],
        "agentRevisions": [
            {"agentId": agent_id, "revisionId": agent_revision_id}
        ],
    }


def _resource_document_payload(
    revision: object,
    *,
    content_identity: str,
    sha256: str,
    size: int,
) -> dict[str, object]:
    """Add one coherent asset descriptor to an authoring revision payload.

    Args:
        revision: Existing immutable authoring revision.
        content_identity: Private managed-content identity.
        sha256: Declared prefixed digest.
        size: Declared byte count.

    Raises:
        AttributeError: Revision does not expose a strict document.

    Returns:
        JSON-compatible save payload document.
    """
    document = revision.document.model_dump(  # type: ignore[attr-defined]
        mode="json", by_alias=True
    )
    manifest_resource = {
        "id": "fixture",
        "kind": "asset",
        "path": "assets/fixture.txt",
        "media_type": "text/plain",
        "sha256": sha256,
        "size": size,
    }
    document["manifest"]["document"]["resources"] = [manifest_resource]
    document["resources"] = [
        {
            "id": "fixture",
            "kind": "asset",
            "path": "assets/fixture.txt",
            "mediaType": "text/plain",
            "sha256": sha256,
            "size": size,
            "contentIdentity": content_identity,
        }
    ]
    return document


def test_analysis_request_bounds_and_fingerprints_are_explicit(
    tmp_path: Path,
) -> None:
    """Lock the first C-1 request bounds and deterministic fingerprints."""
    fixture = _analysis_fixture(tmp_path)
    analysis = fixture["analysis"]
    revision = fixture["revision"]
    agent = fixture["agent"]
    agent_revision = fixture["agentRevision"]
    validation = analysis.parse_validation_request(  # type: ignore[union-attr]
        _validation_request(revision.revision_id)  # type: ignore[union-attr]
    )
    dry_run = analysis.parse_dry_run_request(  # type: ignore[union-attr]
        _dry_run_request(
            revision.revision_id,  # type: ignore[union-attr]
            agent.agent_id,  # type: ignore[union-attr]
            agent_revision.revision_id,  # type: ignore[union-attr]
        )
    )
    assert validation.fingerprint.startswith("sha256:")
    assert dry_run.fingerprint.startswith("sha256:")
    assert STUDIO_BENCHMARK_ANALYSIS_MAX_AGENTS == 16
    assert STUDIO_BENCHMARK_ANALYSIS_MAX_TASKS == 100
    assert STUDIO_BENCHMARK_ANALYSIS_MAX_SCHEDULE_ENTRIES == 10_000


@pytest.mark.parametrize(
    "mutation",
    (
        lambda payload: payload.update({"destination": "/tmp/forbidden"}),
        lambda payload: payload.update({"split": "../escape"}),
        lambda payload: payload.update(
            {
                "taskIds": ["same", "same"],
            }
        ),
        lambda payload: payload.update(
            {
                "agentRevisions": payload["agentRevisions"] * 17,
            }
        ),
        lambda payload: payload.update(
            {
                "taskIds": [f"task-{index}" for index in range(101)],
            }
        ),
    ),
)
def test_analysis_requests_reject_unknown_unsafe_duplicate_and_overbound_values(
    tmp_path: Path,
    mutation,
) -> None:
    """Reject caller capabilities and invalid selection shapes before reads."""
    fixture = _analysis_fixture(tmp_path)
    analysis = fixture["analysis"]
    revision = fixture["revision"]
    agent = fixture["agent"]
    agent_revision = fixture["agentRevision"]
    payload = _dry_run_request(
        revision.revision_id,  # type: ignore[union-attr]
        agent.agent_id,  # type: ignore[union-attr]
        agent_revision.revision_id,  # type: ignore[union-attr]
    )
    mutation(payload)
    with pytest.raises(StudioBenchmarkAuthoringValidationError):
        analysis.parse_dry_run_request(payload)  # type: ignore[union-attr]


def test_diagnostic_projection_is_sorted_capped_and_redacted(
    tmp_path: Path,
) -> None:
    """Expose only bounded declared paths and redact private capabilities."""
    fixture = _analysis_fixture(tmp_path)
    revision = fixture["revision"]
    private_identity = "benchmark-content-" + "a" * 64
    diagnostics = tuple(
        BenchmarkDiagnostic(
            code=f"benchmark.test.{index:03d}",
            message=(
                f"/Users/private/secret-{index} {private_identity} must not leak"
            ),
            source=(
                "tasks/test.json" if index % 2 else "/private/tmp/package"
            ),
            path=(0, "instruction"),
            task_id="example-task",
        )
        for index in range(105)
    )
    projected, truncated = project_authoring_diagnostics(
        diagnostics,
        document=revision.document,  # type: ignore[union-attr]
        split="test",
    )
    assert truncated
    assert len(projected) == 100
    serialized = str(
        [item.model_dump(mode="json", by_alias=True) for item in projected]
    )
    assert "/Users/private" not in serialized
    assert "/private/tmp" not in serialized
    assert private_identity not in serialized
    repeated, repeated_truncated = project_authoring_diagnostics(
        reversed(diagnostics),
        document=revision.document,  # type: ignore[union-attr]
        split="test",
    )
    assert repeated_truncated
    assert repeated == projected


def test_validation_emits_staged_identities_and_no_execution_claim(
    tmp_path: Path,
) -> None:
    """Return exact canonical definition identities without execution evidence."""
    fixture = _analysis_fixture(tmp_path)
    analysis = fixture["analysis"]
    draft = fixture["draft"]
    revision = fixture["revision"]
    request = analysis.parse_validation_request(  # type: ignore[union-attr]
        _validation_request(revision.revision_id)  # type: ignore[union-attr]
    )
    result = analysis.validate(draft.draft_id, request)  # type: ignore[union-attr]
    assert result.valid
    assert result.execution_evidence is False
    assert result.identities.package == "tests/analysis@0.1.0"
    assert result.identities.package_content.startswith("sha256:")
    assert result.identities.benchmark_plan.startswith("sha256:")
    assert result.identities.experiment_protocol.startswith("sha256:")
    assert result.unverified_checks == ("plugin-availability",)


def test_dry_run_is_deterministic_complete_and_definition_only(
    tmp_path: Path,
) -> None:
    """Produce the same bounded schedule from exact Plan/Protocol/Agent facts."""
    fixture = _analysis_fixture(tmp_path)
    analysis = fixture["analysis"]
    draft = fixture["draft"]
    revision = fixture["revision"]
    agent = fixture["agent"]
    agent_revision = fixture["agentRevision"]
    request = analysis.parse_dry_run_request(  # type: ignore[union-attr]
        _dry_run_request(
            revision.revision_id,  # type: ignore[union-attr]
            agent.agent_id,  # type: ignore[union-attr]
            agent_revision.revision_id,  # type: ignore[union-attr]
        )
    )
    first = analysis.dry_run(draft.draft_id, request)  # type: ignore[union-attr]
    second = analysis.dry_run(draft.draft_id, request)  # type: ignore[union-attr]
    assert first == second
    assert first.ok
    assert first.execution_evidence is False
    assert len(first.schedule) == 1
    assert first.schedule[0].task_id == "example-task"
    assert first.schedule[0].agent_id == agent.agent_id  # type: ignore[union-attr]
    assert first.agent_revisions[0].agent_graph_identity.startswith("sha256:")
    assert first.output_layout is not None
    assert first.output_layout.experiment_report.startswith("<artifact-root>")
    assert "current-worker-cardinality" not in first.unverified_checks


def test_analysis_rejects_stale_revision_before_compilation(
    tmp_path: Path,
) -> None:
    """Return current pointer evidence instead of analyzing historical content."""
    fixture = _analysis_fixture(tmp_path)
    analysis = fixture["analysis"]
    authoring = fixture["authoring"]
    draft = fixture["draft"]
    revision = fixture["revision"]
    authoring.save_revision(  # type: ignore[union-attr]
        draft.draft_id,  # type: ignore[union-attr]
        {
            "schemaVersion": 1,
            "clientRequestId": "advance-current",
            "baseRevisionId": revision.revision_id,  # type: ignore[union-attr]
            "document": revision.document.model_dump(  # type: ignore[union-attr]
                mode="json", by_alias=True
            ),
        },
    )
    request = analysis.parse_validation_request(  # type: ignore[union-attr]
        _validation_request(revision.revision_id)  # type: ignore[union-attr]
    )
    with pytest.raises(StudioBenchmarkAuthoringRevisionConflictError) as caught:
        analysis.validate(draft.draft_id, request)  # type: ignore[union-attr]
    assert caught.value.current_revision_id != revision.revision_id  # type: ignore[union-attr]


def test_invalid_task_diagnostic_points_to_declared_member_and_local_field(
    tmp_path: Path,
) -> None:
    """Localize aggregate BenchmarkTask errors to the authoring task file."""
    fixture = _analysis_fixture(tmp_path)
    analysis = fixture["analysis"]
    authoring = fixture["authoring"]
    draft = fixture["draft"]
    revision = fixture["revision"]
    document = revision.document.model_dump(  # type: ignore[union-attr]
        mode="json", by_alias=True
    )
    document["taskFiles"][0]["tasks"][0]["max_steps"] = 0
    saved = authoring.save_revision(  # type: ignore[union-attr]
        draft.draft_id,  # type: ignore[union-attr]
        {
            "schemaVersion": 1,
            "clientRequestId": "invalid-task",
            "baseRevisionId": revision.revision_id,  # type: ignore[union-attr]
            "document": document,
        },
    )
    request = analysis.parse_validation_request(  # type: ignore[union-attr]
        _validation_request(saved.revision.revision_id)
    )
    result = analysis.validate(draft.draft_id, request)  # type: ignore[union-attr]
    assert not result.valid
    assert result.identities.package == "tests/analysis@0.1.0"
    assert result.identities.package_content is None
    assert result.identities.benchmark_plan is None
    diagnostic = next(
        item for item in result.diagnostics if item.member_kind == "task"
    )
    assert diagnostic.member_path == "tasks/test.json"
    assert diagnostic.field_path == (0, "max_steps")
    assert diagnostic.task_id == "example-task"


def test_validation_unknown_split_and_missing_default_protocol_are_facts(
    tmp_path: Path,
) -> None:
    """Keep semantic failures in 200-style results with truthful partial IDs."""
    fixture = _analysis_fixture(tmp_path)
    analysis = fixture["analysis"]
    authoring = fixture["authoring"]
    draft = fixture["draft"]
    revision = fixture["revision"]
    unknown = analysis.validate(  # type: ignore[union-attr]
        draft.draft_id,  # type: ignore[union-attr]
        analysis.parse_validation_request(  # type: ignore[union-attr]
            {
                "schemaVersion": 1,
                "revisionId": revision.revision_id,  # type: ignore[union-attr]
                "split": "unknown",
            }
        ),
    )
    assert not unknown.valid
    assert unknown.identities.package_content is not None
    assert unknown.identities.benchmark_plan is None
    assert any(
        item.code == "benchmark.split.not_found"
        for item in unknown.diagnostics
    )

    document = revision.document.model_dump(  # type: ignore[union-attr]
        mode="json", by_alias=True
    )
    document["manifest"]["document"].pop("default_protocol")
    saved = authoring.save_revision(  # type: ignore[union-attr]
        draft.draft_id,  # type: ignore[union-attr]
        {
            "schemaVersion": 1,
            "clientRequestId": "missing-protocol",
            "baseRevisionId": revision.revision_id,  # type: ignore[union-attr]
            "document": document,
        },
    )
    missing = analysis.validate(  # type: ignore[union-attr]
        draft.draft_id,  # type: ignore[union-attr]
        analysis.parse_validation_request(  # type: ignore[union-attr]
            _validation_request(saved.revision.revision_id)
        ),
    )
    assert not missing.valid
    assert missing.identities.benchmark_plan is not None
    assert missing.identities.experiment_protocol is None
    assert any(
        item.code == "benchmark.protocol.default_required"
        and item.member_kind == "manifest"
        and item.field_path == ("default_protocol",)
        for item in missing.diagnostics
    )


def test_validation_reports_missing_resource_but_fails_closed_on_corruption(
    tmp_path: Path,
) -> None:
    """Separate logical absence from untrusted stored-byte integrity drift."""
    fixture = _analysis_fixture(tmp_path)
    analysis = fixture["analysis"]
    authoring = fixture["authoring"]
    content = fixture["content"]
    draft = fixture["draft"]
    revision = fixture["revision"]
    missing_document = _resource_document_payload(
        revision,
        content_identity="benchmark-content-" + "a" * 64,
        sha256="sha256:" + "a" * 64,
        size=7,
    )
    missing_saved = authoring.save_revision(  # type: ignore[union-attr]
        draft.draft_id,  # type: ignore[union-attr]
        {
            "schemaVersion": 1,
            "clientRequestId": "missing-resource",
            "baseRevisionId": revision.revision_id,  # type: ignore[union-attr]
            "document": missing_document,
        },
    )
    missing = analysis.validate(  # type: ignore[union-attr]
        draft.draft_id,  # type: ignore[union-attr]
        analysis.parse_validation_request(  # type: ignore[union-attr]
            _validation_request(missing_saved.revision.revision_id)
        ),
    )
    assert not missing.valid
    assert missing.identities.package == "tests/analysis@0.1.0"
    assert missing.identities.package_content is None
    assert missing.identities.benchmark_plan is None
    assert any(
        item.code == "benchmark.resource.content_unavailable"
        and item.resource_id == "fixture"
        and item.member_path == "assets/fixture.txt"
        for item in missing.diagnostics
    )

    raw = b"trusted"
    content_identity, digest, size = content.store_stream(  # type: ignore[union-attr]
        BytesIO(raw), max_bytes=100
    )
    corrupt_document = _resource_document_payload(
        missing_saved.revision,
        content_identity=content_identity,
        sha256=digest,
        size=size,
    )
    corrupt_saved = authoring.save_revision(  # type: ignore[union-attr]
        draft.draft_id,  # type: ignore[union-attr]
        {
            "schemaVersion": 1,
            "clientRequestId": "corrupt-resource",
            "baseRevisionId": missing_saved.revision.revision_id,
            "document": corrupt_document,
        },
    )
    content.content_path(content_identity).write_bytes(b"corrupt")  # type: ignore[union-attr]
    with pytest.raises(StudioBenchmarkAuthoringStorageError):
        analysis.validate(  # type: ignore[union-attr]
            draft.draft_id,  # type: ignore[union-attr]
            analysis.parse_validation_request(  # type: ignore[union-attr]
                _validation_request(corrupt_saved.revision.revision_id)
            ),
        )


def test_validation_hides_foreign_revision_ownership(
    tmp_path: Path,
) -> None:
    """Return hidden not-found before disclosing another draft's pointer."""
    fixture = _analysis_fixture(tmp_path)
    analysis = fixture["analysis"]
    authoring = fixture["authoring"]
    first_revision = fixture["revision"]
    second = authoring.create_draft(  # type: ignore[union-attr]
        {
            "schemaVersion": 1,
            "clientRequestId": "foreign-create",
            "name": "Foreign Draft",
            "source": {
                "kind": "template",
                "template": "minimal",
                "publisher": "tests",
                "packageName": "foreign-analysis",
                "version": "0.1.0",
            },
        }
    )
    request = analysis.parse_validation_request(  # type: ignore[union-attr]
        _validation_request(first_revision.revision_id)  # type: ignore[union-attr]
    )
    with pytest.raises(StudioBenchmarkAuthoringNotFoundError):
        analysis.validate(second.draft.draft_id, request)  # type: ignore[union-attr]


def test_validation_rechecks_current_pointer_after_analysis(
    tmp_path: Path,
) -> None:
    """Discard a completed computation when a concurrent save wins the race."""
    fixture = _analysis_fixture(tmp_path)
    repository = fixture["repository"]
    authoring = fixture["authoring"]
    draft = fixture["draft"]
    revision = fixture["revision"]

    class AdvancingRepository:
        """Delegate reads while advancing the pointer on its second draft read."""

        def __init__(self) -> None:
            """Initialize a one-shot concurrent-save injection."""
            self.reads = 0

        def get_draft(self, draft_id: str):
            """Advance the pointer just before the response-time recheck.

            Args:
                draft_id: Requested draft identity.

            Returns:
                Current delegated draft record.
            """
            self.reads += 1
            if self.reads == 2:
                document = revision.document.model_dump(  # type: ignore[union-attr]
                    mode="json", by_alias=True
                )
                document["manifest"]["document"]["title"] = "Concurrent"
                authoring.save_revision(  # type: ignore[union-attr]
                    draft_id,
                    {
                        "schemaVersion": 1,
                        "clientRequestId": "concurrent-save",
                        "baseRevisionId": revision.revision_id,  # type: ignore[union-attr]
                        "document": document,
                    },
                )
            return repository.get_draft(draft_id)  # type: ignore[union-attr]

        def get_revision(self, draft_id: str, revision_id: str):
            """Delegate exact owned revision reads.

            Args:
                draft_id: Owning draft identity.
                revision_id: Exact immutable revision identity.

            Returns:
                Delegated immutable revision.
            """
            return repository.get_revision(  # type: ignore[union-attr]
                draft_id, revision_id
            )

    raced = StudioBenchmarkValidationDryRunApplicationService(
        repository=AdvancingRepository(),  # type: ignore[arg-type]
        materializer=fixture["materializer"],  # type: ignore[arg-type]
        agents=fixture["agents"],  # type: ignore[arg-type]
        contract_catalog=fixture["components"].node_contract_catalog(),  # type: ignore[union-attr]
    )
    request = raced.parse_validation_request(
        _validation_request(revision.revision_id)  # type: ignore[union-attr]
    )
    with pytest.raises(StudioBenchmarkAuthoringRevisionConflictError):
        raced.validate(draft.draft_id, request)  # type: ignore[union-attr]


def test_repeated_validation_never_mutates_durable_authoring_state(
    tmp_path: Path,
) -> None:
    """Keep revision ordinal, fingerprint, status, and pointer unchanged."""
    fixture = _analysis_fixture(tmp_path)
    analysis = fixture["analysis"]
    repository = fixture["repository"]
    draft = fixture["draft"]
    revision = fixture["revision"]
    request = analysis.parse_validation_request(  # type: ignore[union-attr]
        _validation_request(revision.revision_id)  # type: ignore[union-attr]
    )
    first = analysis.validate(draft.draft_id, request)  # type: ignore[union-attr]
    second = analysis.validate(draft.draft_id, request)  # type: ignore[union-attr]
    durable_draft = repository.get_draft(draft.draft_id)  # type: ignore[union-attr]
    durable_revision = repository.get_revision(  # type: ignore[union-attr]
        draft.draft_id, revision.revision_id  # type: ignore[union-attr]
    )
    assert first == second
    assert durable_draft.current_revision_id == revision.revision_id  # type: ignore[union-attr]
    assert durable_revision.ordinal == 1
    assert durable_revision.status == "unvalidated"
    assert durable_revision.document_fingerprint == first.document_fingerprint


def test_dry_run_checks_cardinality_before_allocating_schedule(
    tmp_path: Path,
) -> None:
    """Reject an oversized matrix before the Core schedule builder is called."""
    fixture = _analysis_fixture(tmp_path)
    analysis = fixture["analysis"]
    authoring = fixture["authoring"]
    draft = fixture["draft"]
    revision = fixture["revision"]
    agent = fixture["agent"]
    agent_revision = fixture["agentRevision"]
    document = revision.document.model_dump(  # type: ignore[union-attr]
        mode="json", by_alias=True
    )
    document["protocolFiles"][0]["document"]["repeats"] = 10_001
    saved = authoring.save_revision(  # type: ignore[union-attr]
        draft.draft_id,  # type: ignore[union-attr]
        {
            "schemaVersion": 1,
            "clientRequestId": "large-schedule",
            "baseRevisionId": revision.revision_id,  # type: ignore[union-attr]
            "document": document,
        },
    )
    request = analysis.parse_dry_run_request(  # type: ignore[union-attr]
        _dry_run_request(
            saved.revision.revision_id,
            agent.agent_id,  # type: ignore[union-attr]
            agent_revision.revision_id,  # type: ignore[union-attr]
        )
    )
    with pytest.raises(StudioBenchmarkAuthoringCapacityError) as caught:
        analysis.dry_run(draft.draft_id, request)  # type: ignore[union-attr]
    assert caught.value.code == "benchmark.authoring.schedule_too_large"


def test_dry_run_accepts_exact_ten_thousand_entry_boundary(
    tmp_path: Path,
) -> None:
    """Allow a complete schedule exactly at the aggregate output cap."""
    fixture = _analysis_fixture(tmp_path)
    analysis = fixture["analysis"]
    authoring = fixture["authoring"]
    draft = fixture["draft"]
    revision = fixture["revision"]
    agent = fixture["agent"]
    agent_revision = fixture["agentRevision"]
    document = revision.document.model_dump(  # type: ignore[union-attr]
        mode="json", by_alias=True
    )
    document["protocolFiles"][0]["document"]["repeats"] = 10_000
    saved = authoring.save_revision(  # type: ignore[union-attr]
        draft.draft_id,  # type: ignore[union-attr]
        {
            "schemaVersion": 1,
            "clientRequestId": "exact-cap-schedule",
            "baseRevisionId": revision.revision_id,  # type: ignore[union-attr]
            "document": document,
        },
    )
    request = analysis.parse_dry_run_request(  # type: ignore[union-attr]
        _dry_run_request(
            saved.revision.revision_id,
            agent.agent_id,  # type: ignore[union-attr]
            agent_revision.revision_id,  # type: ignore[union-attr]
        )
    )
    result = analysis.dry_run(draft.draft_id, request)  # type: ignore[union-attr]
    assert result.ok
    assert len(result.schedule) == 10_000
    assert "current-worker-cardinality" in result.unverified_checks


def test_dry_run_supports_many_agents_and_explicit_task_subset(
    tmp_path: Path,
) -> None:
    """Build the full Agent matrix only for the caller's valid task subset."""
    fixture = _analysis_fixture(tmp_path)
    analysis = fixture["analysis"]
    authoring = fixture["authoring"]
    agent_service = fixture["agentService"]
    draft = fixture["draft"]
    revision = fixture["revision"]
    first_agent = fixture["agent"]
    first_agent_revision = fixture["agentRevision"]
    second_agent, second_agent_revision = agent_service.create_agent(  # type: ignore[union-attr]
        "Second Analysis Agent",
        initial_document=get_flow_template_document("modular_baseline"),
    )
    document = revision.document.model_dump(  # type: ignore[union-attr]
        mode="json", by_alias=True
    )
    second_task = dict(document["taskFiles"][0]["tasks"][0])
    second_task["id"] = "second-task"
    document["taskFiles"][0]["tasks"].append(second_task)
    saved = authoring.save_revision(  # type: ignore[union-attr]
        draft.draft_id,  # type: ignore[union-attr]
        {
            "schemaVersion": 1,
            "clientRequestId": "two-tasks",
            "baseRevisionId": revision.revision_id,  # type: ignore[union-attr]
            "document": document,
        },
    )
    request = analysis.parse_dry_run_request(  # type: ignore[union-attr]
        {
            "schemaVersion": 1,
            "revisionId": saved.revision.revision_id,
            "split": "test",
            "taskIds": ["second-task"],
            "agentRevisions": [
                {
                    "agentId": first_agent.agent_id,  # type: ignore[union-attr]
                    "revisionId": first_agent_revision.revision_id,  # type: ignore[union-attr]
                },
                {
                    "agentId": second_agent.agent_id,
                    "revisionId": second_agent_revision.revision_id,
                },
            ],
        }
    )
    result = analysis.dry_run(draft.draft_id, request)  # type: ignore[union-attr]
    assert result.ok
    assert len(result.schedule) == 2
    assert {item.task_id for item in result.schedule} == {"second-task"}
    assert [item.agent_id for item in result.schedule] == sorted(
        (first_agent.agent_id, second_agent.agent_id)  # type: ignore[union-attr]
    )


def test_dry_run_projects_fairness_dynamic_and_worker_scope_warnings(
    tmp_path: Path,
) -> None:
    """Preserve declared fairness while naming unexecuted dynamic work."""
    fixture = _analysis_fixture(tmp_path)
    analysis = fixture["analysis"]
    authoring = fixture["authoring"]
    agent = fixture["agent"]
    agent_revision = fixture["agentRevision"]
    created = authoring.create_draft(  # type: ignore[union-attr]
        {
            "schemaVersion": 1,
            "clientRequestId": "dynamic-create",
            "name": "Dynamic Draft",
            "source": {
                "kind": "template",
                "template": "dynamic-task",
                "publisher": "tests",
                "packageName": "dynamic-analysis",
                "version": "0.1.0",
            },
        }
    )
    document = created.revision.document.model_dump(
        mode="json", by_alias=True
    )
    protocol = document["protocolFiles"][0]["document"]
    protocol["repeats"] = 2
    protocol["task_materialization"]["reuse_across_agents"] = False
    saved = authoring.save_revision(  # type: ignore[union-attr]
        created.draft.draft_id,
        {
            "schemaVersion": 1,
            "clientRequestId": "dynamic-fairness",
            "baseRevisionId": created.revision.revision_id,
            "document": document,
        },
    )
    request = analysis.parse_dry_run_request(  # type: ignore[union-attr]
        _dry_run_request(
            saved.revision.revision_id,
            agent.agent_id,  # type: ignore[union-attr]
            agent_revision.revision_id,  # type: ignore[union-attr]
        )
    )
    result = analysis.dry_run(created.draft.draft_id, request)  # type: ignore[union-attr]
    assert result.ok
    assert result.fairness_warnings == (
        "benchmark.protocol.unpaired_materialization",
    )
    assert "dynamic-task-materialization" in result.unverified_checks
    assert "current-worker-cardinality" in result.unverified_checks
    assert len({item.seed for item in result.schedule}) == 2


def test_dry_run_returns_agent_addressed_failure_without_schedule(
    tmp_path: Path,
) -> None:
    """Keep missing or foreign Agent revisions as bounded analysis facts."""
    fixture = _analysis_fixture(tmp_path)
    analysis = fixture["analysis"]
    draft = fixture["draft"]
    revision = fixture["revision"]
    request = analysis.parse_dry_run_request(  # type: ignore[union-attr]
        _dry_run_request(
            revision.revision_id,  # type: ignore[union-attr]
            "agent-" + "f" * 32,
            "revision-" + "e" * 32,
        )
    )
    result = analysis.dry_run(draft.draft_id, request)  # type: ignore[union-attr]
    assert not result.ok
    assert result.schedule == ()
    diagnostic = next(
        item for item in result.diagnostics if item.member_kind == "agent"
    )
    assert diagnostic.agent_id == "agent-" + "f" * 32
    assert diagnostic.revision_id == "revision-" + "e" * 32
    assert diagnostic.member_path is None


def test_dry_run_rejects_saved_agent_revision_without_policy_identity_closure(
    tmp_path: Path,
) -> None:
    """Reverify policy and graph evidence instead of trusting revision existence."""
    fixture = _analysis_fixture(tmp_path)
    analysis = fixture["analysis"]
    agents = fixture["agents"]
    draft = fixture["draft"]
    revision = fixture["revision"]
    agent = fixture["agent"]
    agent_revision = fixture["agentRevision"]
    _, invalid_revision = agents.save_revision(  # type: ignore[union-attr]
        agent.agent_id,  # type: ignore[union-attr]
        base_revision_id=agent_revision.revision_id,  # type: ignore[union-attr]
        document=agent_revision.document,  # type: ignore[union-attr]
        snapshot=CompileSnapshot(status="invalid"),
    )
    request = analysis.parse_dry_run_request(  # type: ignore[union-attr]
        _dry_run_request(
            revision.revision_id,  # type: ignore[union-attr]
            agent.agent_id,  # type: ignore[union-attr]
            invalid_revision.revision_id,
        )
    )
    result = analysis.dry_run(draft.draft_id, request)  # type: ignore[union-attr]
    assert not result.ok
    assert result.schedule == ()
    assert any(
        item.code
        == "benchmark.authoring.studio.policy.authoring_policy_unsupported"
        and item.agent_id == agent.agent_id  # type: ignore[union-attr]
        for item in result.diagnostics
    )


def test_disposable_analysis_package_is_removed_after_each_request(
    tmp_path: Path,
) -> None:
    """Leave no revision reconstruction behind after successful validation."""
    fixture = _analysis_fixture(tmp_path)
    analysis = fixture["analysis"]
    draft = fixture["draft"]
    revision = fixture["revision"]
    staging = fixture["staging"]
    request = analysis.parse_validation_request(  # type: ignore[union-attr]
        _validation_request(revision.revision_id)  # type: ignore[union-attr]
    )
    analysis.validate(draft.draft_id, request)  # type: ignore[union-attr]
    assert list(staging.iterdir()) == []  # type: ignore[union-attr]


def test_validation_and_dry_run_cross_no_runtime_or_publication_boundaries(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Install fail-fast canaries at representative forbidden side effects."""
    import socket

    import zhixing.benchmark.reporting.writer as report_writer
    import zhixing.benchmark.runtime.evaluator as runtime_evaluator
    import zhixing.benchmark.runtime.lifecycle as runtime_lifecycle
    import zhixing.benchmark.runtime.materializer as runtime_materializer
    import zhixing.benchmark.runtime.suite as runtime_suite
    import zhixing.studio.benchmark_execution as benchmark_execution
    import zhixing.studio.benchmark_experiment_service as experiment_service
    import zhixing.studio.benchmark_publication as publication
    import zhixing.studio.benchmark_replay as benchmark_replay
    import zhixing.studio.replay_service as replay_service
    import zhixing.studio.run_execution as run_execution
    import zhixing.studio.service as studio_service

    calls: dict[str, int] = {}

    def fail(name: str):
        """Return one canary that records and rejects a forbidden call.

        Args:
            name: Side-effect boundary label.

        Returns:
            Variadic failure callable for monkeypatching.
        """

        def canary(*args, **kwargs):
            """Record a forbidden boundary crossing and fail immediately.

            Args:
                *args: Ignored target positional arguments.
                **kwargs: Ignored target keyword arguments.

            Raises:
                AssertionError: Always, because analysis must not call it.
            """
            del args, kwargs
            calls[name] = calls.get(name, 0) + 1
            raise AssertionError(f"analysis crossed forbidden {name} boundary")

        return canary

    targets = (
        (runtime_materializer, "materialize_task", "initializer/plugin"),
        (runtime_lifecycle, "execute_environment_calls", "environment/device"),
        (runtime_evaluator, "evaluate_tree", "evaluator"),
        (runtime_suite.BenchmarkExperimentRuntime, "run", "benchmark-runtime"),
        (run_execution.ProductionComponentResolverFactory, "create", "secret/model"),
        (run_execution.AndroidDeviceProfileResolver, "resolve", "android"),
        (
            run_execution.AndroidStudioRunExecutionAdapter,
            "execute",
            "agent-execution",
        ),
        (benchmark_execution.StudioBenchmarkExecutionAdapter, "execute", "task-result"),
        (
            experiment_service.StudioBenchmarkExperimentApplicationService,
            "create_experiment",
            "experiment",
        ),
        (report_writer, "write_experiment_artifacts", "report/trajectory/bundle"),
        (publication.DurableStudioBenchmarkPublisher, "publish", "publication"),
        (benchmark_replay.NativeStudioBenchmarkReplayPublisher, "build", "replay"),
        (replay_service.ReplayApplicationService, "export_bundle", "export"),
        (studio_service.StudioApplicationService, "migrate_document", "migration"),
        (socket, "create_connection", "network"),
    )
    for target, attribute, name in targets:
        monkeypatch.setattr(target, attribute, fail(name))

    fixture = _analysis_fixture(tmp_path)
    analysis = fixture["analysis"]
    draft = fixture["draft"]
    revision = fixture["revision"]
    agent = fixture["agent"]
    agent_revision = fixture["agentRevision"]
    validation = analysis.validate(  # type: ignore[union-attr]
        draft.draft_id,  # type: ignore[union-attr]
        analysis.parse_validation_request(  # type: ignore[union-attr]
            _validation_request(revision.revision_id)  # type: ignore[union-attr]
        ),
    )
    dry_run = analysis.dry_run(  # type: ignore[union-attr]
        draft.draft_id,  # type: ignore[union-attr]
        analysis.parse_dry_run_request(  # type: ignore[union-attr]
            _dry_run_request(
                revision.revision_id,  # type: ignore[union-attr]
                agent.agent_id,  # type: ignore[union-attr]
                agent_revision.revision_id,  # type: ignore[union-attr]
            )
        ),
    )
    assert validation.valid
    assert dry_run.ok
    assert calls == {}
