"""Stage 5.2C-2 formal publication and native Replay contract tests."""

from __future__ import annotations

import http.client
import hashlib
import io
import json
import sqlite3
import threading
import zipfile
from dataclasses import replace
from pathlib import Path
from typing import Any, Callable

import pytest

from tests.benchmark.test_experiment_runtime import (
    FakeBenchmarkDevice,
    FakeBenchmarkResolver,
)
from tests.studio.test_benchmark_execution_worker import _agent, _task
from tests.studio.test_benchmark_experiment_resource import _resource_service
from zhixing.benchmark import (
    BenchmarkExperimentRuntime,
    BenchmarkOutcome,
    BenchmarkPublicationPolicy,
    BenchmarkRunConfig,
    ExperimentProtocol,
    compile_benchmark_suite,
)
from zhixing.components import Action, ActionType, RunStatus
from zhixing.config.contracts import BenchmarkSuite
from zhixing.studio import StudioApplicationService, build_studio_component_catalog
from zhixing.studio.benchmark_artifacts import (
    CoreStudioBenchmarkBundleVerifier,
    LocalStudioBenchmarkManagedArtifactStore,
)
from zhixing.studio.benchmark_composition import StudioBenchmarkComposition
from zhixing.studio.benchmark_errors import (
    StudioBenchmarkIntegrityError,
    StudioBenchmarkNotFoundError,
    StudioBenchmarkStorageError,
)
from zhixing.studio.benchmark_evidence import (
    LocalStudioBenchmarkEvidenceStore,
)
from zhixing.studio.benchmark_experiment_models import (
    StudioBenchmarkEventDraftV1,
    StudioBenchmarkExperimentLifecycle,
    StudioBenchmarkExperimentTerminalReason,
    StudioBenchmarkTaskRunLifecycle,
    StudioBenchmarkTaskRunTerminalReason,
)
from zhixing.studio.benchmark_publication import (
    CoreStudioBenchmarkPublicationPreparer,
    DurableStudioBenchmarkPublisher,
)
from zhixing.studio import benchmark_publication as benchmark_publication_module
from zhixing.studio.benchmark_publication_models import (
    StudioBenchmarkArtifactAvailability,
    StudioBenchmarkArtifactDescriptorV1,
    StudioBenchmarkPublicationRecordV1,
)
from zhixing.studio.benchmark_publication_repository import (
    SQLiteStudioBenchmarkPublicationRepository,
)
from zhixing.studio.benchmark_replay import (
    NativeStudioBenchmarkReplayPublisher,
)
from zhixing.studio.benchmark_result import project_benchmark_task_result
from zhixing.studio.database import (
    STUDIO_SQLITE_SCHEMA_VERSION,
    migrate_studio_database,
)
from zhixing.studio.httpd import create_http_server
from zhixing.studio.evidence_origin import StudioExecutionEvidenceOriginV1
from zhixing.studio.replay_service import build_default_replay_service
from zhixing.studio.replay_storage import default_studio_artifact_directory


def _read_publication_payloads(path: Path) -> bytes:
    """Read one managed file and recursively expand ZIP member payloads.

    Args:
        path: Managed publication file.

    Raises:
        OSError: The file cannot be read.
        zipfile.BadZipFile: A declared ZIP is malformed.

    Returns:
        Concatenated bytes suitable for deterministic canary scanning.
    """
    content = path.read_bytes()
    if path.suffix.lower() != ".zip" and not content.startswith(b"PK"):
        return content
    collected = [content]
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        for name in archive.namelist():
            member = archive.read(name)
            collected.append(member)
            if name.endswith(".zip"):
                with zipfile.ZipFile(io.BytesIO(member)) as nested:
                    collected.extend(
                        nested.read(nested_name)
                        for nested_name in nested.namelist()
                    )
    return b"\n".join(collected)


def _ready_core_result(
    tmp_path: Path,
    *,
    outcome: BenchmarkOutcome = BenchmarkOutcome.PASS,
    agent_status: RunStatus | None = None,
    terminal_reason: StudioBenchmarkTaskRunTerminalReason = (
        StudioBenchmarkTaskRunTerminalReason.COMPLETED
    ),
) -> tuple[Any, Any, Any, Any]:
    """Create one finalizing Experiment with a committed immutable TaskResult.

    Args:
        tmp_path: Isolated workspace root.
        outcome: Optional independent Benchmark outcome override.
        agent_status: Optional Agent RunStatus override.
        terminal_reason: Durable service TaskRun terminal reason.

    Returns:
        Experiment service, repository, complete Core suite, and TaskRun.
    """
    service, repository, payload = _resource_service(tmp_path)
    experiment = service.create_experiment(payload).experiment
    owner = "benchmark-publication-test-owner"
    repository.enroll_accepted_experiment(
        experiment.experiment_id,
        process_owner_id=owner,
    )
    claimed = repository.claim_experiment(
        experiment.experiment_id,
        process_owner_id=owner,
        timestamp=10,
    )
    task = claimed.task_runs[0]
    repository.transition_execution(
        experiment.experiment_id,
        task.task_run_id,
        process_owner_id=owner,
        experiment_lifecycle=StudioBenchmarkExperimentLifecycle.RUNNING,
        task_lifecycle=StudioBenchmarkTaskRunLifecycle.RUNNING,
        timestamp=11,
        event=StudioBenchmarkEventDraftV1(
            event_id=f"benchmark-event-{'1' * 32}",
            timestamp=11,
            kind="worker.execution_started",
            task_run_id=task.task_run_id,
        ),
    )
    compiled = compile_benchmark_suite(
        BenchmarkSuite.model_validate([_task(task.task_id)])
    )
    assert compiled.plan is not None
    suite = BenchmarkExperimentRuntime().run(
        compiled.plan,
        ExperimentProtocol(),
        {
            task.agent_id: _agent(
                Action(ActionType.KEY, {"code": "home"})
            )
        },
        run_config=BenchmarkRunConfig(
            artifact_root=(
                tmp_path
                / "private-evidence"
                / experiment.experiment_id
                / "runtime"
            ),
            experiment_id=experiment.experiment_id,
            publication_policy=BenchmarkPublicationPolicy.DEFER,
        ),
        resolver=FakeBenchmarkResolver(),
        device=FakeBenchmarkDevice(),
    )
    core_result = suite.results[0]
    agent_result = core_result.agent_result
    if agent_status is not None and agent_result is not None:
        agent_result = replace(agent_result, status=agent_status)
    core_result = replace(
        core_result,
        outcome=outcome,
        agent_result=agent_result,
    )
    origin = StudioExecutionEvidenceOriginV1(
        acquisition="contract_fixture",
        environment="fake_device",
        device_profile_id="local-android",
    )
    suite = replace(
        suite,
        results=(core_result,),
        device_provenance={
            key: value
            for key, value in suite.device_provenance.items()
            if key != "device_id"
        }
        | {
            "evidence_origin": origin.model_dump(
                mode="json",
                by_alias=True,
                exclude_none=True,
            )
        },
    )
    projected, fingerprint = project_benchmark_task_result(
        core_result,
        planned_task_run_id=task.task_run_id,
        agent_revision_id=task.revision_id,
        schedule_order=task.order,
        service_terminal_reason=(
            terminal_reason
        ),
        evidence_origin=origin,
    )
    repository.commit_task_result(
        experiment.experiment_id,
        task.task_run_id,
        process_owner_id=owner,
        result=projected,
        fingerprint=fingerprint,
        terminal_reason=terminal_reason,
        timestamp=12,
    )
    return service, repository, suite, task


