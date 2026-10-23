"""Real HTTP contracts for the Studio Benchmark Catalog and Composer."""

from __future__ import annotations

import http.client
import json
import shutil
import threading
from collections.abc import Iterator
from dataclasses import replace
from io import BytesIO
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import pytest

from zhixing.benchmark.authoring import studio_fixture_profile_registry

from zhixing.studio import (
    SQLiteAgentDocumentRepository,
    StudioApplicationService,
    build_studio_component_catalog,
)
from zhixing.studio.benchmark_composition import StudioBenchmarkComposition
from zhixing.studio.benchmark_errors import StudioBenchmarkValidationError
from zhixing.studio.benchmark_authoring_content import (
    StudioBenchmarkAuthoringContentApplicationService,
)
from zhixing.studio.benchmark_authoring_analysis import (
    StudioBenchmarkValidationDryRunApplicationService,
)
from zhixing.studio.benchmark_authoring_analysis_models import (
    StudioBenchmarkAuthoringDiagnosticV1,
)
from zhixing.studio.benchmark_authoring_contracts import (
    StudioBenchmarkContractTestApplicationService,
)
from zhixing.studio.benchmark_authoring_freeze import (
    StudioBenchmarkFrozenClosureBuilder,
)
from zhixing.studio.benchmark_authoring_freeze_service import (
    StudioBenchmarkValidatedFreezeAnalyzer,
    StudioBenchmarkValidatedFreezeApplicationService,
)
from zhixing.studio.benchmark_authoring_errors import (
    StudioBenchmarkAuthoringCapacityError,
    StudioBenchmarkAuthoringFreezeEligibilityError,
    StudioBenchmarkAuthoringIdempotencyConflictError,
    StudioBenchmarkAuthoringNotFoundError,
    StudioBenchmarkAuthoringRevisionConflictError,
    StudioBenchmarkAuthoringStorageError,
)
from zhixing.studio.benchmark_authoring_import import (
    StudioBenchmarkAuthoringPackageAdapter,
)
from zhixing.studio.benchmark_authoring_materializer import (
    StudioBenchmarkAuthoringPackageMaterializer,
)
from zhixing.studio.benchmark_authoring_migration import (
    StudioBenchmarkLegacyMigrationApplicationService,
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
from zhixing.studio.benchmark_authoring_release_service import (
    StudioBenchmarkPackageReleaseApplicationService,
)
from zhixing.studio.benchmark_authoring_release_storage import (
    LocalStudioBenchmarkPackageReleaseStore,
    StudioBenchmarkFrozenClosureReader,
    default_studio_benchmark_release_root,
)
from zhixing.studio.benchmark_service import (
    StudioBenchmarkApplicationService,
    StudioBenchmarkCatalogService,
    StudioBenchmarkCatalogSnapshotOwner,
    StudioBenchmarkSource,
)
from zhixing.studio.httpd import _ExactContentLengthStream, create_http_server
from zhixing.studio.run_execution import (
    AndroidDeviceProfile,
    AndroidDeviceProfileResolver,
)
from zhixing.studio.flow_template_loader import get_flow_template_document

from .benchmark_fixtures import write_studio_benchmark_package
from .test_benchmark_composer import NoResolveProfileResolver, _preview_payload


@pytest.fixture
def benchmark_http_server(tmp_path: Path) -> Iterator[dict[str, Any]]:
    """Run one complete definition-only Benchmark HTTP composition.

    Args:
        tmp_path: Pytest temporary directory.

    Raises:
        OSError: Fixture files, SQLite, or the loopback socket cannot be used.

    Yields:
        Address and selected public resource identities.
    """
    root = tmp_path / "benchmarks"
    first = write_studio_benchmark_package(root / "first", name="alpha")
    write_studio_benchmark_package(root / "second", name="beta")
    write_studio_benchmark_package(
        root / "invalid",
        name="invalid",
        invalid_tasks=True,
    )
    duplicate = root / "alpha-divergent"
    shutil.copytree(first, duplicate)
    task_path = duplicate / "tasks" / "test.json"
    tasks = json.loads(task_path.read_text(encoding="utf-8"))
    tasks[0]["instruction"] = "Divergent Alpha task"
    task_path.write_text(json.dumps(tasks), encoding="utf-8")

    catalog = StudioBenchmarkCatalogSnapshotOwner(
        StudioBenchmarkCatalogService(
            (StudioBenchmarkSource("fixture-root", "catalog_root", root),)
        )
    )
    agents = SQLiteAgentDocumentRepository(tmp_path / "studio.sqlite3")
    component_catalog = build_studio_component_catalog()
    authoring = StudioApplicationService(
        catalog=component_catalog,
        repository=agents,
    )
    agent, revision = authoring.create_agent(
        "Benchmark HTTP Agent",
        initial_document=get_flow_template_document("modular_baseline"),
    )
    profiles = NoResolveProfileResolver(
        {
            "local-android": AndroidDeviceProfile(
                "local-android",
                serial="/private/serial-must-not-leak",
                label="Local Android",
            )
        }
    )
    benchmark_service = StudioBenchmarkApplicationService(
        catalog=catalog,
        agents=agents,
        profiles=profiles,
        contract_catalog=component_catalog.node_contract_catalog(),
    )
    authoring_repository = SQLiteStudioBenchmarkAuthoringRepository(
        tmp_path / "studio.sqlite3"
    )
    authoring_content = LocalStudioBenchmarkManagedContent(
        default_studio_benchmark_authoring_root(
            authoring_repository.database_path
        )
    )
    benchmark_authoring = StudioBenchmarkAuthoringApplicationService(
        repository=authoring_repository,
        packages=StudioBenchmarkAuthoringPackageAdapter(
            authoring_content,
            staging_root=authoring_content.staging_root,
        ),
        catalog=catalog,
    )
    benchmark_authoring_content = (
        StudioBenchmarkAuthoringContentApplicationService(
            repository=authoring_repository,
            content=authoring_content,
        )
    )
    benchmark_authoring_analysis = (
        StudioBenchmarkValidationDryRunApplicationService(
            repository=authoring_repository,
            materializer=StudioBenchmarkAuthoringPackageMaterializer(
                authoring_content,
                staging_root=authoring_content.staging_root / "analysis",
            ),
            agents=agents,
            contract_catalog=component_catalog.node_contract_catalog(),
        )
    )
    benchmark_authoring_contract_tests = (
        StudioBenchmarkContractTestApplicationService(
            compiler=benchmark_authoring_analysis._compiler,
            profiles=studio_fixture_profile_registry(),
        )
    )
    benchmark_authoring_freeze = (
        StudioBenchmarkValidatedFreezeApplicationService(
            repository=authoring_repository,
            analyzer=StudioBenchmarkValidatedFreezeAnalyzer(
                benchmark_authoring_analysis._compiler
            ),
            closure_builder=StudioBenchmarkFrozenClosureBuilder(
                authoring_content
            ),
        )
    )
    benchmark_authoring_release = (
        StudioBenchmarkPackageReleaseApplicationService(
            repository=authoring_repository,
            frozen_reader=StudioBenchmarkFrozenClosureReader(
                authoring_content
            ),
            storage=LocalStudioBenchmarkPackageReleaseStore(
                default_studio_benchmark_release_root(
                    authoring_repository.database_path
                )
            ),
            catalog=catalog,
        )
    )
    benchmark_authoring_release.recover_publications()
    benchmark_authoring_migration = (
        StudioBenchmarkLegacyMigrationApplicationService(
            repository=authoring_repository
        )
    )
    composition = StudioBenchmarkComposition(
        service=benchmark_service,
        catalog=catalog,
        profiles=profiles,
        authoring=benchmark_authoring,
        authoring_content_service=benchmark_authoring_content,
        authoring_repository=authoring_repository,
        authoring_content=authoring_content,
        authoring_analysis=benchmark_authoring_analysis,
        authoring_contract_tests=benchmark_authoring_contract_tests,
        authoring_freeze=benchmark_authoring_freeze,
        authoring_release=benchmark_authoring_release,
        authoring_migration=benchmark_authoring_migration,
    )
    selected = next(
        item
        for item in catalog.list_entries().items
        if item.package_identity == "tests/beta@1.0.0"
    )
    task = catalog.list_tasks(
        selected.catalog_entry_id,
        split="test",
    ).items[0]
    server = create_http_server(
        "127.0.0.1",
        0,
        application_service=authoring,
        benchmark_composition=composition,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield {
            "address": ("127.0.0.1", int(server.server_address[1])),
            "entryId": selected.catalog_entry_id,
            "taskId": task.task_id,
            "agentId": agent.agent_id,
            "revisionId": revision.revision_id,
            "tmpPath": str(tmp_path),
            "contractTests": benchmark_authoring_contract_tests,
            "freeze": benchmark_authoring_freeze,
            "applicationService": authoring,
            "composition": composition,
        }
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


def test_legacy_migration_http_preview_confirm_retry_and_private_headers(
    benchmark_http_server: dict[str, Any],
) -> None:
    """Preview, Confirm, and exactly replay one migration over real HTTP.

    Args:
        benchmark_http_server: Complete loopback Studio fixture.

    Raises:
        OSError: Local HTTP transport fails.

    Returns:
        None.
    """
    address = benchmark_http_server["address"]
    payload = _legacy_migration_payload()
    status, raw_preview, preview_headers = _binary_request(
        address,
        "POST",
        "/studio/benchmark-authoring/legacy-migrations/preview",
        body=json.dumps(payload).encode("utf-8"),
        content_type="application/json",
        origin="http://127.0.0.1:5173",
    )
    preview = json.loads(raw_preview)
    assert status == 200
    assert preview["confirmable"] is True
    assert preview_headers["cache-control"] == "private, no-store"
    assert preview_headers["access-control-allow-origin"] == (
        "http://127.0.0.1:5173"
    )
    assert "sourceText" not in raw_preview.decode("utf-8")

    confirm = {
        **payload,
        "clientRequestId": "http-legacy-confirm",
        "previewFingerprint": preview["previewFingerprint"],
        "migrationContractIdentity": preview["migrationContractIdentity"],
    }
    status, created = _request(
        address,
        "POST",
        "/studio/benchmark-authoring/legacy-migrations/confirm",
        confirm,
    )
    assert status == 201
    assert created["created"] is True
    assert created["revision"]["provenance"]["sourceKind"] == (
        "legacy_migration"
    )
    assert created["revision"]["status"] == "unvalidated"
    assert all(value is False for value in created["evidence"].values())

    status, replayed = _request(
        address,
        "POST",
        "/studio/benchmark-authoring/legacy-migrations/confirm",
        confirm,
    )
    assert status == 200
    assert replayed["created"] is False
    assert replayed["draft"]["draftId"] == created["draft"]["draftId"]


def test_legacy_migration_http_rejects_duplicates_stale_and_malformed_input(
    benchmark_http_server: dict[str, Any],
) -> None:
    """Fail closed on non-confirmable, stale, oversized, and invalid routes.

    Args:
        benchmark_http_server: Complete loopback Studio fixture.

    Raises:
        OSError: Local HTTP transport fails.

    Returns:
        None.
    """
    address = benchmark_http_server["address"]
    one_task = json.loads(_legacy_migration_payload()["sourceText"])[0]
    duplicate_payload = _legacy_migration_payload([one_task, one_task])
    status, duplicate = _request(
        address,
        "POST",
        "/studio/benchmark-authoring/legacy-migrations/preview",
        duplicate_payload,
    )
    assert status == 200
    assert duplicate["confirmable"] is False
    assert duplicate.get("previewFingerprint") is None
    assert any(
        item["code"] == "benchmark.migration.task_id_duplicate"
        for item in duplicate["diagnostics"]
    )

    valid_payload = _legacy_migration_payload()
    status, preview = _request(
        address,
        "POST",
        "/studio/benchmark-authoring/legacy-migrations/preview",
        valid_payload,
    )
    assert status == 200
    stale = {
        **valid_payload,
        "clientRequestId": "http-legacy-stale",
        "previewFingerprint": preview["previewFingerprint"],
        "migrationContractIdentity": preview["migrationContractIdentity"],
    }
    stale["target"] = {**stale["target"], "split": "dev"}
    status, conflict = _request(
        address,
        "POST",
        "/studio/benchmark-authoring/legacy-migrations/confirm",
        stale,
    )
    assert status == 409
    assert "sourceText" not in json.dumps(conflict)

    invalid = {**valid_payload, "hostPath": benchmark_http_server["tmpPath"]}
    status, error = _request(
        address,
        "POST",
        "/studio/benchmark-authoring/legacy-migrations/preview",
        invalid,
    )
    assert status == 400
    assert benchmark_http_server["tmpPath"] not in json.dumps(error)
    status, _ = _request(
        address,
        "GET",
        "/studio/benchmark-authoring/legacy-migrations/preview",
    )
    assert status == 405
    status, _ = _request(
        address,
        "POST",
        "/studio/benchmark-authoring/legacy-migrations/preview?path=nope",
        valid_payload,
    )
    assert status == 400

    oversized = {**valid_payload, "sourceText": "x" * (1024 * 1024 + 1)}
    status, oversized_error = _request(
        address,
        "POST",
        "/studio/benchmark-authoring/legacy-migrations/preview",
        oversized,
    )
    assert status == 413
    assert "x" * 100 not in json.dumps(oversized_error)


def test_legacy_migration_http_rejects_untrusted_host_without_cors_echo(
    benchmark_http_server: dict[str, Any],
) -> None:
    """Keep the migration commands behind the shared Host/Origin boundary.

    Args:
        benchmark_http_server: Complete loopback Studio fixture.

    Raises:
        OSError: Local HTTP transport fails.

    Returns:
        None.
    """
    address = benchmark_http_server["address"]
    connection = http.client.HTTPConnection(*address, timeout=5)
    body = json.dumps(_legacy_migration_payload()).encode("utf-8")
    try:
        connection.putrequest(
            "POST",
            "/studio/benchmark-authoring/legacy-migrations/preview",
            skip_host=True,
        )
        connection.putheader("Host", "attacker.example")
        connection.putheader("Origin", "https://attacker.example")
        connection.putheader("Content-Type", "application/json")
        connection.putheader("Content-Length", str(len(body)))
        connection.endheaders(body)
        response = connection.getresponse()
        headers = {key.lower(): value for key, value in response.getheaders()}
        assert response.status == 403
        assert "access-control-allow-origin" not in headers
        assert benchmark_http_server["tmpPath"] not in (
            response.read().decode("utf-8")
        )
    finally:
        connection.close()


def _request(
    address: tuple[str, int],
    method: str,
    path: str,
    payload: object | None = None,
    *,
    origin: str | None = None,
) -> tuple[int, dict[str, Any]]:
    """Send one bounded JSON request to the local fixture server.

    Args:
        address: Host and port.
        method: HTTP method.
        path: Public API path and query.
        payload: Optional JSON-compatible body.
        origin: Optional browser Origin header.

    Raises:
        OSError: HTTP transport fails.
        json.JSONDecodeError: Response is not JSON.

    Returns:
        HTTP status and decoded object.
    """
    connection = http.client.HTTPConnection(*address, timeout=5)
    headers = {"Accept": "application/json"}
    body = None
    if payload is not None:
        body = json.dumps(payload)
        headers["Content-Type"] = "application/json"
    if origin is not None:
        headers["Origin"] = origin
    try:
        connection.request(method, path, body=body, headers=headers)
        response = connection.getresponse()
        return response.status, json.loads(response.read().decode("utf-8"))
    finally:
        connection.close()


def _binary_request(
    address: tuple[str, int],
    method: str,
    path: str,
    *,
    body: bytes | None = None,
    content_type: str | None = None,
    origin: str | None = None,
) -> tuple[int, bytes, dict[str, str]]:
    """Send one raw-body request and retain exact response headers.

    Args:
        address: Host and port.
        method: HTTP method.
        path: Public API path and query.
        body: Optional exact binary body.
        content_type: Optional declared request media type.
        origin: Optional browser Origin header.

    Raises:
        OSError: HTTP transport fails.

    Returns:
        Status, raw response bytes, and case-insensitive header mapping.
    """
    connection = http.client.HTTPConnection(*address, timeout=10)
    headers: dict[str, str] = {}
    if content_type is not None:
        headers["Content-Type"] = content_type
    if origin is not None:
        headers["Origin"] = origin
    try:
        connection.request(method, path, body=body, headers=headers)
        response = connection.getresponse()
        return (
            response.status,
            response.read(),
            {key.lower(): value for key, value in response.getheaders()},
        )
    finally:
        connection.close()


def _legacy_migration_payload(
    tasks: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build one complete local legacy migration Preview payload.

    Args:
        tasks: Optional standalone BenchmarkTask V1 mappings.

    Raises:
        None.

    Returns:
        JSON-compatible strict Preview request.
    """
    task = {
        "id": "http-legacy-task",
        "instruction": "Complete the task",
        "type": "static",
        "task_initializer": {},
        "environment_initializer": [],
        "cleanup_initializer": [],
        "evaluator": {
            "name": "system_state",
            "params": {
                "method": "file_exist",
                "file_path": "/sdcard/result.txt",
            },
        },
        "app": "clock",
        "requires_login": False,
    }
    return {
        "schemaVersion": 1,
        "sourceName": "legacy.json",
        "sourceText": json.dumps(tasks or [task]),
        "target": {
            "draftName": "Imported HTTP legacy suite",
            "publisher": "tests",
            "packageName": "http-legacy-suite",
            "version": "0.1.0",
            "title": "Imported HTTP legacy suite",
            "platform": "android",
            "split": "test",
            "taskFilePath": "tasks/imported.json",
        },
    }


def test_exact_content_length_stream_rejects_short_and_overlong_sources() -> None:
    """Enforce the declared raw-body boundary without buffering the upload."""
    short = _ExactContentLengthStream(BytesIO(b"ab"), 3)
    assert short.read(3) == b"ab"
    with pytest.raises(StudioBenchmarkValidationError) as short_failure:
        short.read(1)
    assert getattr(short_failure.value, "code", None) == (
        "benchmark.authoring.content_length_mismatch"
    )

    class OverlongStream:
        """Return more bytes than the wrapper asks for."""

        def read(self, size: int = -1) -> bytes:
            """Return one deliberately overlong block.

            Args:
                size: Requested maximum byte count.

            Raises:
                None.

            Returns:
                A byte block one byte longer than requested.
            """
            return b"x" * (size + 1)

    overlong = _ExactContentLengthStream(OverlongStream(), 2)
    with pytest.raises(StudioBenchmarkValidationError) as overlong_failure:
        overlong.read(2)
    assert getattr(overlong_failure.value, "code", None) == (
        "benchmark.authoring.content_length_mismatch"
    )
    assert _ExactContentLengthStream(BytesIO(b""), 0).read() == b""
    with pytest.raises(ValueError):
        _ExactContentLengthStream(BytesIO(b""), -1)


def test_catalog_detail_tasks_validation_and_navigation_http(
    benchmark_http_server: dict[str, Any],
) -> None:
    """Traverse the complete Catalog definition HTTP surface."""
    address = benchmark_http_server["address"]
    status, first_page = _request(
        address,
        "GET",
        "/studio/benchmarks?limit=1&platform=android&sourceKind=catalog",
        origin="http://127.0.0.1:5173",
    )
    assert status == 200
    assert len(first_page["items"]) == 1
    assert first_page["nextCursor"]
    status, second_page = _request(
        address,
        "GET",
        "/studio/benchmarks?limit=1&platform=android"
        f"&sourceKind=catalog&cursor={first_page['nextCursor']}",
    )
    assert status == 200
    assert len(second_page["items"]) == 1

    status, ambiguous = _request(
        address,
        "GET",
        "/studio/benchmarks?query=alpha",
    )
    assert status == 200
    assert len(ambiguous["items"]) == 2
    assert all(
        any(
            warning["code"] == "benchmark.catalog.identity_ambiguous"
            for warning in item["warnings"]
        )
        for item in ambiguous["items"]
    )

    entry_id = benchmark_http_server["entryId"]
    status, detail = _request(
        address,
        "GET",
        f"/studio/benchmarks/{entry_id}",
    )
    assert status == 200
    assert detail["catalogEntryId"] == entry_id
    status, tasks = _request(
        address,
        "GET",
        f"/studio/benchmarks/{entry_id}/tasks?split=test&limit=1",
    )
    assert status == 200
    assert tasks["items"][0]["taskId"] == benchmark_http_server["taskId"]
    status, validation = _request(
        address,
        "POST",
        f"/studio/benchmarks/{entry_id}/validate",
        {"schemaVersion": 1, "split": "test"},
    )
    assert status == 200
    assert validation["valid"] is True

    status, profiles = _request(address, "GET", "/studio/device-profiles")
    assert status == 200
    serialized = json.dumps(profiles)
    assert profiles["items"][0]["deviceProfileId"] == "local-android"
    assert "serial" not in serialized
    assert "/private/" not in serialized
    status, navigation = _request(address, "GET", "/studio/nav-modules")
    assert status == 200
    benchmark_module = next(
        item for item in navigation["modules"] if item["id"] == "benchmark"
    )
    assert benchmark_module["path"] == "/benchmarks"


def test_preview_http_is_deterministic_strict_and_path_safe(
    benchmark_http_server: dict[str, Any],
) -> None:
    """Preview without persistence/device resolution and return safe errors."""
    payload = _preview_payload(
        benchmark_http_server["entryId"],
        benchmark_http_server["taskId"],
        benchmark_http_server["agentId"],
        benchmark_http_server["revisionId"],
    )
    status, first = _request(
        benchmark_http_server["address"],
        "POST",
        "/studio/benchmark-experiments/preview",
        payload,
    )
    assert status == 200
    assert first["previewOnly"] is True
    assert first["executionLimits"]["maxAgents"] == 1
    status, second = _request(
        benchmark_http_server["address"],
        "POST",
        "/studio/benchmark-experiments/preview",
        json.loads(json.dumps(payload, sort_keys=True)),
    )
    assert status == 200
    assert second["previewFingerprint"] == first["previewFingerprint"]
    assert second["schedule"] == first["schedule"]
    serialized = json.dumps(first)
    assert "experimentId" not in serialized
    assert "taskRunId" not in serialized
    assert benchmark_http_server["tmpPath"] not in serialized

    malformed = dict(payload)
    malformed["hostPath"] = benchmark_http_server["tmpPath"]
    status, error = _request(
        benchmark_http_server["address"],
        "POST",
        "/studio/benchmark-experiments/preview",
        malformed,
    )
    assert status == 400
    assert error["error"]["code"] == "benchmark.preview.request_invalid"
    assert benchmark_http_server["tmpPath"] not in json.dumps(error)


def test_device_profile_http_is_static_empty_safe_and_preview_only(
    benchmark_http_server: dict[str, Any],
) -> None:
    """Keep configured metadata static and no-config HTTP device-free.

    Args:
        benchmark_http_server: Complete loopback Studio fixture.

    Raises:
        OSError: The temporary loopback server cannot be used.

    Returns:
        None.
    """
    address = benchmark_http_server["address"]
    status, configured = _request(address, "GET", "/studio/device-profiles")
    assert status == 200
    assert configured["items"] == [
        {
            "deviceProfileId": "local-android",
            "label": "Local Android",
            "platform": "android",
            "availability": "configured",
        }
    ]
    serialized = json.dumps(configured, sort_keys=True)
    for private_canary in ("serial", "adb", "target", "fingerprint", "/private/"):
        assert private_canary not in serialized.lower()

    payload = _preview_payload(
        benchmark_http_server["entryId"],
        benchmark_http_server["taskId"],
        benchmark_http_server["agentId"],
        benchmark_http_server["revisionId"],
    )
    payload["deviceProfileId"] = "unknown-profile"
    status, unknown = _request(
        address,
        "POST",
        "/studio/benchmark-experiments/preview",
        payload,
    )
    assert status == 400
    assert unknown["error"]["code"] == "benchmark.preview.device_profile_unknown"

    composition = benchmark_http_server["composition"]
    empty_profiles = AndroidDeviceProfileResolver()
    empty_service = StudioBenchmarkApplicationService(
        catalog=composition.catalog,
        agents=composition.service.agents,
        profiles=empty_profiles,
        contract_catalog=composition.service.contract_catalog,
    )
    empty_composition = replace(
        composition,
        service=empty_service,
        profiles=empty_profiles,
    )
    server = create_http_server(
        "127.0.0.1",
        0,
        application_service=benchmark_http_server["applicationService"],
        benchmark_composition=empty_composition,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        empty_address = ("127.0.0.1", int(server.server_address[1]))
        status, empty = _request(
            empty_address,
            "GET",
            "/studio/device-profiles",
        )
        assert status == 200
        assert empty == {"schemaVersion": 1, "items": []}
        status, rejected = _request(
            empty_address,
            "POST",
            "/studio/benchmark-experiments/preview",
            {**payload, "deviceProfileId": "local-android"},
        )
        assert status == 400
        assert rejected["error"]["code"] == (
            "benchmark.preview.device_profile_unknown"
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


def test_authoring_http_template_revision_and_conflict_journey(
    benchmark_http_server: dict[str, Any],
) -> None:
    """Create, page, reopen, save, retry, and reject a stale HTTP writer."""
    address = benchmark_http_server["address"]
    create_payload = {
        "schemaVersion": 1,
        "clientRequestId": "http-create-template",
        "name": "HTTP Draft",
        "source": {
            "kind": "template",
            "template": "minimal",
            "publisher": "tests",
            "packageName": "http-draft",
            "version": "0.1.0",
        },
    }
    status, created = _request(
        address,
        "POST",
        "/api/studio/benchmark-authoring/drafts",
        create_payload,
        origin="http://127.0.0.1:5173",
    )
    assert status == 201
    assert created["created"] is True
    draft_id = created["draft"]["draftId"]
    first_revision_id = created["revision"]["revisionId"]
    status, retried = _request(
        address,
        "POST",
        "/studio/benchmark-authoring/drafts",
        create_payload,
    )
    assert status == 200
    assert retried["created"] is False
    assert retried["revision"]["revisionId"] == first_revision_id

    status, page = _request(
        address,
        "GET",
        "/studio/benchmark-authoring/drafts?limit=1",
    )
    assert status == 200
    assert page["items"][0]["draftId"] == draft_id
    second_payload = json.loads(json.dumps(create_payload))
    second_payload["clientRequestId"] = "http-create-template-second"
    second_payload["name"] = "Second HTTP Draft"
    second_payload["source"]["packageName"] = "http-draft-second"
    status, second_created = _request(
        address,
        "POST",
        "/studio/benchmark-authoring/drafts",
        second_payload,
    )
    assert status == 201
    status, first_page = _request(
        address,
        "GET",
        "/studio/benchmark-authoring/drafts?limit=1",
    )
    assert status == 200
    assert first_page["nextCursor"]
    status, second_page = _request(
        address,
        "GET",
        "/studio/benchmark-authoring/drafts?limit=1"
        f"&cursor={first_page['nextCursor']}",
    )
    assert status == 200
    assert len(second_page["items"]) == 1
    status, detail = _request(
        address,
        "GET",
        f"/studio/benchmark-authoring/drafts/{draft_id}",
    )
    assert status == 200
    assert detail["currentRevision"]["revisionId"] == first_revision_id
    status, exact = _request(
        address,
        "GET",
        f"/studio/benchmark-authoring/drafts/{draft_id}"
        f"/revisions/{first_revision_id}",
    )
    assert status == 200
    assert exact["revisionId"] == first_revision_id
    status, foreign = _request(
        address,
        "GET",
        "/studio/benchmark-authoring/drafts/"
        f"{second_created['draft']['draftId']}"
        f"/revisions/{first_revision_id}",
    )
    assert status == 404
    assert foreign["error"]["code"] == "benchmark.authoring.not_found"

    document = created["revision"]["document"]
    document["manifest"]["document"]["title"] = "HTTP Edited"
    save_payload = {
        "schemaVersion": 1,
        "clientRequestId": "http-save",
        "baseRevisionId": first_revision_id,
        "document": document,
    }
    status, saved = _request(
        address,
        "POST",
        f"/studio/benchmark-authoring/drafts/{draft_id}/revisions",
        save_payload,
    )
    assert status == 201
    assert saved["revision"]["ordinal"] == 2
    status, saved_retry = _request(
        address,
        "POST",
        f"/studio/benchmark-authoring/drafts/{draft_id}/revisions",
        save_payload,
    )
    assert status == 200
    assert saved_retry["created"] is False
    stale_payload = {
        **save_payload,
        "clientRequestId": "http-save-stale",
    }
    status, stale = _request(
        address,
        "POST",
        f"/studio/benchmark-authoring/drafts/{draft_id}/revisions",
        stale_payload,
    )
    assert status == 409
    assert stale["error"]["code"] == "benchmark.authoring.revision_conflict"
    assert stale["error"]["currentRevisionId"] == (
        saved["revision"]["revisionId"]
    )

def test_authoring_contract_test_http_profiles_command_and_methods(
    benchmark_http_server: dict[str, Any],
) -> None:
    """Expose strict no-store profile metadata and exact-revision commands.

    Args:
        benchmark_http_server: Running complete authoring HTTP composition.

    Raises:
        AssertionError: Public schema, safety, or HTTP mapping drifts.

    Returns:
        None.
    """
    address = benchmark_http_server["address"]
    status, body, headers = _binary_request(
        address,
        "GET",
        "/api/studio/benchmark-authoring/contract-test-profiles",
        origin="http://127.0.0.1:5173",
    )
    assert status == 200
    profiles = json.loads(body.decode("utf-8"))
    assert profiles["profiles"][0]["profileId"] == "studio-safe-v1"
    assert headers["cache-control"] == "private, no-store"
    assert "factory" not in body.decode("utf-8")

    status, created = _request(
        address,
        "POST",
        "/studio/benchmark-authoring/drafts",
        {
            "schemaVersion": 1,
            "clientRequestId": "contract-http-create",
            "name": "Contract HTTP Draft",
            "source": {
                "kind": "template",
                "template": "minimal",
                "publisher": "tests",
                "packageName": "contract-http",
                "version": "0.1.0",
            },
        },
    )
    assert status == 201
    draft_id = created["draft"]["draftId"]
    revision_id = created["revision"]["revisionId"]
    path = f"/studio/benchmark-authoring/drafts/{draft_id}/contract-tests"
    command = {
        "schemaVersion": 1,
        "revisionId": revision_id,
        "split": "test",
        "seed": 23,
        "fixtureProfileId": "studio-safe-v1",
    }
    status, result = _request(address, "POST", path, command)
    assert status == 200
    assert result["revisionId"] == revision_id
    assert result["validDefinition"] is True
    assert result["coverage"]["failed"] == 0
    assert result["safety"]["realDeviceEvidence"] is False
    assert result["safety"]["processSandbox"] is False
    assert result["safety"]["packageCodeExecuted"] is False
    serialized = json.dumps(result)
    assert benchmark_http_server["tmpPath"] not in serialized
    assert "contentIdentity" not in serialized

    status, malformed = _request(
        address,
        "POST",
        path,
        {**command, "module": "forbidden.fixture"},
    )
    assert status == 400
    assert malformed["error"]["code"] == (
        "benchmark.authoring.contract_test_request_invalid"
    )
    status, unavailable = _request(
        address,
        "POST",
        path,
        {**command, "fixtureProfileId": "absent"},
    )
    assert status == 400
    assert unavailable["error"]["code"] == (
        "benchmark.authoring.fixture_profile_unavailable"
    )
    assert _request(address, "GET", path)[0] == 405
    assert _request(
        address,
        "POST",
        "/studio/benchmark-authoring/contract-test-profiles",
        {"schemaVersion": 1},
    )[0] == 405


def test_authoring_contract_test_http_failure_matrix_is_private(
    benchmark_http_server: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Map bounded Contract Test failures without partial or cacheable facts.

    Args:
        benchmark_http_server: Running complete authoring HTTP composition.
        monkeypatch: Pytest method replacement fixture.

    Raises:
        AssertionError: Status, error code, or cache control drifts.

    Returns:
        None.
    """
    address = benchmark_http_server["address"]
    status, created = _request(
        address,
        "POST",
        "/studio/benchmark-authoring/drafts",
        {
            "schemaVersion": 1,
            "clientRequestId": "contract-http-failure-create",
            "name": "Contract HTTP Failure Draft",
            "source": {
                "kind": "template",
                "template": "minimal",
                "publisher": "tests",
                "packageName": "contract-http-failure",
                "version": "0.1.0",
            },
        },
    )
    assert status == 201
    draft_id = created["draft"]["draftId"]
    revision_id = created["revision"]["revisionId"]
    path = f"/studio/benchmark-authoring/drafts/{draft_id}/contract-tests"
    command = {
        "schemaVersion": 1,
        "revisionId": revision_id,
        "split": "test",
        "seed": 23,
        "fixtureProfileId": "studio-safe-v1",
    }
    encoded = json.dumps(command).encode("utf-8")
    service = benchmark_http_server["contractTests"]

    failures = (
        (
            413,
            StudioBenchmarkAuthoringCapacityError(
                "benchmark.authoring.contract_test_too_large",
                "Contract Test exceeds its safe limit",
            ),
        ),
        (
            409,
            StudioBenchmarkAuthoringRevisionConflictError(
                "benchmark.authoring.analysis_revision_stale",
                "Current revision changed",
                current_revision_id=revision_id,
            ),
        ),
        (
            404,
            StudioBenchmarkAuthoringNotFoundError(
                "benchmark.authoring.revision_not_found",
                "Requested resource was not found",
            ),
        ),
        (
            503,
            StudioBenchmarkAuthoringStorageError(
                "benchmark.authoring.analysis_unavailable",
                "Private analysis is unavailable",
            ),
        ),
    )
    for expected_status, failure in failures:
        def reject(*args: object, _failure=failure, **kwargs: object) -> object:
            """Raise one injected bounded domain failure.

            Args:
                args: Ignored service inputs.
                _failure: Bound failure for this matrix row.
                kwargs: Ignored service keyword inputs.

            Raises:
                Exception: The injected domain failure.
            """
            del args, kwargs
            raise _failure

        monkeypatch.setattr(service, "run", reject)
        actual_status, raw, headers = _binary_request(
            address,
            "POST",
            path,
            body=encoded,
            content_type="application/json",
        )
        assert actual_status == expected_status
        assert headers["cache-control"] == "private, no-store"
        payload = json.loads(raw.decode("utf-8"))
        assert payload["error"]["code"] == failure.code
        if expected_status == 409:
            assert payload["error"]["currentRevisionId"] == revision_id

    malformed_status, _, malformed_headers = _binary_request(
        address,
        "POST",
        path,
        body=b"not-json",
        content_type="application/json",
    )
    assert malformed_status == 400
    assert malformed_headers["cache-control"] == "private, no-store"


def test_authoring_validated_freeze_http_success_retry_and_exact_read(
    benchmark_http_server: dict[str, Any],
) -> None:
    """Expose only strict private freeze command and exact-read resources.

    Args:
        benchmark_http_server: Running complete authoring HTTP composition.

    Raises:
        AssertionError: Status, shape, privacy, or ownership contracts drift.

    Returns:
        None.
    """
    address = benchmark_http_server["address"]
    status, created = _request(
        address,
        "POST",
        "/studio/benchmark-authoring/drafts",
        {
            "schemaVersion": 1,
            "clientRequestId": "freeze-http-create",
            "name": "Freeze HTTP Draft",
            "source": {
                "kind": "template",
                "template": "minimal",
                "publisher": "tests",
                "packageName": "freeze-http",
                "version": "0.1.0",
            },
        },
    )
    assert status == 201
    draft_id = created["draft"]["draftId"]
    revision_id = created["revision"]["revisionId"]
    path = (
        f"/api/studio/benchmark-authoring/drafts/{draft_id}"
        "/package-revisions"
    )
    command = {
        "schemaVersion": 1,
        "clientRequestId": "freeze-http-command",
        "revisionId": revision_id,
    }
    status, raw, headers = _binary_request(
        address,
        "POST",
        path,
        body=json.dumps(command).encode("utf-8"),
        content_type="application/json",
        origin="http://127.0.0.1:5173",
    )
    assert status == 201
    result = json.loads(raw.decode("utf-8"))
    assert result["created"] is True
    assert headers["cache-control"] == "private, no-store"
    assert headers["access-control-allow-origin"] == (
        "http://127.0.0.1:5173"
    )
    package = result["detail"]["packageRevision"]
    attestation = result["detail"]["validationAttestation"]
    package_id = package["packageRevisionId"]
    assert package["authoringRevisionId"] == revision_id
    assert attestation["safety"]["executionEvidence"] is False
    assert attestation["safety"]["publicationEvidence"] is False
    serialized = json.dumps(result)
    assert benchmark_http_server["tmpPath"] not in serialized
    assert "/private/" not in serialized
    assert "storageKey" not in serialized

    retry_status, retry = _request(address, "POST", path, command)
    assert retry_status == 200
    assert retry["created"] is False
    assert retry["detail"] == result["detail"]
    detail_path = f"{path}/{package_id}"
    read_status, read_raw, read_headers = _binary_request(
        address,
        "GET",
        detail_path,
    )
    assert read_status == 200
    assert json.loads(read_raw.decode("utf-8")) == result["detail"]
    assert read_headers["cache-control"] == "private, no-store"

    page_status, page = _request(address, "GET", path)
    assert page_status == 200
    assert page["items"][0]["packageRevisionId"] == package_id
    assert _request(address, "POST", detail_path, command)[0] == 405
    query_status, query_error = _request(
        address,
        "GET",
        detail_path + "?member=benchmark.yaml",
    )
    assert query_status == 400
    assert query_error["error"]["code"] == (
        "benchmark.authoring.freeze_query_invalid"
    )
    malformed_status, malformed = _request(
        address,
        "POST",
        path,
        {**command, "publish": True},
    )
    assert malformed_status == 400
    assert malformed["error"]["code"] == (
        "benchmark.authoring.freeze_request_invalid"
    )


def test_authoring_package_release_http_publish_export_and_download(
    benchmark_http_server: dict[str, Any],
) -> None:
    """Expose strict release resources and GET/HEAD archive parity.

    Args:
        benchmark_http_server: Running complete authoring HTTP composition.

    Raises:
        AssertionError: Release status, ownership, headers, or privacy drift.

    Returns:
        None.
    """
    address = benchmark_http_server["address"]
    status, created = _request(
        address,
        "POST",
        "/studio/benchmark-authoring/drafts",
        {
            "schemaVersion": 1,
            "clientRequestId": "release-http-create",
            "name": "Release HTTP Draft",
            "source": {
                "kind": "template",
                "template": "minimal",
                "publisher": "tests",
                "packageName": "release-http",
                "version": "0.1.0",
            },
        },
    )
    assert status == 201
    draft_id = created["draft"]["draftId"]
    revision_id = created["revision"]["revisionId"]
    collection = (
        f"/api/studio/benchmark-authoring/drafts/{draft_id}"
        "/package-revisions"
    )
    status, frozen = _request(
        address,
        "POST",
        collection,
        {
            "schemaVersion": 1,
            "clientRequestId": "release-http-freeze",
            "revisionId": revision_id,
        },
    )
    assert status == 201
    package = frozen["detail"]["packageRevision"]
    package_id = package["packageRevisionId"]

    status, page = _request(address, "GET", collection + "?limit=1")
    assert status == 200
    assert page["items"][0]["packageRevisionId"] == package_id
    publish_path = f"{collection}/{package_id}/publications"
    release_command = {
        "schemaVersion": 1,
        "clientRequestId": "release-http-publish",
    }
    status, publication = _request(
        address,
        "POST",
        publish_path,
        release_command,
    )
    assert status == 201
    assert publication["publication"]["safety"]["executionEvidence"] is False
    publication_id = publication["publication"]["publicationId"]
    status, retried = _request(
        address,
        "POST",
        publish_path,
        release_command,
    )
    assert status == 200
    assert retried["publication"] == publication["publication"]
    status, exact_publication = _request(
        address,
        "GET",
        f"{publish_path}/{publication_id}",
    )
    assert status == 200
    assert exact_publication == publication["publication"]
    malformed_status, malformed = _request(
        address,
        "POST",
        publish_path,
        {**release_command, "destination": "/tmp/private"},
    )
    assert malformed_status == 400
    assert malformed["error"]["code"] == (
        "benchmark.authoring.release_request_invalid"
    )
    status, catalog_page = _request(
        address,
        "GET",
        "/studio/benchmarks?query=release-http&sourceKind=catalog",
    )
    assert status == 200
    assert any(
        item["catalogEntryId"]
        == publication["publication"]["catalogEntryId"]
        for item in catalog_page["items"]
    )

    export_path = f"{collection}/{package_id}/exports"
    status, exported = _request(
        address,
        "POST",
        export_path,
        {
            "schemaVersion": 1,
            "clientRequestId": "release-http-export",
        },
    )
    assert status == 201
    descriptor = exported["packageExport"]
    retry_status, retry_export = _request(
        address,
        "POST",
        export_path,
        {
            "schemaVersion": 1,
            "clientRequestId": "release-http-export",
        },
    )
    assert retry_status == 200
    assert retry_export["packageExport"] == descriptor
    exact_export_status, exact_export = _request(
        address,
        "GET",
        f"{export_path}/{descriptor['exportId']}",
    )
    assert exact_export_status == 200
    assert exact_export == descriptor
    content_path = descriptor["contentLink"]
    head_status, head_body, head_headers = _binary_request(
        address,
        "HEAD",
        content_path,
        origin="http://127.0.0.1:5173",
    )
    assert head_status == 200
    assert head_body == b""
    assert int(head_headers["content-length"]) == descriptor["size"]
    assert head_headers["x-content-sha256"] == descriptor["sha256"]
    assert head_headers["content-type"] == "application/zip"
    assert head_headers["cache-control"] == "private, no-store"
    assert head_headers["x-content-type-options"] == "nosniff"
    assert "X-Content-SHA256" in head_headers["access-control-expose-headers"]
    assert descriptor["filename"] in head_headers["content-disposition"]
    get_status, archive, get_headers = _binary_request(
        address,
        "GET",
        content_path,
    )
    assert get_status == 200
    assert len(archive) == descriptor["size"]
    assert get_headers["x-content-sha256"] == descriptor["sha256"]
    assert get_headers["content-disposition"] == head_headers["content-disposition"]
    assert benchmark_http_server["tmpPath"] not in json.dumps(exported)
    assert "/private/" not in json.dumps(exported)
    assert _request(
        address,
        "GET",
        content_path.replace(draft_id, "benchmark-draft-" + "f" * 32),
    )[0] == 404
    assert _request(
        address,
        "POST",
        content_path,
        {"schemaVersion": 1},
    )[0] == 405


def test_authoring_validated_freeze_http_failure_matrix_is_private(
    benchmark_http_server: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Map eligibility, ownership, conflict, capacity, and outage failures.

    Args:
        benchmark_http_server: Running complete authoring HTTP composition.
        monkeypatch: Pytest method replacement fixture.

    Raises:
        AssertionError: Safe status or private error shape drifts.

    Returns:
        None.
    """
    address = benchmark_http_server["address"]
    status, created = _request(
        address,
        "POST",
        "/studio/benchmark-authoring/drafts",
        {
            "schemaVersion": 1,
            "clientRequestId": "freeze-http-failure-create",
            "name": "Freeze HTTP Failure Draft",
            "source": {
                "kind": "template",
                "template": "minimal",
                "publisher": "tests",
                "packageName": "freeze-http-failure",
                "version": "0.1.0",
            },
        },
    )
    assert status == 201
    draft_id = created["draft"]["draftId"]
    revision_id = created["revision"]["revisionId"]
    path = (
        f"/studio/benchmark-authoring/drafts/{draft_id}/package-revisions"
    )
    command = {
        "schemaVersion": 1,
        "clientRequestId": "freeze-http-failure-command",
        "revisionId": revision_id,
    }
    encoded = json.dumps(command).encode("utf-8")
    service = benchmark_http_server["freeze"]
    eligibility_diagnostics = (
        StudioBenchmarkAuthoringDiagnosticV1(
            code="benchmark.package.invalid",
            message="Benchmark Package is invalid.",
            member_kind="manifest",
            member_path="benchmark.yaml",
            field_path=("manifest",),
        ),
    )
    failures = (
        (
            400,
            StudioBenchmarkAuthoringFreezeEligibilityError(
                "benchmark.authoring.freeze_ineligible",
                "Benchmark revision is not eligible",
                diagnostics=eligibility_diagnostics,
            ),
        ),
        (
            404,
            StudioBenchmarkAuthoringNotFoundError(
                "benchmark.authoring.package_revision_not_found",
                "Benchmark Package revision was not found",
            ),
        ),
        (
            409,
            StudioBenchmarkAuthoringRevisionConflictError(
                "benchmark.authoring.freeze_revision_stale",
                "Benchmark revision is stale",
                current_revision_id=revision_id,
            ),
        ),
        (
            409,
            StudioBenchmarkAuthoringIdempotencyConflictError(
                "benchmark.authoring.freeze_idempotency_conflict",
                "Benchmark freeze request identity was reused",
            ),
        ),
        (
            413,
            StudioBenchmarkAuthoringCapacityError(
                "benchmark.authoring.freeze_content_too_large",
                "Benchmark freeze exceeds its safe limit",
            ),
        ),
        (
            503,
            StudioBenchmarkAuthoringStorageError(
                "benchmark.authoring.storage_failed",
                "Benchmark freeze storage is unavailable",
            ),
        ),
    )
    for expected_status, failure in failures:
        def reject(*args: object, _failure=failure, **kwargs: object) -> object:
            """Raise one injected bounded freeze failure.

            Args:
                args: Ignored service arguments.
                _failure: Bound matrix failure.
                kwargs: Ignored service keyword arguments.

            Raises:
                Exception: Injected domain failure.
            """
            del args, kwargs
            raise _failure

        monkeypatch.setattr(service, "freeze", reject)
        actual_status, body, headers = _binary_request(
            address,
            "POST",
            path,
            body=encoded,
            content_type="application/json",
        )
        assert actual_status == expected_status
        assert headers["cache-control"] == "private, no-store"
        payload = json.loads(body.decode("utf-8"))
        assert payload["error"]["code"] == failure.code
        assert benchmark_http_server["tmpPath"] not in json.dumps(payload)
        if expected_status == 400:
            assert payload["error"]["diagnostics"]
        if isinstance(failure, StudioBenchmarkAuthoringRevisionConflictError):
            assert payload["error"]["currentRevisionId"] == revision_id

    missing_type_status, _, missing_type_headers = _binary_request(
        address,
        "POST",
        path,
        body=encoded,
    )
    assert missing_type_status == 400
    assert missing_type_headers["cache-control"] == "private, no-store"


def test_authoring_analysis_http_validation_dry_run_and_strict_methods(
    benchmark_http_server: dict[str, Any],
) -> None:
    """Expose exact-current analysis with strict method and error semantics.

    Args:
        benchmark_http_server: Running local server plus created Agent and
            private fixture-location facts used only for leakage assertions.

    Raises:
        AssertionError: Any success, partial-identity, stale, ownership,
            capacity, storage, method, or safe-error contract drifts.

    Returns:
        None.
    """
    address = benchmark_http_server["address"]
    status, created = _request(
        address,
        "POST",
        "/studio/benchmark-authoring/drafts",
        {
            "schemaVersion": 1,
            "clientRequestId": "analysis-http-create",
            "name": "Analysis HTTP Draft",
            "source": {
                "kind": "template",
                "template": "minimal",
                "publisher": "tests",
                "packageName": "analysis-http",
                "version": "0.1.0",
            },
        },
    )
    assert status == 201
    draft_id = created["draft"]["draftId"]
    revision_id = created["revision"]["revisionId"]
    validate_path = (
        f"/api/studio/benchmark-authoring/drafts/{draft_id}/validate"
    )
    payload = json.dumps(
        {"schemaVersion": 1, "revisionId": revision_id, "split": "test"}
    ).encode("utf-8")
    status, body, headers = _binary_request(
        address,
        "POST",
        validate_path,
        body=payload,
        content_type="application/json",
        origin="http://127.0.0.1:5173",
    )
    assert status == 200
    validation = json.loads(body.decode("utf-8"))
    assert validation["valid"] is True
    assert validation["executionEvidence"] is False
    assert headers["cache-control"] == "private, no-store"
    assert headers["access-control-allow-origin"] == (
        "http://127.0.0.1:5173"
    )

    dry_run_path = (
        f"/studio/benchmark-authoring/drafts/{draft_id}/dry-run"
    )
    status, dry_run = _request(
        address,
        "POST",
        dry_run_path,
        {
            "schemaVersion": 1,
            "revisionId": revision_id,
            "split": "test",
            "taskIds": [],
            "agentRevisions": [
                {
                    "agentId": benchmark_http_server["agentId"],
                    "revisionId": benchmark_http_server["revisionId"],
                }
            ],
        },
    )
    assert status == 200
    assert dry_run["ok"] is True
    assert len(dry_run["schedule"]) == 1
    assert dry_run["executionEvidence"] is False
    serialized = json.dumps(dry_run)
    assert benchmark_http_server["tmpPath"] not in serialized
    assert "contentIdentity" not in serialized

    status, partial = _request(
        address,
        "POST",
        validate_path,
        {
            "schemaVersion": 1,
            "revisionId": revision_id,
            "split": "unknown",
        },
    )
    assert status == 200
    assert partial["valid"] is False
    assert partial["identities"]["package"] == "tests/analysis-http@0.1.0"
    assert partial["identities"]["packageContent"].startswith("sha256:")
    assert "benchmarkPlan" not in partial["identities"]

    status, method_error = _request(address, "GET", validate_path)
    assert status == 405
    assert method_error["error"]["code"] == "studio.http.method_not_allowed"
    status, unknown = _request(
        address,
        "POST",
        dry_run_path,
        {
            "schemaVersion": 1,
            "revisionId": revision_id,
            "split": "test",
            "agentRevisions": [
                {
                    "agentId": benchmark_http_server["agentId"],
                    "revisionId": benchmark_http_server["revisionId"],
                }
            ],
            "deviceProfileId": "forbidden",
        },
    )
    assert status == 400
    assert unknown["error"]["code"] == (
        "benchmark.authoring.analysis_request_invalid"
    )

    saved_document = created["revision"]["document"]
    saved_document["manifest"]["document"]["title"] = "Advance"
    status, saved = _request(
        address,
        "POST",
        f"/studio/benchmark-authoring/drafts/{draft_id}/revisions",
        {
            "schemaVersion": 1,
            "clientRequestId": "analysis-http-advance",
            "baseRevisionId": revision_id,
            "document": saved_document,
        },
    )
    assert status == 201
    status, stale = _request(
        address,
        "POST",
        validate_path,
        {"schemaVersion": 1, "revisionId": revision_id, "split": "test"},
    )
    assert status == 409
    assert stale["error"]["currentRevisionId"] == (
        saved["revision"]["revisionId"]
    )

    status, foreign_draft = _request(
        address,
        "POST",
        "/studio/benchmark-authoring/drafts",
        {
            "schemaVersion": 1,
            "clientRequestId": "analysis-http-foreign",
            "name": "Foreign Analysis Draft",
            "source": {
                "kind": "template",
                "template": "minimal",
                "publisher": "tests",
                "packageName": "analysis-http-foreign",
                "version": "0.1.0",
            },
        },
    )
    assert status == 201
    status, foreign = _request(
        address,
        "POST",
        "/studio/benchmark-authoring/drafts/"
        f"{foreign_draft['draft']['draftId']}/validate",
        {
            "schemaVersion": 1,
            "revisionId": saved["revision"]["revisionId"],
            "split": "test",
        },
    )
    assert status == 404
    assert foreign["error"]["code"] == "benchmark.authoring.not_found"

    capacity_document = saved["revision"]["document"]
    capacity_document["protocolFiles"][0]["document"]["repeats"] = 10_001
    status, capacity_saved = _request(
        address,
        "POST",
        f"/studio/benchmark-authoring/drafts/{draft_id}/revisions",
        {
            "schemaVersion": 1,
            "clientRequestId": "analysis-http-capacity",
            "baseRevisionId": saved["revision"]["revisionId"],
            "document": capacity_document,
        },
    )
    assert status == 201
    status, capacity = _request(
        address,
        "POST",
        dry_run_path,
        {
            "schemaVersion": 1,
            "revisionId": capacity_saved["revision"]["revisionId"],
            "split": "test",
            "taskIds": [],
            "agentRevisions": [
                {
                    "agentId": benchmark_http_server["agentId"],
                    "revisionId": benchmark_http_server["revisionId"],
                }
            ],
        },
    )
    assert status == 413
    assert capacity["error"]["code"] == (
        "benchmark.authoring.schedule_too_large"
    )

    invalid_document = capacity_saved["revision"]["document"]
    invalid_document["manifest"]["document"]["title"] = ""
    invalid_document["protocolFiles"][0]["document"]["repeats"] = 1
    status, invalid_saved = _request(
        address,
        "POST",
        f"/studio/benchmark-authoring/drafts/{draft_id}/revisions",
        {
            "schemaVersion": 1,
            "clientRequestId": "analysis-http-invalid",
            "baseRevisionId": capacity_saved["revision"]["revisionId"],
            "document": invalid_document,
        },
    )
    assert status == 201
    status, invalid = _request(
        address,
        "POST",
        validate_path,
        {
            "schemaVersion": 1,
            "revisionId": invalid_saved["revision"]["revisionId"],
            "split": "test",
        },
    )
    assert status == 200
    assert invalid["valid"] is False
    assert "package" not in invalid["identities"]
    assert invalid["diagnostics"]

    status, query_error = _request(
        address,
        "POST",
        validate_path + "?destination=forbidden",
        {
            "schemaVersion": 1,
            "revisionId": invalid_saved["revision"]["revisionId"],
            "split": "test",
        },
    )
    assert status == 400
    assert query_error["error"]["code"] == (
        "benchmark.authoring.analysis_query_invalid"
    )

    status, corrupt_draft = _request(
        address,
        "POST",
        "/studio/benchmark-authoring/drafts",
        {
            "schemaVersion": 1,
            "clientRequestId": "analysis-http-corrupt-create",
            "name": "Corrupt Analysis Draft",
            "source": {
                "kind": "template",
                "template": "minimal",
                "publisher": "tests",
                "packageName": "analysis-http-corrupt",
                "version": "0.1.0",
            },
        },
    )
    assert status == 201
    corrupt_draft_id = corrupt_draft["draft"]["draftId"]
    upload_query = urlencode(
        {
            "schemaVersion": "1",
            "clientRequestId": "analysis-http-corrupt-upload",
            "baseRevisionId": corrupt_draft["revision"]["revisionId"],
            "kind": "asset",
            "path": "assets/corrupt.txt",
        }
    )
    status, upload_body, _ = _binary_request(
        address,
        "POST",
        "/studio/benchmark-authoring/drafts/"
        f"{corrupt_draft_id}/resources/corrupt/upload?{upload_query}",
        body=b"trusted",
        content_type="text/plain",
    )
    assert status == 201
    uploaded = json.loads(upload_body.decode("utf-8"))
    object_root = (
        Path(benchmark_http_server["tmpPath"])
        / "studio.sqlite3.benchmark-authoring"
        / "objects"
    )
    digest = uploaded["resource"]["sha256"].removeprefix("sha256:")
    stored = object_root / digest[:2] / digest
    assert stored.is_file()
    stored.write_bytes(b"corrupt")
    status, storage = _request(
        address,
        "POST",
        "/studio/benchmark-authoring/drafts/"
        f"{corrupt_draft_id}/validate",
        {
            "schemaVersion": 1,
            "revisionId": uploaded["revision"]["revisionId"],
            "split": "test",
        },
    )
    assert status == 503
    assert storage["error"]["code"] == "benchmark.authoring.content_integrity"
    assert benchmark_http_server["tmpPath"] not in json.dumps(storage)


def test_authoring_analysis_http_journey_crosses_no_forbidden_boundaries(
    benchmark_http_server: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Prove complete validation/dry-run HTTP journeys remain side-effect free.

    Args:
        benchmark_http_server: Running local server with durable authoring and
            one immutable saved Agent revision.
        monkeypatch: Pytest patch helper used to install fail-fast canaries.

    Raises:
        AssertionError: A forbidden runtime, external, or publication boundary
            is crossed.

    Returns:
        None.
    """
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

    counts = {
        name: 0
        for name in (
            "initializer/plugin-construction",
            "environment",
            "evaluator",
            "benchmark-runtime",
            "model/secret-resolution",
            "device/android",
            "agent-execution",
            "task-run/result",
            "experiment",
            "report/trajectory/bundle",
            "publication",
            "replay",
            "export",
            "migration",
            "network",
        )
    }

    def fail(name: str):
        """Create one variadic fail-fast canary for a forbidden boundary.

        Args:
            name: Stable boundary label whose counter must remain zero.

        Raises:
            None.

        Returns:
            Callable that records and rejects any boundary crossing.
        """

        def canary(*args, **kwargs):
            """Record one forbidden call and fail the HTTP journey immediately.

            Args:
                *args: Ignored target positional arguments.
                **kwargs: Ignored target keyword arguments.

            Raises:
                AssertionError: Always, because analysis cannot cross this
                    boundary.

            Returns:
                Never returns.
            """
            del args, kwargs
            counts[name] += 1
            raise AssertionError(f"analysis crossed forbidden {name} boundary")

        return canary

    targets = (
        (runtime_materializer, "materialize_task", "initializer/plugin-construction"),
        (runtime_lifecycle, "execute_environment_calls", "environment"),
        (runtime_evaluator, "evaluate_tree", "evaluator"),
        (runtime_suite.BenchmarkExperimentRuntime, "run", "benchmark-runtime"),
        (
            run_execution.ProductionComponentResolverFactory,
            "create",
            "model/secret-resolution",
        ),
        (run_execution.AndroidDeviceProfileResolver, "resolve", "device/android"),
        (
            run_execution.AndroidStudioRunExecutionAdapter,
            "execute",
            "agent-execution",
        ),
        (
            benchmark_execution.StudioBenchmarkExecutionAdapter,
            "execute",
            "task-run/result",
        ),
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
    )
    for target, attribute, name in targets:
        monkeypatch.setattr(target, attribute, fail(name))

    address = benchmark_http_server["address"]
    original_create_connection = socket.create_connection

    def allow_only_fixture_transport(target_address, *args, **kwargs):
        """Allow the loopback fixture transport and reject outbound networking.

        Args:
            target_address: Requested ``(host, port)`` socket destination.
            *args: Remaining standard ``socket.create_connection`` arguments.
            **kwargs: Remaining standard ``socket.create_connection`` options.

        Raises:
            AssertionError: Destination is not the exact fixture server.
            OSError: The allowed loopback transport cannot be opened.

        Returns:
            Connected loopback socket for the test HTTP client.
        """
        if tuple(target_address) != tuple(address):
            counts["network"] += 1
            raise AssertionError(
                "analysis attempted a non-fixture network connection"
            )
        return original_create_connection(target_address, *args, **kwargs)

    monkeypatch.setattr(socket, "create_connection", allow_only_fixture_transport)

    status, created = _request(
        address,
        "POST",
        "/studio/benchmark-authoring/drafts",
        {
            "schemaVersion": 1,
            "clientRequestId": "analysis-http-side-effect-create",
            "name": "Analysis HTTP Side Effect Draft",
            "source": {
                "kind": "template",
                "template": "minimal",
                "publisher": "tests",
                "packageName": "analysis-http-side-effects",
                "version": "0.1.0",
            },
        },
    )
    assert status == 201
    draft_id = created["draft"]["draftId"]
    revision_id = created["revision"]["revisionId"]
    status, validation = _request(
        address,
        "POST",
        f"/studio/benchmark-authoring/drafts/{draft_id}/validate",
        {"schemaVersion": 1, "revisionId": revision_id, "split": "test"},
    )
    assert status == 200
    assert validation["valid"] is True
    status, dry_run = _request(
        address,
        "POST",
        f"/studio/benchmark-authoring/drafts/{draft_id}/dry-run",
        {
            "schemaVersion": 1,
            "revisionId": revision_id,
            "split": "test",
            "taskIds": [],
            "agentRevisions": [
                {
                    "agentId": benchmark_http_server["agentId"],
                    "revisionId": benchmark_http_server["revisionId"],
                }
            ],
        },
    )
    assert status == 200
    assert dry_run["ok"] is True
    assert all(count == 0 for count in counts.values())
    analysis_staging = (
        Path(benchmark_http_server["tmpPath"])
        / "studio.sqlite3.benchmark-authoring"
        / "staging"
        / "analysis"
    )
    assert not tuple(analysis_staging.iterdir())


def test_authoring_http_catalog_metadata_and_strict_negative_cases(
    benchmark_http_server: dict[str, Any],
) -> None:
    """Import metadata-only resources and reject path/query/identity injection."""
    address = benchmark_http_server["address"]
    entry_id = benchmark_http_server["entryId"]
    status, imported = _request(
        address,
        "POST",
        "/studio/benchmark-authoring/drafts",
        {
            "schemaVersion": 1,
            "clientRequestId": "http-create-catalog",
            "name": "Catalog Draft",
            "source": {
                "kind": "catalog",
                "catalogEntryId": entry_id,
            },
        },
    )
    assert status == 201
    resource = imported["revision"]["document"]["resources"][0]
    assert resource["contentIdentity"].startswith("benchmark-content-")
    serialized = json.dumps(imported)
    assert benchmark_http_server["tmpPath"] not in serialized
    assert "fixture\n" not in serialized

    status, invalid = _request(
        address,
        "POST",
        "/studio/benchmark-authoring/drafts",
        {
            "schemaVersion": 1,
            "clientRequestId": "http-invalid",
            "name": "Invalid",
            "source": {
                "kind": "catalog",
                "catalogEntryId": entry_id,
                "path": benchmark_http_server["tmpPath"],
            },
        },
    )
    assert status == 400
    assert benchmark_http_server["tmpPath"] not in json.dumps(invalid)
    status, query_error = _request(
        address,
        "GET",
        "/studio/benchmark-authoring/drafts?hostPath=forbidden",
    )
    assert status == 400
    assert query_error["error"]["code"] == (
        "benchmark.authoring.query_invalid"
    )
    status, cursor_error = _request(
        address,
        "GET",
        "/studio/benchmark-authoring/drafts?cursor=not-a-cursor",
    )
    assert status == 400
    assert cursor_error["error"]["code"] == (
        "benchmark.authoring.cursor_invalid"
    )
    status, identity_error = _request(
        address,
        "GET",
        "/studio/benchmark-authoring/drafts/not-a-draft",
    )
    assert status == 400
    assert identity_error["error"]["code"] == (
        "benchmark.authoring.request_invalid"
    )
    status, unsupported = _request(
        address,
        "GET",
        "/studio/benchmark-authoring/content/"
        f"{resource['contentIdentity']}",
    )
    assert status == 404
    status, forbidden_origin = _request(
        address,
        "GET",
        "/studio/benchmark-authoring/drafts",
        origin="https://attacker.invalid",
    )
    assert status == 403
    assert forbidden_origin["error"]["code"] == "studio.http.forbidden"

    connection = http.client.HTTPConnection(*address, timeout=5)
    try:
        connection.request(
            "GET",
            "/studio/benchmark-authoring/drafts",
            headers={"Host": "attacker.invalid"},
        )
        response = connection.getresponse()
        assert response.status == 403
        host_error = json.loads(response.read().decode("utf-8"))
        assert host_error["error"]["code"] == "studio.http.forbidden"
    finally:
        connection.close()

    connection = http.client.HTTPConnection(*address, timeout=5)
    try:
        connection.request(
            "POST",
            "/studio/benchmark-authoring/drafts",
            body=b"",
            headers={
                "Content-Type": "application/json",
                "Content-Length": str(2 * 1024 * 1024 + 1),
            },
        )
        response = connection.getresponse()
        assert response.status == 413
        body_error = json.loads(response.read().decode("utf-8"))
        assert body_error["error"]["code"] == "studio.http.body_too_large"
    finally:
        connection.close()


def test_authoring_content_http_upload_read_replace_remove_and_limits(
    benchmark_http_server: dict[str, Any],
) -> None:
    """Exercise owner-scoped raw writes and exact safe GET/HEAD reads."""
    address = benchmark_http_server["address"]
    status, created = _request(
        address,
        "POST",
        "/studio/benchmark-authoring/drafts",
        {
            "schemaVersion": 1,
            "clientRequestId": "content-http-create",
            "name": "Content HTTP Draft",
            "source": {
                "kind": "template",
                "template": "minimal",
                "publisher": "tests",
                "packageName": "content-http",
                "version": "0.1.0",
            },
        },
    )
    assert status == 201
    draft_id = created["draft"]["draftId"]
    base_revision_id = created["revision"]["revisionId"]
    resource_id = "large-fixture"
    upload_bytes = b"x" * (2 * 1024 * 1024 + 1)
    upload_query = urlencode(
        {
            "schemaVersion": "1",
            "clientRequestId": "content-http-upload",
            "baseRevisionId": base_revision_id,
            "kind": "asset",
            "path": "assets/\u6d4b\u8bd5.txt",
        }
    )
    upload_path = (
        f"/api/studio/benchmark-authoring/drafts/{draft_id}"
        f"/resources/{resource_id}/upload?{upload_query}"
    )
    status, raw, headers = _binary_request(
        address,
        "POST",
        upload_path,
        body=upload_bytes,
        content_type="text/plain; charset=utf-8",
        origin="http://127.0.0.1:5173",
    )
    assert status == 201
    assert headers["content-type"] == "application/json; charset=utf-8"
    uploaded = json.loads(raw.decode("utf-8"))
    assert uploaded["operation"] == "upload"
    assert uploaded["resource"]["size"] == len(upload_bytes)
    upload_revision_id = uploaded["revision"]["revisionId"]

    content_path = (
        f"/studio/benchmark-authoring/drafts/{draft_id}"
        f"/revisions/{upload_revision_id}/resources/{resource_id}/content"
    )
    status, body, content_headers = _binary_request(
        address,
        "GET",
        content_path,
        origin="http://127.0.0.1:5173",
    )
    assert status == 200
    assert body == upload_bytes
    assert content_headers["content-length"] == str(len(upload_bytes))
    assert content_headers["content-type"] == "text/plain; charset=utf-8"
    assert content_headers["content-disposition"] == (
        'attachment; filename="large-fixture"'
    )
    assert content_headers["cache-control"] == "private, no-store"
    assert content_headers["x-content-type-options"] == "nosniff"
    status, body, head_headers = _binary_request(
        address,
        "HEAD",
        content_path,
    )
    assert status == 200
    assert body == b""
    assert head_headers["content-length"] == str(len(upload_bytes))

    replace_query = urlencode(
        {
            "schemaVersion": "1",
            "clientRequestId": "content-http-replace",
            "baseRevisionId": upload_revision_id,
        }
    )
    replacement = b"<svg><script>unsafe if inline</script></svg>"
    replace_path = (
        f"/studio/benchmark-authoring/drafts/{draft_id}"
        f"/resources/{resource_id}/replace?{replace_query}"
    )
    status, raw, _headers = _binary_request(
        address,
        "POST",
        replace_path,
        body=replacement,
        content_type="image/svg+xml",
    )
    assert status == 201
    replaced = json.loads(raw.decode("utf-8"))
    replace_revision_id = replaced["revision"]["revisionId"]
    assert replaced["resource"]["path"] == "assets/\u6d4b\u8bd5.txt"

    status, old_body, _headers = _binary_request(
        address,
        "GET",
        content_path,
    )
    assert status == 200
    assert old_body == upload_bytes
    replacement_content_path = (
        f"/studio/benchmark-authoring/drafts/{draft_id}"
        f"/revisions/{replace_revision_id}"
        f"/resources/{resource_id}/content"
    )
    status, replacement_body, replacement_headers = _binary_request(
        address,
        "GET",
        replacement_content_path,
    )
    assert status == 200
    assert replacement_body == replacement
    assert replacement_headers["content-type"] == "image/svg+xml"
    assert replacement_headers["content-disposition"].startswith("attachment;")

    remove_query = urlencode(
        {
            "schemaVersion": "1",
            "clientRequestId": "content-http-remove",
            "baseRevisionId": replace_revision_id,
        }
    )
    remove_path = (
        f"/studio/benchmark-authoring/drafts/{draft_id}"
        f"/resources/{resource_id}/remove?{remove_query}"
    )
    status, raw, _headers = _binary_request(
        address,
        "POST",
        remove_path,
        body=b"",
    )
    assert status == 201
    removed = json.loads(raw.decode("utf-8"))
    assert removed["removedResourceId"] == resource_id
    removed_revision_id = removed["revision"]["revisionId"]
    status, raw, _headers = _binary_request(
        address,
        "GET",
        (
            f"/studio/benchmark-authoring/drafts/{draft_id}"
            f"/revisions/{removed_revision_id}"
            f"/resources/{resource_id}/content"
        ),
    )
    assert status == 404
    assert json.loads(raw.decode("utf-8"))["error"]["code"] == (
        "benchmark.authoring.resource_not_found"
    )

    status, raw, _headers = _binary_request(
        address,
        "POST",
        upload_path,
        body=upload_bytes,
        content_type="text/plain; charset=utf-8",
    )
    assert status == 200
    upload_retry = json.loads(raw.decode("utf-8"))
    assert upload_retry["created"] is False
    assert upload_retry["revision"]["revisionId"] == upload_revision_id
    assert upload_retry["draft"]["currentRevisionId"] == removed_revision_id

    stale_query = urlencode(
        {
            "schemaVersion": "1",
            "clientRequestId": "content-http-new-stale",
            "baseRevisionId": upload_revision_id,
            "kind": "asset",
            "path": "assets/stale.txt",
        }
    )
    status, raw, _headers = _binary_request(
        address,
        "POST",
        (
            f"/studio/benchmark-authoring/drafts/{draft_id}"
            f"/resources/stale-asset/upload?{stale_query}"
        ),
        body=b"must not advance",
        content_type="text/plain",
    )
    assert status == 409
    stale = json.loads(raw.decode("utf-8"))
    assert stale["error"]["code"] == "benchmark.authoring.revision_conflict"
    assert stale["error"]["currentRevisionId"] == removed_revision_id

    status, raw, _headers = _binary_request(
        address,
        "GET",
        upload_path,
    )
    assert status == 405
    assert json.loads(raw.decode("utf-8"))["error"]["code"] == (
        "studio.http.method_not_allowed"
    )


def test_authoring_content_http_rejects_ambiguous_framing_and_metadata(
    benchmark_http_server: dict[str, Any],
) -> None:
    """Reject unsafe query, length, transfer, method, and origin inputs."""
    address = benchmark_http_server["address"]
    status, created = _request(
        address,
        "POST",
        "/studio/benchmark-authoring/drafts",
        {
            "schemaVersion": 1,
            "clientRequestId": "content-negative-create",
            "name": "Content Negative Draft",
            "source": {
                "kind": "template",
                "template": "minimal",
                "publisher": "tests",
                "packageName": "content-negative",
                "version": "0.1.0",
            },
        },
    )
    assert status == 201
    draft_id = created["draft"]["draftId"]
    revision_id = created["revision"]["revisionId"]
    base_query = urlencode(
        {
            "schemaVersion": "1",
            "clientRequestId": "negative-upload",
            "baseRevisionId": revision_id,
            "kind": "asset",
            "path": "assets/fixture.txt",
        }
    )
    route = (
        f"/studio/benchmark-authoring/drafts/{draft_id}"
        f"/resources/negative-asset/upload?{base_query}"
    )
    status, raw, _headers = _binary_request(
        address,
        "POST",
        route + "&contentIdentity=benchmark-content-" + "a" * 64,
        body=b"fixture",
        content_type="text/plain",
    )
    assert status == 400
    assert "contentIdentity" not in raw.decode("utf-8")

    status, raw, _headers = _binary_request(
        address,
        "POST",
        route + "&clientRequestId=duplicate",
        body=b"fixture",
        content_type="text/plain",
    )
    assert status == 400
    assert json.loads(raw.decode("utf-8"))["error"]["code"] == (
        "benchmark.authoring.content_request_invalid"
    )
    status, raw, _headers = _binary_request(
        address,
        "POST",
        route,
        body=b"fixture",
        content_type="text/plain, application/json",
    )
    assert status == 400
    assert b"application/json" not in raw
    status, raw, _headers = _binary_request(
        address,
        "POST",
        route,
        body=b"fixture",
        content_type="text/plain",
        origin="https://attacker.invalid",
    )
    assert status == 403
    assert json.loads(raw.decode("utf-8"))["error"]["code"] == (
        "studio.http.forbidden"
    )

    connection = http.client.HTTPConnection(*address, timeout=5)
    try:
        connection.putrequest("POST", route)
        connection.putheader("Content-Type", "text/plain")
        connection.endheaders()
        response = connection.getresponse()
        assert response.status == 400
        error = json.loads(response.read().decode("utf-8"))
        assert error["error"]["code"] == (
            "benchmark.authoring.content_length_invalid"
        )
    finally:
        connection.close()

    connection = http.client.HTTPConnection(*address, timeout=5)
    try:
        connection.putrequest("POST", route)
        connection.putheader("Content-Type", "text/plain")
        connection.putheader("Transfer-Encoding", "chunked")
        connection.endheaders()
        response = connection.getresponse()
        assert response.status == 400
        error = json.loads(response.read().decode("utf-8"))
        assert error["error"]["code"] == (
            "benchmark.authoring.transfer_encoding_invalid"
        )
    finally:
        connection.close()

    connection = http.client.HTTPConnection(*address, timeout=5)
    try:
        connection.putrequest("POST", route)
        connection.putheader("Content-Type", "application/octet-stream")
        connection.putheader("Content-Length", str(64 * 1024 * 1024 + 1))
        connection.endheaders()
        response = connection.getresponse()
        assert response.status == 413
        error = json.loads(response.read().decode("utf-8"))
        assert error["error"]["code"] == (
            "benchmark.authoring.content_too_large"
        )
    finally:
        connection.close()


def test_empty_catalog_and_invalid_queries_have_stable_http_errors(
    tmp_path: Path,
) -> None:
    """Return an empty page and bounded errors without runtime configuration."""
    agents = SQLiteAgentDocumentRepository(tmp_path / "empty.sqlite3")
    authoring = StudioApplicationService(
        catalog=build_studio_component_catalog(),
        repository=agents,
    )
    catalog = StudioBenchmarkCatalogService()
    profiles = AndroidDeviceProfileResolver()
    service = StudioBenchmarkApplicationService(
        catalog=catalog,
        agents=agents,
        profiles=profiles,
    )
    server = create_http_server(
        "127.0.0.1",
        0,
        application_service=authoring,
        benchmark_composition=StudioBenchmarkComposition(
            service=service,
            catalog=catalog,
            profiles=profiles,
        ),
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    address = ("127.0.0.1", int(server.server_address[1]))
    try:
        status, page = _request(address, "GET", "/studio/benchmarks")
        assert status == 200
        assert page == {"schemaVersion": 1, "items": []}
        status, error = _request(
            address,
            "GET",
            "/studio/benchmarks?limit=0",
        )
        assert status == 400
        assert error["error"]["code"] == "benchmark.catalog.limit_invalid"
        status, missing = _request(
            address,
            "GET",
            "/studio/benchmarks/benchmark-entry-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        )
        assert status == 404
        assert missing["error"]["code"] == "benchmark.catalog.not_found"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
