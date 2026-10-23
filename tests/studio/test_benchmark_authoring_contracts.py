"""Exact-revision Studio Benchmark Contract Test service contracts."""

from __future__ import annotations

import random
from pathlib import Path
from typing import Any, Mapping

import pytest

from zhixing.benchmark.authoring import (
    BenchmarkContractTestCapacityError,
    BenchmarkFixtureDescriptor,
    BenchmarkFixtureKind,
    BenchmarkFixtureProfile,
    BenchmarkFixtureProfileRegistry,
    studio_fixture_profile_registry,
)
import zhixing.studio.benchmark_authoring_contracts as contract_module
from zhixing.studio.benchmark_authoring_contracts import (
    StudioBenchmarkContractTestApplicationService,
)
from zhixing.studio.benchmark_authoring_errors import (
    StudioBenchmarkAuthoringRevisionConflictError,
    StudioBenchmarkAuthoringCapacityError,
    StudioBenchmarkAuthoringNotFoundError,
    StudioBenchmarkAuthoringStorageError,
    StudioBenchmarkAuthoringValidationError,
)

from .test_benchmark_authoring_analysis import _analysis_fixture


def _service(tmp_path: Path) -> tuple[dict[str, object], StudioBenchmarkContractTestApplicationService]:
    """Build a real authoring fixture and trusted Contract Test service.

    Args:
        tmp_path: Pytest persistence root.

    Raises:
        OSError: Local test persistence cannot be prepared.

    Returns:
        Shared authoring fixture and Contract Test service.
    """
    fixture = _analysis_fixture(tmp_path)
    analysis = fixture["analysis"]
    return fixture, StudioBenchmarkContractTestApplicationService(
        compiler=analysis._compiler,  # type: ignore[union-attr]
        profiles=studio_fixture_profile_registry(),
    )


def _request(revision_id: str, *, profile_id: str = "studio-safe-v1") -> dict[str, object]:
    """Build one strict exact-revision Contract Test command.

    Args:
        revision_id: Exact current immutable revision identity.
        profile_id: Explicit server-owned fixture profile identity.

    Returns:
        JSON-compatible strict command.
    """
    return {
        "schemaVersion": 1,
        "revisionId": revision_id,
        "split": "test",
        "seed": 19,
        "fixtureProfileId": profile_id,
    }


def _constant_fixture(value: Any):
    """Create a fresh constant fake-fixture factory for service tests.

    Args:
        value: Controlled fixture output.

    Returns:
        Factory producing fresh deterministic fixture callables.
    """
    def factory():
        """Create one fresh deterministic fake fixture.

        Returns:
            Fresh fake-fixture callable.
        """
        def runner(
            params: Mapping[str, Any],
            rng: random.Random,
        ) -> Any:
            """Return the configured controlled value.

            Args:
                params: Safe copied definition parameters.
                rng: Case-local deterministic random source.

            Returns:
                Configured fixture output.
            """
            del params, rng
            return value

        return runner

    return factory


def _profile_service(
    fixture: Mapping[str, object],
    profile: BenchmarkFixtureProfile,
) -> StudioBenchmarkContractTestApplicationService:
    """Build a Contract Test service around one injected test profile.

    Args:
        fixture: Shared exact-revision analysis fixture.
        profile: Trusted test-only fake fixture profile.

    Returns:
        Contract Test application service using the shared compiler.
    """
    analysis = fixture["analysis"]
    return StudioBenchmarkContractTestApplicationService(
        compiler=analysis._compiler,  # type: ignore[union-attr]
        profiles=BenchmarkFixtureProfileRegistry((profile,)),
    )


def test_contract_test_profiles_are_metadata_only_and_stable(tmp_path: Path) -> None:
    """Expose reviewed profile facts without factories or module locations."""
    _, service = _service(tmp_path)
    payload = service.list_profiles().model_dump(mode="json", by_alias=True)
    assert payload["schemaVersion"] == 1
    assert payload["profiles"][0]["profileId"] == "studio-safe-v1"
    encoded = str(payload)
    assert "factory" not in encoded
    assert "callable" not in encoded
    assert "/Users/" not in encoded


def test_contract_test_runs_exact_revision_without_durable_mutation(tmp_path: Path) -> None:
    """Return bounded fake facts while keeping current revision unchanged."""
    fixture, service = _service(tmp_path)
    draft = fixture["draft"]
    revision = fixture["revision"]
    repository = fixture["repository"]
    request = service.parse_request(_request(revision.revision_id))  # type: ignore[union-attr]
    before = repository.get_draft(draft.draft_id)  # type: ignore[union-attr]
    result = service.run(draft.draft_id, request)  # type: ignore[union-attr]
    after = repository.get_draft(draft.draft_id)  # type: ignore[union-attr]

    assert result.revision_id == revision.revision_id  # type: ignore[union-attr]
    assert result.valid_definition is True
    assert result.coverage.total == len(result.cases)
    assert result.coverage.failed == 0
    assert result.safety.fixture_execution is True
    assert result.safety.package_code_executed is False
    assert result.safety.real_device_evidence is False
    assert result.safety.process_sandbox is False
    assert result.safety.experiment_capability is False
    assert result.safety.output_path_capability is False
    assert before == after