def _publisher(
    tmp_path: Path,
    repository: Any,
    *,
    failure_step: str | None = None,
    event_commit_hook: Callable[[str], None] | None = None,
) -> tuple[
    CoreStudioBenchmarkPublicationPreparer,
    SQLiteStudioBenchmarkPublicationRepository,
    LocalStudioBenchmarkManagedArtifactStore,
    DurableStudioBenchmarkPublisher,
]:
    """Build publication dependencies over one shared database.

    Args:
        tmp_path: Isolated workspace root.
        repository: Durable Experiment repository.
        failure_step: Optional coordinated transaction failure checkpoint.
        event_commit_hook: Optional post-commit waiter notification callback.

    Returns:
        Preparer, publication repository, store, and publisher.
    """
    evidence = LocalStudioBenchmarkEvidenceStore(
        tmp_path / "private-evidence",
        minimum_free_bytes=0,
    )
    preparer = CoreStudioBenchmarkPublicationPreparer(evidence)

    def failure_hook(step: str) -> None:
        """Raise at one configured transaction checkpoint.

        Args:
            step: Stable repository checkpoint.

        Raises:
            RuntimeError: Configured checkpoint was reached.
        """
        if step == failure_step:
            raise RuntimeError("injected publication rollback")

    publications = SQLiteStudioBenchmarkPublicationRepository(
        tmp_path / "studio.sqlite3",
        failure_hook=failure_hook if failure_step is not None else None,
        event_commit_hook=event_commit_hook,
    )
    artifacts = LocalStudioBenchmarkManagedArtifactStore(
        default_studio_artifact_directory(tmp_path / "studio.sqlite3"),
        publications,
    )
    publisher = DurableStudioBenchmarkPublisher(
        experiments=repository,
        publications=publications,
        preparer=preparer,
        artifacts=artifacts,
        bundles=CoreStudioBenchmarkBundleVerifier(),
        replay=NativeStudioBenchmarkReplayPublisher(
            repository,
            artifacts,
        ),
    )
    return preparer, publications, artifacts, publisher


def test_publication_dtos_reject_inconsistent_readable_shapes() -> None:
    """Keep hidden/readable metadata and typed identities explicit."""
    with pytest.raises(ValueError):
        StudioBenchmarkArtifactDescriptorV1(
            artifact_id=f"artifact-{'1' * 32}",
            experiment_id=f"experiment-{'2' * 32}",
            kind="prompt",
            availability="hidden",
            content_type="text/plain",
            size=5,
            sha256=f"sha256:{'3' * 64}",
            hidden=False,
        )
    with pytest.raises(ValueError):
        StudioBenchmarkPublicationRecordV1(
            experiment_id=f"experiment-{'2' * 32}",
            task_run_id=f"task-run-{'4' * 32}",
            publication_fingerprint=f"sha256:{'5' * 64}",
            preparation_fingerprint=f"sha256:{'6' * 64}",
            preparation_availability="available",
            report_availability="available",
            trajectory_availability="not_produced",
            bundle_availability="not_produced",
            replay_availability="not_produced",
            journal_high_water_mark=1,
            published_at=1,
        )


@pytest.mark.parametrize(
    ("availability", "hidden", "content_type", "sha256"),
    [
        ("pending", False, "", None),
        ("not_produced", False, "", None),
        ("excluded", False, "", None),
        ("missing", False, "", None),
        ("corrupt", False, "", None),
        ("failed", False, "", None),
        ("hidden", True, "", None),
    ],
)
def test_publication_dtos_accept_explicit_unreadable_states(
    availability: str,
    hidden: bool,
    content_type: str,
    sha256: str | None,
) -> None:
    """Represent every unreadable evidence state without a download shape."""
    descriptor = StudioBenchmarkArtifactDescriptorV1(
        artifact_id=f"artifact-{'1' * 32}",
        experiment_id=f"experiment-{'2' * 32}",
        kind="optional_evidence",
        availability=availability,
        content_type=content_type,
        sha256=sha256,
        hidden=hidden,
    )
    assert descriptor.availability.value == availability
    assert descriptor.hidden is hidden


def test_schema_five_upgrade_adds_publication_without_losing_task_runs(
    tmp_path: Path,
) -> None:
    """Upgrade a populated schema-5 shape through migration 6."""
    service, _repository, payload = _resource_service(tmp_path)
    created = service.create_experiment(payload).experiment
    database = tmp_path / "studio.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.execute("PRAGMA foreign_keys = OFF")
        connection.execute("DROP TABLE studio_benchmark_artifacts")
        connection.execute("DROP TABLE studio_benchmark_publications")
        for column in (
            "publication_diagnostics_json",
            "replay_id",
            "bundle_availability",
            "trajectory_availability",
            "report_availability",
        ):
            connection.execute(
                f"ALTER TABLE studio_benchmark_task_runs DROP COLUMN {column}"
            )
        connection.execute(
            "DELETE FROM studio_schema_migrations WHERE version = 6"
        )
    migrate_studio_database(database)
    with sqlite3.connect(database) as connection:
        versions = [
            row[0]
            for row in connection.execute(
                "SELECT version FROM studio_schema_migrations ORDER BY version"
            )
        ]
        task_row = connection.execute(
            "SELECT report_availability, trajectory_availability, "
            "bundle_availability, replay_id, "
            "publication_diagnostics_json "
            "FROM studio_benchmark_task_runs WHERE experiment_id = ?",
            (created.experiment_id,),
        ).fetchone()
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
    assert versions == list(range(1, STUDIO_SQLITE_SCHEMA_VERSION + 1))
    assert task_row == ("not_produced", "not_produced", "not_produced", None, "[]")
    assert {
        "studio_benchmark_publications",
        "studio_benchmark_artifacts",
    } <= tables


def test_managed_store_rejects_unsafe_types_limits_and_symlinks(
    tmp_path: Path,
) -> None:
    """Accept only declared bounded regular members under the trusted root."""
    _service, repository, suite, task = _ready_core_result(tmp_path)
    preparer, publications, _artifacts, _publisher_service = _publisher(
        tmp_path,
        repository,
    )
    preparer.prepare(
        suite,
        planned_task_run_id=task.task_run_id,
        definition_snapshot=repository.get_experiment(
            suite.experiment_id
        ).definition.model_dump(
            mode="json",
            by_alias=True,
            exclude_none=True,
        ),
        prepared_at=13,
    )
    trusted = tmp_path / "trusted"
    trusted.mkdir()
    source = trusted / "member.json"
    source.write_bytes(b'{"value":1}\n')
    digest = "sha256:" + hashlib.sha256(source.read_bytes()).hexdigest()
    store = LocalStudioBenchmarkManagedArtifactStore(
        tmp_path / "managed-limit-test",
        publications,
        maximum_file_bytes=source.stat().st_size,
        maximum_experiment_bytes=source.stat().st_size,
    )
    first = store.import_file(
        experiment_id=suite.experiment_id,
        task_run_id=task.task_run_id,
        reference="member.json",
        kind="task_result",
        content_type="application/json",
        source=source,
        trusted_root=trusted,
        expected_sha256=digest,
    )
    repeated = store.import_file(
        experiment_id=suite.experiment_id,
        task_run_id=task.task_run_id,
        reference="member.json",
        kind="task_result",
        content_type="application/json",
        source=source,
        trusted_root=trusted,
        expected_sha256=digest,
    )
    assert repeated == first
    with pytest.raises(StudioBenchmarkIntegrityError):
        store.import_file(
            experiment_id=suite.experiment_id,
            task_run_id=task.task_run_id,
            reference="member.json",
            kind="task_result",
            content_type="application/octet-stream",
            source=source,
            trusted_root=trusted,
            expected_sha256=digest,
        )
    oversized = trusted / "oversized.json"
    oversized.write_bytes(b'{"value":12}\n')
    oversized_digest = (
        "sha256:" + hashlib.sha256(oversized.read_bytes()).hexdigest()
    )
    with pytest.raises(StudioBenchmarkIntegrityError):
        store.import_file(
            experiment_id=suite.experiment_id,
            task_run_id=task.task_run_id,
            reference="oversized.json",
            kind="task_result",
            content_type="application/json",
            source=oversized,
            trusted_root=trusted,
            expected_sha256=oversized_digest,
        )
    outside = tmp_path / "outside.json"
    outside.write_bytes(source.read_bytes())
    symlink = trusted / "symlink.json"
    symlink.symlink_to(outside)
    with pytest.raises(StudioBenchmarkIntegrityError):
        store.import_file(
            experiment_id=suite.experiment_id,
            task_run_id=task.task_run_id,
            reference="symlink.json",
            kind="task_result",
            content_type="application/json",
            source=symlink,
            trusted_root=trusted,
            expected_sha256=digest,
        )
    with pytest.raises(StudioBenchmarkIntegrityError):
        preparer.member_path(suite.experiment_id, "../escape.json")


def test_formal_publication_and_native_replay_are_idempotent(
    tmp_path: Path,
) -> None:
    """Expose formal Core output and one native Replay atomically."""
    service, repository, suite, task = _ready_core_result(tmp_path)
    notifications: list[str] = []
    preparer, publications, artifacts, publisher = _publisher(
        tmp_path,
        repository,
        event_commit_hook=notifications.append,
    )
    prepared = preparer.prepare(
        suite,
        planned_task_run_id=task.task_run_id,
        definition_snapshot=repository.get_experiment(
            suite.experiment_id
        ).definition.model_dump(
            mode="json",
            by_alias=True,
            exclude_none=True,
        ),
        prepared_at=13,
    )
    assert len(prepared.members) > 10
    assert {"screenshot", "action_evidence", "runtime_manifest"} <= {
        member.kind for member in prepared.members
    }
    before = repository.get_experiment(suite.experiment_id)
    publication = publisher.publish(
        suite.experiment_id,
        task.task_run_id,
        timestamp=14,
    )
    after_first = repository.get_experiment(suite.experiment_id)
    repeated = publisher.publish(
        suite.experiment_id,
        task.task_run_id,
        timestamp=99,
    )
    after_second = repository.get_experiment(suite.experiment_id)
    assert repeated == publication
    assert publication.report_availability == "available"
    assert publication.trajectory_availability == "available"
    assert publication.bundle_availability == "available"
    assert publication.replay_availability == "available"
    assert after_first.event_high_water_mark == (
        before.event_high_water_mark + 1
    )
    assert after_second.event_high_water_mark == after_first.event_high_water_mark
    assert notifications == [suite.experiment_id]
    restored = service.get_task_run(
        suite.experiment_id,
        task.task_run_id,
    )
    assert restored.result is not None
    assert restored.replay_id == publication.replay_id
    assert restored.links is not None
    assert restored.links.replay == f"/studio/replays/{publication.replay_id}"
    assert len(restored.artifacts) >= 3
    assert "screenshot" in {
        descriptor.kind for descriptor in restored.artifacts
    }
    report_record = publications.get_artifact(
        suite.experiment_id,
        publication.report_artifact_id,
    )
    descriptor, stream = artifacts.open_artifact(
        suite.experiment_id,
        report_record.descriptor.artifact_id,
    )
    try:
        report = json.load(stream)
    finally:
        stream.close()
    assert descriptor.kind == "experiment_report"
    assert report["experiment_id"] == suite.experiment_id
    replay = build_default_replay_service(
        tmp_path / "studio.sqlite3"
    ).get_replay(publication.replay_id)
    assert replay.provenance == "native_benchmark_task_run"
    assert replay.benchmark is not None
    assert replay.benchmark.outcome == "pass"
    assert replay.moments
    assert any(
        observation.screenshot_artifact_id is not None
        for observation in replay.observations
    )
    reopened = SQLiteStudioBenchmarkPublicationRepository(
        tmp_path / "studio.sqlite3"
    )
    assert reopened.get_publication(suite.experiment_id) == publication