def test_contract_test_distinguishes_skipped_and_failed_coverage(
    tmp_path: Path,
) -> None:
    """Keep unavailable coverage separate from executed fixture failure."""
    fixture = _analysis_fixture(tmp_path)
    draft = fixture["draft"]
    revision = fixture["revision"]
    empty = BenchmarkFixtureProfile(
        profile_id="tests-empty",
        version="1.0.0",
        title="Empty",
        description="No registered logical fixture.",
        evidence_level="fake-contract",
        fixtures=(
            BenchmarkFixtureDescriptor(
                BenchmarkFixtureKind.INITIALIZER,
                "random_choice",
                "tests.unused-initializer",
                "1.0.0",
                _constant_fixture({"value": "unused"}),
            ),
        ),
    )
    skipped_service = _profile_service(fixture, empty)
    skipped = skipped_service.run(
        draft.draft_id,  # type: ignore[union-attr]
        skipped_service.parse_request(
            _request(revision.revision_id, profile_id="tests-empty")  # type: ignore[union-attr]
        ),
    )
    assert skipped.coverage.skipped == 1
    assert skipped.coverage.failed == 0
    assert skipped.coverage.complete is False
    assert skipped.coverage.executed_checks_passed is True

    failing = BenchmarkFixtureProfile(
        profile_id="tests-failing",
        version="1.0.0",
        title="Failing",
        description="Produces controlled unsafe evidence.",
        evidence_level="fake-contract",
        fixtures=(
            BenchmarkFixtureDescriptor(
                BenchmarkFixtureKind.EVALUATOR,
                "file_exist",
                "tests.file-exist-failure",
                "1.0.0",
                _constant_fixture({"api_key": "must-not-leak"}),
            ),
        ),
    )
    failing_service = _profile_service(fixture, failing)
    failed = failing_service.run(
        draft.draft_id,  # type: ignore[union-attr]
        failing_service.parse_request(
            _request(revision.revision_id, profile_id="tests-failing")  # type: ignore[union-attr]
        ),
    )
    assert failed.coverage.failed == 1
    assert failed.coverage.skipped == 0
    assert failed.coverage.complete is True
    assert failed.coverage.executed_checks_passed is False
    assert "must-not-leak" not in str(
        failed.model_dump(mode="json", by_alias=True)
    )