def test_studio_bundle_is_complete_verified_and_sanitized(
    tmp_path: Path,
) -> None:
    """Bundle immutable definition, formal output, and sanitized runtime facts."""
    _service, repository, suite, task = _ready_core_result(tmp_path)
    runtime_action = (
        tmp_path
        / "private-evidence"
        / suite.experiment_id
        / "runtime"
        / suite.results[0].artifact_namespace
        / "interaction-0000"
        / "action-0000.json"
    )
    runtime_action.write_text(
        json.dumps(
            {
                "prompt": "do-not-publish-prompt",
                "api_key": "sk-do-not-publish",
                "serial": "emulator-5554",
                "path": "/Users/example/private/evidence.json",
                "adb_arguments": "adb -s emulator-5554 shell getprop",
                "binding_fingerprint": "sha256:private-binding-canary",
                "configuration_path": "/private/config/profile-canary.json",
                "device_handle": "live-handle-private-canary",
            }
        ),
        encoding="utf-8",
    )
    runtime_namespace = runtime_action.parents[1]
    (runtime_namespace / "prompt-0000.json").write_text(
        json.dumps({"prompt": "dedicated-prompt-canary"}),
        encoding="utf-8",
    )
    (runtime_namespace / "model-response-0000.json").write_text(
        json.dumps(
            {
                "response": "complete-model-response",
                "api_key": "sk-model-secret",
            }
        ),
        encoding="utf-8",
    )
    preparer, _publications, _artifacts, publisher = _publisher(
        tmp_path,
        repository,
    )
    prepared = preparer.prepare(
        suite,
        planned_task_run_id=task.task_run_id,
        definition_snapshot=repository.get_experiment(
            suite.experiment_id
        ).definition.model_dump(
            mode="json",
            by_alias=True,
            exclude_none=True,
        ),
        prepared_at=13,
    )
    bundle = preparer.member_path(
        suite.experiment_id,
        prepared.bundle_reference,
    )
    verifier = CoreStudioBenchmarkBundleVerifier()
    assert verifier.verify(bundle)
    with zipfile.ZipFile(bundle) as archive:
        names = set(archive.namelist())
        assert {
            "definition-snapshot.json",
            "studio-publication-manifest.json",
            "bundle-manifest.json",
        } <= names
        action_name = next(
            name
            for name in names
            if name.startswith("runtime/")
            and name.endswith("action-0000.json")
        )
        safe_action = json.loads(archive.read(action_name))
        response_name = next(
            name
            for name in names
            if name.startswith("runtime/")
            and name.endswith("model-response-0000.json")
        )
        safe_response = json.loads(archive.read(response_name))
        assert safe_response["response"] == "complete-model-response"
        assert safe_response["api_key"] == "<redacted>"
        assert all("prompt-0000.json" not in name for name in names)
        assert safe_action["prompt"] == "<hidden>"
        assert safe_action["api_key"] == "<redacted>"
        assert safe_action["serial"].startswith("device-sha256:")
        assert safe_action["path"] == "<host-path>"
        serialized = archive.read(action_name).decode("utf-8")
        assert "do-not-publish-prompt" not in serialized
        assert "sk-do-not-publish" not in serialized
        assert "emulator-5554" not in serialized
        assert "/Users/example" not in serialized
        assert "dedicated-prompt-canary" not in serialized
        assert "private-binding-canary" not in serialized
        assert "profile-canary.json" not in serialized
        assert "live-handle-private-canary" not in serialized
        assert "adb -s" not in serialized
        result_name = next(
            name
            for name in names
            if name.endswith("experiment-result.json")
        )
        published_result = json.loads(archive.read(result_name))
        assert published_result["result"]["device_provenance"]["evidence_origin"] == {
            "schemaVersion": 1,
            "acquisition": "contract_fixture",
            "environment": "fake_device",
            "deviceProfileId": "local-android",
            "deviceChecks": [],
            "realDeviceEvidence": False,
        }
    publication = publisher.publish(
        suite.experiment_id,
        task.task_run_id,
        timestamp=14,
    )
    replay_service = build_default_replay_service(
        tmp_path / "studio.sqlite3"
    )
    replay_bundle = replay_service.export_bundle(publication.replay_id)
    with zipfile.ZipFile(replay_bundle) as archive:
        readable_export = b"\n".join(
            archive.read(name)
            for name in archive.namelist()
            if not name.endswith(".zip")
        )
    assert b"do-not-publish-prompt" not in readable_export
    assert b"sk-do-not-publish" not in readable_export
    assert b"emulator-5554" not in readable_export
    assert b"/Users/example" not in readable_export
    assert b"dedicated-prompt-canary" not in readable_export
    assert b"sk-model-secret" not in readable_export
    replay = replay_service.get_replay(publication.replay_id)
    assert replay.evidence_origin.acquisition == "replay_projection"
    assert replay.evidence_origin.environment == "fake_device"
    assert replay.evidence_origin.real_device_evidence is False
    durable_public_bytes = [
        (tmp_path / "studio.sqlite3").read_bytes(),
        _read_publication_payloads(replay_bundle),
    ]
    durable_public_bytes.extend(
        _read_publication_payloads(path)
        for path in default_studio_artifact_directory(
            tmp_path / "studio.sqlite3"
        ).rglob("*")
        if path.is_file()
    )
    public_surface = b"\n".join(durable_public_bytes)
    for canary in (
        b"do-not-publish-prompt",
        b"dedicated-prompt-canary",
        b"sk-do-not-publish",
        b"sk-model-secret",
        b"emulator-5554",
        b"/Users/example",
        b"private-binding-canary",
        b"profile-canary.json",
        b"live-handle-private-canary",
        b"adb -s",
    ):
        assert canary not in public_surface
    tampered_bundle = tmp_path / "tampered-studio-bundle.zip"
    with zipfile.ZipFile(bundle) as source, zipfile.ZipFile(
        tampered_bundle,
        mode="w",
        compression=zipfile.ZIP_DEFLATED,
    ) as target:
        for name in source.namelist():
            target.writestr(
                name,
                b"tampered"
                if name == "definition-snapshot.json"
                else source.read(name),
            )
    assert verifier.verify(tampered_bundle) is False


@pytest.mark.parametrize(
    ("outcome", "agent_status", "terminal_reason"),
    [
        (
            BenchmarkOutcome.FAIL,
            RunStatus.SUCCESS,
            StudioBenchmarkTaskRunTerminalReason.COMPLETED,
        ),
        (
            BenchmarkOutcome.INVALID,
            RunStatus.SUCCESS,
            StudioBenchmarkTaskRunTerminalReason.COMPLETED,
        ),
        (
            BenchmarkOutcome.INVALID,
            RunStatus.DEVICE_FAILURE,
            StudioBenchmarkTaskRunTerminalReason.COMPLETED,
        ),
        (
            BenchmarkOutcome.SKIPPED,
            RunStatus.CANCELLED,
            StudioBenchmarkTaskRunTerminalReason.CANCELLED,
        ),
    ],
)
def test_native_replay_preserves_independent_terminal_facts(
    tmp_path: Path,
    outcome: BenchmarkOutcome,
    agent_status: RunStatus,
    terminal_reason: StudioBenchmarkTaskRunTerminalReason,
) -> None:
    """Keep Agent, Benchmark, device, and cancellation facts independent."""
    _service, repository, suite, task = _ready_core_result(
        tmp_path,
        outcome=outcome,
        agent_status=agent_status,
        terminal_reason=terminal_reason,
    )
    preparer, _publications, _artifacts, publisher = _publisher(
        tmp_path,
        repository,
    )
    preparer.prepare(
        suite,
        planned_task_run_id=task.task_run_id,
        definition_snapshot=repository.get_experiment(
            suite.experiment_id
        ).definition.model_dump(
            mode="json",
            by_alias=True,
            exclude_none=True,
        ),
        prepared_at=13,
    )
    publication = publisher.publish(
        suite.experiment_id,
        task.task_run_id,
        timestamp=14,
    )
    replay = build_default_replay_service(
        tmp_path / "studio.sqlite3"
    ).get_replay(publication.replay_id)
    assert replay.result.status == agent_status.value
    assert replay.benchmark is not None
    assert replay.benchmark.outcome == outcome.value
    assert replay.moments


def test_conflicting_replay_provenance_preserves_other_components(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fail Replay alone when its stable identity belongs to other evidence."""
    _service, repository, suite, task = _ready_core_result(tmp_path)
    preparer, publications, _artifacts, publisher = _publisher(
        tmp_path,
        repository,
    )
    preparer.prepare(
        suite,
        planned_task_run_id=task.task_run_id,
        definition_snapshot=repository.get_experiment(
            suite.experiment_id
        ).definition.model_dump(
            mode="json",
            by_alias=True,
            exclude_none=True,
        ),
        prepared_at=13,
    )
    conflicting_id = f"benchmark-replay-{'f' * 32}"
    monkeypatch.setattr(
        benchmark_publication_module,
        "benchmark_replay_id",
        lambda _fingerprint: conflicting_id,
    )
    with sqlite3.connect(tmp_path / "studio.sqlite3") as connection:
        connection.execute(
            """
            INSERT INTO studio_replays(
                run_id, agent_id, agent_status, benchmark_outcome,
                provenance, integrity_state, evidence_completeness,
                imported_at, envelope_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                conflicting_id,
                task.agent_id,
                "success",
                None,
                "native_studio_run",
                "complete",
                100,
                1,
                "{}",
            ),
        )
    publication = publisher.publish(
        suite.experiment_id,
        task.task_run_id,
        timestamp=14,
    )
    assert publication.report_availability == "available"
    assert publication.bundle_availability == "available"
    assert publication.replay_availability == "failed"
    assert publication.replay_id is None
    assert any(
        item.code == "benchmark.publication.replay_identity_conflict"
        for item in publication.diagnostics
    )
    assert publications.get_publication(suite.experiment_id) == publication
    with sqlite3.connect(tmp_path / "studio.sqlite3") as connection:
        row = connection.execute(
            "SELECT provenance FROM studio_replays WHERE run_id = ?",
            (conflicting_id,),
        ).fetchone()
    assert row == ("native_studio_run",)