def test_invalid_definition_returns_zero_cases_without_fixture_work(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Treat compile diagnostics as preconditions and invoke no fake fixture."""
    fixture, service = _service(tmp_path)
    draft = fixture["draft"]
    revision = fixture["revision"]
    authoring = fixture["authoring"]
    document = revision.document.model_dump(  # type: ignore[union-attr]
        mode="json", by_alias=True
    )
    document["taskFiles"][0]["tasks"][0]["max_steps"] = 0
    saved = authoring.save_revision(  # type: ignore[union-attr]
        draft.draft_id,  # type: ignore[union-attr]
        {
            "schemaVersion": 1,
            "clientRequestId": "contract-invalid-task",
            "baseRevisionId": revision.revision_id,  # type: ignore[union-attr]
            "document": document,
        },
    )

    def forbidden_runner(*args: object, **kwargs: object) -> object:
        """Fail if an invalid definition reaches fixture execution.

        Args:
            args: Unexpected runner inputs.
            kwargs: Unexpected runner keyword inputs.

        Raises:
            AssertionError: Always.
        """
        raise AssertionError((args, kwargs))

    monkeypatch.setattr(contract_module, "run_benchmark_contract_tests", forbidden_runner)
    result = service.run(
        draft.draft_id,  # type: ignore[union-attr]
        service.parse_request(_request(saved.revision.revision_id)),
    )
    assert result.valid_definition is False
    assert result.coverage.total == 0
    assert result.cases == ()
    assert result.precondition_diagnostics


@pytest.mark.parametrize(
    "extra",
    (
        {"module": "malicious.fixture"},
        {"deviceProfileId": "android"},
        {"credential": "secret"},
        {"destination": "/tmp/output"},
    ),
)
def test_contract_test_request_rejects_execution_fields(
    tmp_path: Path,
    extra: dict[str, object],
) -> None:
    """Reject author-controlled executable or runtime capability fields."""
    fixture, service = _service(tmp_path)
    revision = fixture["revision"]
    payload = _request(revision.revision_id)  # type: ignore[union-attr]
    payload.update(extra)
    with pytest.raises(StudioBenchmarkAuthoringValidationError):
        service.parse_request(payload)


def test_unavailable_profile_fails_before_revision_compilation(tmp_path: Path) -> None:
    """Do not guess a profile or enter private staging when selection fails."""
    fixture, service = _service(tmp_path)
    revision = fixture["revision"]
    compiler = service._compiler
    called = False
    original = compiler.compile

    def forbidden_compile(*args, **kwargs):
        """Fail if unavailable-profile handling reaches compilation.

        Args:
            args: Unexpected positional compilation arguments.
            kwargs: Unexpected keyword compilation arguments.

        Raises:
            AssertionError: Always, because compilation is forbidden.
        """
        nonlocal called
        called = True
        raise AssertionError((args, kwargs))

    compiler.compile = forbidden_compile  # type: ignore[method-assign]
    try:
        request = service.parse_request(
            _request(revision.revision_id, profile_id="absent")  # type: ignore[union-attr]
        )
        with pytest.raises(StudioBenchmarkAuthoringValidationError):
            service.run(fixture["draft"].draft_id, request)  # type: ignore[union-attr]
    finally:
        compiler.compile = original  # type: ignore[method-assign]
    assert called is False


def test_contract_test_hides_foreign_and_rejects_pre_stale_revision(
    tmp_path: Path,
) -> None:
    """Reuse exact-current ownership checks before any fixture invocation."""
    fixture, service = _service(tmp_path)
    authoring = fixture["authoring"]
    draft = fixture["draft"]
    revision = fixture["revision"]
    foreign = authoring.create_draft(  # type: ignore[union-attr]
        {
            "schemaVersion": 1,
            "clientRequestId": "contract-foreign",
            "name": "Foreign Contract Draft",
            "source": {
                "kind": "template",
                "template": "minimal",
                "publisher": "tests",
                "packageName": "contract-foreign",
                "version": "0.1.0",
            },
        }
    )
    request = service.parse_request(_request(revision.revision_id))  # type: ignore[union-attr]
    with pytest.raises(StudioBenchmarkAuthoringNotFoundError):
        service.run(foreign.draft.draft_id, request)

    authoring.save_revision(  # type: ignore[union-attr]
        draft.draft_id,  # type: ignore[union-attr]
        {
            "schemaVersion": 1,
            "clientRequestId": "contract-advance-current",
            "baseRevisionId": revision.revision_id,  # type: ignore[union-attr]
            "document": revision.document.model_dump(  # type: ignore[union-attr]
                mode="json", by_alias=True
            ),
        },
    )
    with pytest.raises(StudioBenchmarkAuthoringRevisionConflictError):
        service.run(draft.draft_id, request)  # type: ignore[union-attr]


def test_contract_test_maps_capacity_and_private_compiler_failures(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Return no partial result for capacity or private staging failure."""
    fixture, service = _service(tmp_path)
    draft = fixture["draft"]
    revision = fixture["revision"]
    request = service.parse_request(_request(revision.revision_id))  # type: ignore[union-attr]

    def too_large(*args: object, **kwargs: object) -> object:
        """Simulate Core pre-execution capacity rejection.

        Args:
            args: Ignored Core runner inputs.
            kwargs: Ignored Core runner keyword inputs.

        Raises:
            BenchmarkContractTestCapacityError: Always.
        """
        del args, kwargs
        raise BenchmarkContractTestCapacityError("too large")

    monkeypatch.setattr(contract_module, "run_benchmark_contract_tests", too_large)
    with pytest.raises(StudioBenchmarkAuthoringCapacityError):
        service.run(draft.draft_id, request)  # type: ignore[union-attr]

    def unavailable(*args: object, **kwargs: object) -> object:
        """Simulate safe private materializer or cleanup unavailability.

        Args:
            args: Ignored compiler inputs.
            kwargs: Ignored compiler keyword inputs.

        Raises:
            StudioBenchmarkAuthoringStorageError: Always.
        """
        del args, kwargs
        raise StudioBenchmarkAuthoringStorageError(
            "benchmark.authoring.analysis_unavailable",
            "Private analysis is unavailable",
        )

    monkeypatch.setattr(service._compiler, "compile", unavailable)
    with pytest.raises(StudioBenchmarkAuthoringStorageError):
        service.run(draft.draft_id, request)  # type: ignore[union-attr]


def test_contract_test_rechecks_current_pointer_after_fixture_work(tmp_path: Path) -> None:
    """Discard result authority when the draft advances during the command."""
    fixture, service = _service(tmp_path)
    draft = fixture["draft"]
    revision = fixture["revision"]
    compiler = service._compiler
    original = compiler.assert_still_current

    def stale(*args, **kwargs):
        """Simulate a late durable current-pointer race.

        Args:
            args: Shared current-check arguments.
            kwargs: Shared current-check keyword arguments.

        Raises:
            StudioBenchmarkAuthoringRevisionConflictError: Always.
        """
        del args, kwargs
        raise StudioBenchmarkAuthoringRevisionConflictError(
            "benchmark.authoring.analysis_revision_stale",
            "Benchmark analysis requires the current draft revision",
            current_revision_id="benchmark-revision-later",
        )

    compiler.assert_still_current = stale  # type: ignore[method-assign]
    try:
        request = service.parse_request(_request(revision.revision_id))  # type: ignore[union-attr]
        with pytest.raises(StudioBenchmarkAuthoringRevisionConflictError):
            service.run(draft.draft_id, request)  # type: ignore[union-attr]
    finally:
        compiler.assert_still_current = original  # type: ignore[method-assign]