def test_publication_rollback_hides_replay_artifacts_and_events(
    tmp_path: Path,
) -> None:
    """Roll back all metadata and notify-visible facts at one failure point."""
    _service, repository, suite, task = _ready_core_result(tmp_path)
    notifications: list[str] = []
    preparer, publications, _artifacts, publisher = _publisher(
        tmp_path,
        repository,
        failure_step="publication.after_replay",
        event_commit_hook=notifications.append,
    )
    preparer.prepare(
        suite,
        planned_task_run_id=task.task_run_id,
        definition_snapshot=repository.get_experiment(
            suite.experiment_id
        ).definition.model_dump(
            mode="json",
            by_alias=True,
            exclude_none=True,
        ),
        prepared_at=13,
    )
    high_water_mark = repository.get_experiment(
        suite.experiment_id
    ).event_high_water_mark
    with pytest.raises(StudioBenchmarkStorageError):
        publisher.publish(
            suite.experiment_id,
            task.task_run_id,
            timestamp=14,
        )
    assert publications.get_publication(suite.experiment_id) is None
    assert publications.list_artifacts(suite.experiment_id) == ()
    assert (
        repository.get_experiment(suite.experiment_id).event_high_water_mark
        == high_water_mark
    )
    assert notifications == []
    with sqlite3.connect(tmp_path / "studio.sqlite3") as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM studio_replays"
        ).fetchone()[0] == 0


def test_missing_preparation_does_not_rewrite_task_result(
    tmp_path: Path,
) -> None:
    """Commit safe failed component facts while retaining TaskResult."""
    service, repository, suite, task = _ready_core_result(tmp_path)
    _preparer, publications, _artifacts, publisher = _publisher(
        tmp_path,
        repository,
    )
    publication = publisher.publish(
        suite.experiment_id,
        task.task_run_id,
        timestamp=14,
    )
    assert publication.preparation_availability == "failed"
    assert publication.report_availability == "failed"
    assert publication.replay_availability == "failed"
    restored = service.get_task_run(
        suite.experiment_id,
        task.task_run_id,
    )
    assert restored.result is not None
    assert restored.result_availability.value == "available"
    assert restored.report_availability.value == "failed"
    assert publications.list_artifacts(suite.experiment_id) == ()


def test_bundle_failure_preserves_report_trajectory_and_replay(
    tmp_path: Path,
) -> None:
    """Keep independently verified publication components available."""
    _service, repository, suite, task = _ready_core_result(tmp_path)
    preparer, publications, artifacts, _publisher_service = _publisher(
        tmp_path,
        repository,
    )
    preparer.prepare(
        suite,
        planned_task_run_id=task.task_run_id,
        definition_snapshot=repository.get_experiment(
            suite.experiment_id
        ).definition.model_dump(
            mode="json",
            by_alias=True,
            exclude_none=True,
        ),
        prepared_at=13,
    )

    class RejectBundle:
        """Deterministically reject the Studio bundle only."""

        def verify(self, source: str | Path) -> bool:
            """Reject the candidate while retaining its private path.

            Args:
                source: Candidate bundle path.

            Returns:
                Always ``False``.
            """
            del source
            return False

    publisher = DurableStudioBenchmarkPublisher(
        experiments=repository,
        publications=publications,
        preparer=preparer,
        artifacts=artifacts,
        bundles=RejectBundle(),
        replay=NativeStudioBenchmarkReplayPublisher(
            repository,
            artifacts,
        ),
    )
    publication = publisher.publish(
        suite.experiment_id,
        task.task_run_id,
        timestamp=14,
    )
    assert publication.report_availability == "available"
    assert publication.trajectory_availability == "available"
    assert publication.bundle_availability == "failed"
    assert publication.bundle_artifact_id is None
    assert publication.replay_availability == "available"
    assert publication.replay_id is not None
    assert any(
        item.component == "experiment_bundle"
        for item in publication.diagnostics
    )


def test_startup_cancelled_no_result_does_not_create_replay(
    tmp_path: Path,
) -> None:
    """Leave all publication components unproduced for an empty cancellation."""
    service, repository, payload = _resource_service(tmp_path)
    experiment = service.create_experiment(payload).experiment
    owner = "benchmark-publication-cancel-owner"
    repository.enroll_accepted_experiment(
        experiment.experiment_id,
        process_owner_id=owner,
    )
    aggregate = repository.claim_experiment(
        experiment.experiment_id,
        process_owner_id=owner,
        timestamp=10,
    )
    task = aggregate.task_runs[0]
    repository.finish_task_without_result(
        experiment.experiment_id,
        task.task_run_id,
        process_owner_id=owner,
        terminal_reason=StudioBenchmarkTaskRunTerminalReason.CANCELLED,
        timestamp=11,
        error_code="benchmark.execution.cancelled",
    )
    repository.finalize_experiment(
        experiment.experiment_id,
        process_owner_id=owner,
        terminal_reason=StudioBenchmarkExperimentTerminalReason.CANCELLED,
        timestamp=12,
    )
    _preparer, publications, _artifacts, publisher = _publisher(
        tmp_path,
        repository,
    )
    with pytest.raises(ValueError, match="TaskResult"):
        publisher.publish(
            experiment.experiment_id,
            task.task_run_id,
            timestamp=13,
        )
    restored = service.get_task_run(
        experiment.experiment_id,
        task.task_run_id,
    )
    assert restored.result is None
    assert restored.report_availability.value == "not_produced"
    assert restored.trajectory_availability.value == "not_produced"
    assert restored.bundle_availability.value == "not_produced"
    assert restored.replay_availability.value == "not_produced"
    assert restored.replay_id is None
    assert publications.get_publication(experiment.experiment_id) is None


def test_managed_artifact_scope_and_corruption_close_safely(
    tmp_path: Path,
) -> None:
    """Hide cross-scope identities and close missing/corrupt readable content."""
    service, repository, suite, task = _ready_core_result(tmp_path)
    preparer, publications, artifacts, publisher = _publisher(
        tmp_path,
        repository,
    )
    preparer.prepare(
        suite,
        planned_task_run_id=task.task_run_id,
        definition_snapshot=repository.get_experiment(
            suite.experiment_id
        ).definition.model_dump(
            mode="json",
            by_alias=True,
            exclude_none=True,
        ),
        prepared_at=13,
    )
    publication = publisher.publish(
        suite.experiment_id,
        task.task_run_id,
        timestamp=14,
    )
    service.publication_repository = publications
    service._publication_enabled = True
    with pytest.raises(StudioBenchmarkNotFoundError):
        publications.get_artifact(
            f"experiment-{'f' * 32}",
            publication.report_artifact_id,
        )
    missing_record = next(
        record
        for record in publications.list_artifacts(
            suite.experiment_id,
            task_run_id=task.task_run_id,
        )
        if (
            record.descriptor.availability
            in {
                StudioBenchmarkArtifactAvailability.AVAILABLE,
                StudioBenchmarkArtifactAvailability.REDACTED,
                StudioBenchmarkArtifactAvailability.TRUNCATED,
            }
            and record.descriptor.artifact_id
            != publication.report_artifact_id
        )
    )
    artifacts.storage_path(missing_record).unlink()
    with pytest.raises(StudioBenchmarkNotFoundError) as missing:
        artifacts.open_artifact(
            suite.experiment_id,
            missing_record.descriptor.artifact_id,
        )
    assert missing.value.code == "benchmark.artifact.missing"
    closed_missing = publications.get_artifact(
        suite.experiment_id,
        missing_record.descriptor.artifact_id,
    )
    assert (
        closed_missing.descriptor.availability
        is StudioBenchmarkArtifactAvailability.MISSING
    )
    assert closed_missing.descriptor.content_type == ""
    assert closed_missing.descriptor.sha256 is None
    inventory = service.list_artifact_inventory(
        suite.experiment_id,
        limit=100,
    )
    missing_item = next(
        item
        for item in inventory.items
        if item.descriptor.artifact_id
        == missing_record.descriptor.artifact_id
    )
    assert missing_item.links.content is None

    record = publications.get_artifact(
        suite.experiment_id,
        publication.report_artifact_id,
    )
    artifacts.storage_path(record).write_bytes(b"tampered")
    with pytest.raises(StudioBenchmarkIntegrityError):
        artifacts.open_artifact(
            suite.experiment_id,
            publication.report_artifact_id,
        )
    closed = publications.get_artifact(
        suite.experiment_id,
        publication.report_artifact_id,
    )
    assert (
        closed.descriptor.availability
        is StudioBenchmarkArtifactAvailability.CORRUPT
    )
    assert closed.descriptor.sha256 is None
    closed_publication = publications.get_publication(suite.experiment_id)
    assert closed_publication is not None
    assert closed_publication.report_availability == "failed"
    assert closed_publication.report_artifact_id is None
    closed_experiment = repository.get_experiment(suite.experiment_id)
    assert closed_experiment.report_availability.value == "failed"
    closed_replay = build_default_replay_service(
        tmp_path / "studio.sqlite3"
    ).get_replay(publication.replay_id)
    assert closed_replay.integrity_state == "partial"
    assert any(
        item.artifact_id == publication.report_artifact_id
        and item.availability == "corrupt"
        for item in closed_replay.artifacts
    )


def test_publication_http_report_bundle_artifact_and_replay_links(
    tmp_path: Path,
) -> None:
    """Serve only committed scoped managed bytes through typed routes."""
    service, repository, suite, task = _ready_core_result(tmp_path)
    preparer, publications, artifacts, publisher = _publisher(
        tmp_path,
        repository,
    )
    preparer.prepare(
        suite,
        planned_task_run_id=task.task_run_id,
        definition_snapshot=repository.get_experiment(
            suite.experiment_id
        ).definition.model_dump(
            mode="json",
            by_alias=True,
            exclude_none=True,
        ),
        prepared_at=13,
    )
    publication = publisher.publish(
        suite.experiment_id,
        task.task_run_id,
        timestamp=14,
    )
    service._publication_enabled = True
    definitions = service.definitions
    authoring = StudioApplicationService(
        catalog=build_studio_component_catalog(),
        repository=definitions.agents,
    )
    composition = StudioBenchmarkComposition(
        service=definitions,
        catalog=definitions.catalog,
        profiles=definitions.profiles,
        experiments=service,
        repository=repository,
        publications=publications,
        artifacts=artifacts,
        publisher=publisher,
    )
    server = create_http_server(
        "127.0.0.1",
        0,
        application_service=authoring,
        benchmark_composition=composition,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    address = ("127.0.0.1", int(server.server_address[1]))

    def request(
        path: str,
        *,
        method: str = "GET",
        origin: str | None = None,
    ) -> tuple[int, dict[str, str], bytes]:
        """Issue one raw local HTTP request.

        Args:
            path: Public route.
            method: HTTP method.
            origin: Optional allowed browser Origin.

        Returns:
            Status, normalized headers, and body bytes.
        """
        connection = http.client.HTTPConnection(*address, timeout=5)
        headers = {"Host": "127.0.0.1"}
        if origin is not None:
            headers["Origin"] = origin
        connection.request(method, path, headers=headers)
        response = connection.getresponse()
        body = response.read()
        response_headers = {
            key.lower(): value for key, value in response.getheaders()
        }
        status = response.status
        connection.close()
        return status, response_headers, body

    try:
        status, headers, content = request(
            f"/studio/benchmark-experiments/{suite.experiment_id}/artifacts/"
            f"{publication.report_artifact_id}"
        )
        assert status == 200
        assert headers["content-type"] == "application/json"
        assert headers["content-length"] == str(len(content))
        assert headers["content-disposition"] == (
            f'attachment; filename="{publication.report_artifact_id}"'
        )
        assert headers["cache-control"] == "private, no-store"
        assert headers["x-content-type-options"] == "nosniff"
        assert json.loads(content)["experiment_id"] == suite.experiment_id
        head_status, head_headers, head_body = request(
            f"/studio/benchmark-experiments/{suite.experiment_id}/artifacts/"
            f"{publication.report_artifact_id}",
            method="HEAD",
            origin="http://127.0.0.1:5173",
        )
        assert head_status == 200
        assert head_body == b""
        assert head_headers["content-type"] == headers["content-type"]
        assert head_headers["content-length"] == headers["content-length"]
        assert head_headers["content-disposition"] == (
            headers["content-disposition"]
        )
        assert head_headers["access-control-allow-origin"] == (
            "http://127.0.0.1:5173"
        )
        assert "Content-Disposition" in (
            head_headers["access-control-expose-headers"]
        )

        task_record = next(
            record
            for record in publications.list_artifacts(
                suite.experiment_id,
                task_run_id=task.task_run_id,
            )
            if record.descriptor.availability in {
                StudioBenchmarkArtifactAvailability.AVAILABLE,
                StudioBenchmarkArtifactAvailability.REDACTED,
                StudioBenchmarkArtifactAvailability.TRUNCATED,
            }
        )
        status, headers, task_content = request(
            f"/studio/benchmark-experiments/{suite.experiment_id}"
            f"/task-runs/{task.task_run_id}/artifacts/"
            f"{task_record.descriptor.artifact_id}"
        )
        assert status == 200
        assert headers["content-type"] in {
            "application/json",
            "application/x-ndjson",
            "application/zip",
            "application/xml",
            "image/png",
            "text/plain",
        }
        assert headers["content-length"] == str(len(task_content))
        assert headers["content-disposition"] == (
            f'attachment; filename="{task_record.descriptor.artifact_id}"'
        )
        assert headers["cache-control"] == "private, no-store"
        assert headers["x-content-type-options"] == "nosniff"
        task_head_status, task_head_headers, task_head_body = request(
            f"/studio/benchmark-experiments/{suite.experiment_id}"
            f"/task-runs/{task.task_run_id}/artifacts/"
            f"{task_record.descriptor.artifact_id}",
            method="HEAD",
        )
        assert task_head_status == 200
        assert task_head_body == b""
        assert task_head_headers["content-type"] == headers["content-type"]
        assert task_head_headers["content-length"] == headers["content-length"]
        assert task_head_headers["content-disposition"] == (
            headers["content-disposition"]
        )

        status, headers, report = request(
            f"/studio/benchmark-experiments/{suite.experiment_id}/report"
        )
        assert status == 200
        assert headers["content-type"] == "application/json"
        assert headers["content-disposition"] == (
            f'attachment; filename="{suite.experiment_id}.report.json"'
        )
        assert json.loads(report)["experiment_id"] == suite.experiment_id
        report_head_status, report_head_headers, report_head_body = request(
            f"/studio/benchmark-experiments/{suite.experiment_id}/report",
            method="HEAD",
        )
        assert report_head_status == 200
        assert report_head_body == b""
        assert report_head_headers["content-type"] == headers["content-type"]
        assert report_head_headers["content-length"] == headers["content-length"]
        assert report_head_headers["content-disposition"] == (
            headers["content-disposition"]
        )
        status, headers, bundle = request(
            f"/studio/benchmark-experiments/{suite.experiment_id}/bundle"
        )
        assert status == 200
        assert headers["content-type"] == "application/zip"
        assert headers["content-disposition"] == (
            f'attachment; filename="{suite.experiment_id}.zip"'
        )
        assert bundle.startswith(b"PK")
        bundle_head_status, bundle_head_headers, bundle_head_body = request(
            f"/studio/benchmark-experiments/{suite.experiment_id}/bundle",
            method="HEAD",
        )
        assert bundle_head_status == 200
        assert bundle_head_body == b""
        assert bundle_head_headers["content-type"] == headers["content-type"]
        assert bundle_head_headers["content-length"] == headers["content-length"]
        assert bundle_head_headers["content-disposition"] == (
            headers["content-disposition"]
        )
        options_status, options_headers, options_body = request(
            f"/studio/benchmark-experiments/{suite.experiment_id}/bundle",
            method="OPTIONS",
            origin="http://127.0.0.1:5173",
        )
        assert options_status == 204
        assert options_body == b""
        assert "HEAD" in options_headers["access-control-allow-methods"]
        status, _headers, body = request(
            "/studio/benchmark-experiments/"
            f"experiment-{'f' * 32}/artifacts/"
            f"{publication.report_artifact_id}"
        )
        assert status == 404
        assert json.loads(body)["error"]["code"] == (
            "benchmark.artifact.not_found"
        )
        safe_error = body.decode("utf-8")
        assert str(tmp_path) not in safe_error
        assert task_record.storage_ref not in safe_error
        assert task_content[:16].hex() not in safe_error

        publications.update_artifact_availability(
            suite.experiment_id,
            task_record.descriptor.artifact_id,
            StudioBenchmarkArtifactAvailability.MISSING,
        )
        status, _headers, body = request(
            f"/studio/benchmark-experiments/{suite.experiment_id}"
            f"/task-runs/{task.task_run_id}/artifacts/"
            f"{task_record.descriptor.artifact_id}"
        )
        assert status == 404
        unreadable_error = json.loads(body)
        assert unreadable_error["error"]["code"] == (
            "benchmark.artifact.not_readable"
        )
        assert str(tmp_path) not in json.dumps(unreadable_error)

        status, _headers, body = request(
            f"/studio/benchmark-experiments/{suite.experiment_id}"
            "/artifacts/not-an-artifact"
        )
        assert status == 400
        assert json.loads(body)["error"]["code"] == (
            "benchmark.artifact.identifier_invalid"
        )
        status, _headers, body = request(
            f"/studio/benchmark-experiments/{suite.experiment_id}"
            f"/task-runs/task-run-{'f' * 32}/artifacts/"
            f"{next(record.descriptor.artifact_id for record in publications.list_artifacts(suite.experiment_id, task_run_id=task.task_run_id))}",
            method="HEAD",
        )
        assert status == 404
        assert body == b""
        status, _headers, body = request(
            f"/studio/benchmark-experiments/{suite.experiment_id}"
        )
        assert status == 200
        resource = json.loads(body)
        assert resource["capabilities"]["reports"] is True
        assert resource["links"]["report"].endswith("/report")
        assert resource["links"]["bundle"].endswith("/bundle")
        report_record = publications.get_artifact(
            suite.experiment_id,
            publication.report_artifact_id,
        )
        artifacts.storage_path(report_record).write_bytes(b"tampered")
        status, _headers, body = request(
            f"/studio/benchmark-experiments/{suite.experiment_id}/report",
            method="HEAD",
        )
        assert status == 409
        assert body == b""
        status, _headers, body = request(
            f"/studio/benchmark-experiments/{suite.experiment_id}"
        )
        assert status == 200
        resource = json.loads(body)
        assert resource["reportAvailability"] == "failed"
        assert "report" not in resource["links"]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
