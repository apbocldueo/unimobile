"""Contract, persistence, safety, and HTTP tests for offline Studio Replay."""

from __future__ import annotations

import hashlib
import http.client
import json
import sqlite3
import threading
import zipfile
from collections.abc import Iterator
from pathlib import Path

import pytest

from tests.graph.helpers import make_golden_graph
from zhixing.studio import (
    SQLiteAgentDocumentRepository,
    StudioApplicationService,
    build_studio_component_catalog,
)
from zhixing.studio.httpd import create_http_server
from zhixing.studio.__main__ import main as studio_main
from zhixing.studio.replay_adapters import (
    LegacyBenchmarkReplayAdapter,
    NativeReplayPackageAdapter,
)
from zhixing.studio.replay_contracts import (
    ReplayArtifactNotFoundError,
    ReplayImportArtifact,
    ReplayImportCandidate,
    ReplayImportError,
)
from zhixing.studio.replay_models import (
    NormalizedReplayMoment,
    ReplayArtifactDescriptor,
    ReplayEvidenceAvailability,
    ReplayEvidenceEnvelope,
    ReplayObservation,
    ReplayRunResultSummary,
    ReplayRunSnapshot,
)
from zhixing.studio.replay_service import build_default_replay_service
from zhixing.studio.replay_storage import (
    ReplayArtifactStore,
    ReplayBundleStore,
    SQLiteReplayRepository,
)


_FIXTURES = Path(__file__).parents[1] / "fixtures" / "studio" / "replay"


def _digest(content: bytes) -> str:
    """Return one prefixed SHA-256 fixture digest.

    Args:
        content (bytes): Fixture content.

    Raises:
        None.

    Returns:
        str: Prefixed digest.
    """
    return "sha256:" + hashlib.sha256(content).hexdigest()


def _artifact(
    suffix: str,
    content: bytes,
    *,
    kind: str = "screenshot",
    content_type: str = "image/png",
    hidden: bool = False,
) -> ReplayArtifactDescriptor:
    """Build one valid deterministic artifact descriptor.

    Args:
        suffix (str): One hexadecimal identity character.
        content (bytes): Expected artifact bytes.
        kind (str): Artifact kind.
        content_type (str): Allowlisted media type.
        hidden (bool): Whether ordinary artifact reads are forbidden.

    Raises:
        ValueError: Fixture fields violate the strict DTO.

    Returns:
        ReplayArtifactDescriptor: Valid descriptor.
    """
    return ReplayArtifactDescriptor(
        artifact_id="artifact-" + suffix * 32,
        kind=kind,
        availability="available",
        content_type=content_type,
        size=len(content),
        sha256=_digest(content),
        provenance="fake_contract_fixture",
        hidden=hidden,
    )


def _envelope(
    run_id: str,
    *,
    artifacts: tuple[ReplayArtifactDescriptor, ...] = (),
    imported_at: int = 10,
    agent_id: str = "fixture-agent",
) -> ReplayEvidenceEnvelope:
    """Build one minimal deterministic Replay envelope.

    Args:
        run_id (str): Stable run identity.
        artifacts (tuple[ReplayArtifactDescriptor, ...]): Artifact metadata.
        imported_at (int): Stable pagination timestamp.
        agent_id (str): Exact owning Agent identity.

    Raises:
        ValueError: Fixture violates Replay contracts.

    Returns:
        ReplayEvidenceEnvelope: Strict fixture envelope.
    """
    first_artifact = artifacts[0].artifact_id if artifacts else None
    return ReplayEvidenceEnvelope(
        run_id=run_id,
        imported_at=imported_at,
        provenance="fake_contract_fixture",
        integrity_state="complete",
        snapshot=ReplayRunSnapshot(
            agent_id=agent_id,
            graph_status="not_captured",
        ),
        result=ReplayRunResultSummary(
            status="success",
            kernel_status="success",
            step_count=1,
            activation_count=1,
            interaction_count=1,
        ),
        moments=(
            NormalizedReplayMoment(
                moment_id=f"moment-{run_id}-1",
                causal_index=0,
                source_kind="agent_graph",
                source_sequence=1,
                kind="start",
                role="reasoning",
                node_id="reasoning",
                node_path="reasoning",
                activation_id="activation-1",
            ),
            NormalizedReplayMoment(
                moment_id=f"moment-{run_id}-2",
                causal_index=1,
                source_kind="agent_graph",
                source_sequence=2,
                kind="complete",
                role="reasoning",
                node_id="reasoning",
                node_path="reasoning",
                activation_id="activation-1",
                observation_id=(
                    "observation-0000" if first_artifact is not None else None
                ),
                artifact_ids=((first_artifact,) if first_artifact else ()),
            ),
        ),
        observations=(
            (
                ReplayObservation(
                    observation_id="observation-0000",
                    sequence=0,
                    interaction_step=0,
                    screenshot_artifact_id=first_artifact,
                    device_id="device-sha256:fixture",
                ),
            )
            if first_artifact is not None
            else ()
        ),
        artifacts=artifacts,
        availability={
            "agentGraph": ReplayEvidenceAvailability(state="not_captured"),
            "screenshots": ReplayEvidenceAvailability(
                state="available" if first_artifact else "not_captured"
            ),
            "prompt": ReplayEvidenceAvailability(state="available"),
        },
    )


def _candidate(
    envelope: ReplayEvidenceEnvelope,
    sources: dict[str, Path],
) -> ReplayImportCandidate:
    """Pair an envelope with explicit trusted direct-file sources.

    Args:
        envelope (ReplayEvidenceEnvelope): Strict Replay evidence.
        sources (dict[str, Path]): Artifact identity to source file.

    Raises:
        KeyError: A descriptor has no source.

    Returns:
        ReplayImportCandidate: Atomic import input.
    """
    descriptors = {item.artifact_id: item for item in envelope.artifacts}
    return ReplayImportCandidate(
        envelope=envelope,
        artifacts={
            identity: ReplayImportArtifact(
                descriptor=descriptors[identity],
                source_path=path,
                trusted_root=path.parent,
            )
            for identity, path in sources.items()
        },
    )


def _write_native_package(
    path: Path,
    envelope: ReplayEvidenceEnvelope,
    contents: dict[str, bytes],
) -> None:
    """Write one deterministic native package for adapter tests.

    Args:
        path (Path): ZIP target.
        envelope (ReplayEvidenceEnvelope): Public envelope.
        contents (dict[str, bytes]): Artifact identity to bytes.

    Raises:
        OSError: Target cannot be written.

    Returns:
        None.
    """
    envelope_bytes = (
        json.dumps(
            envelope.model_dump(
                mode="json",
                by_alias=True,
                exclude_none=True,
            ),
            sort_keys=True,
        )
        + "\n"
    ).encode()
    members: dict[str, bytes] = {"envelope.json": envelope_bytes}
    members.update(
        {f"artifacts/{identity}": content for identity, content in contents.items()}
    )
    manifest = {
        "schemaVersion": 1,
        "kind": "studio_replay_package",
        "runId": envelope.run_id,
        "promptIncluded": False,
        "members": {
            name: {"sha256": _digest(content), "size": len(content)}
            for name, content in sorted(members.items())
        },
    }
    with zipfile.ZipFile(path, "w") as archive:
        for name, content in members.items():
            archive.writestr(name, content)
        archive.writestr("replay-manifest.json", json.dumps(manifest))


def _write_legacy_source(
    root: Path,
    *,
    result: dict | None = None,
    graph_events: list[dict] | None = None,
    observations: list[dict] | None = None,
) -> Path:
    """Write one small legacy compound source.

    Args:
        root (Path): Parent fixture directory.
        result (dict | None): Optional direct Benchmark result override.
        graph_events (list[dict] | None): Optional nested Graph events.
        observations (list[dict] | None): Optional observation records.

    Raises:
        OSError: Fixture files cannot be written.

    Returns:
        Path: Run directory containing the trajectory.
    """
    run_id = "legacy-run"
    run = root / run_id
    run.mkdir(parents=True)
    benchmark = result or {
        "task_run_id": run_id,
        "experiment_id": "experiment-1",
        "task_id": "task-1",
        "agent_id": "agent-1",
        "repeat": 0,
        "outcome": "fail",
        "identities": {},
        "agent_result": {
            "status": "success",
            "kernel_status": "success",
            "activation_count": 1,
            "interaction_count": 1,
        },
        "stages": [
            {"phase": "agent", "status": "success"},
            {"phase": "evaluation", "status": "failure"},
        ],
        "evaluation": {"is_pass": False},
    }
    (run / "benchmark-result.json").write_text(
        json.dumps({"result": benchmark}),
        encoding="utf-8",
    )
    events = graph_events or [
        {
            "sequence": 1,
            "timestamp": 20,
            "kind": "start",
            "node_id": "reasoning",
            "node_path": "reasoning",
            "activation_id": "activation-1",
            "role": "reasoning",
        },
        {
            "sequence": 2,
            "timestamp": 10,
            "kind": "complete",
            "node_id": "reasoning",
            "node_path": "reasoning",
            "activation_id": "activation-1",
            "role": "reasoning",
        },
    ]
    records = [
        {
            "record_index": 1,
            "phase": "agent",
            "lifecycle_events": [
                {
                    "sequence": 1,
                    "timestamp": 30,
                    "phase": "agent",
                    "kind": "start",
                },
                {
                    "sequence": 2,
                    "timestamp": 5,
                    "phase": "agent",
                    "kind": "complete",
                },
            ],
            "agent_graph": {
                "events": events,
                "observations": observations or [],
                "actions": [],
            },
        }
    ]
    (run / "trajectory.jsonl").write_text(
        "\n".join(json.dumps(item) for item in records) + "\n",
        encoding="utf-8",
    )
    return run


def test_fixture_manifest_distinguishes_real_and_fake_evidence() -> None:
    """Require truthful provenance and the key real Android evidence cases."""
    manifest = json.loads(
        (_FIXTURES / "provenance-manifest.json").read_text(encoding="utf-8")
    )
    real = [
        item
        for item in manifest["sources"]
        if item["provenance"] == "real_android_excerpt"
    ]
    fake = [
        item
        for item in manifest["sources"]
        if item["provenance"] == "fake_contract_fixture"
    ]
    assert len(real) >= 4
    assert len(fake) == 1
    facts = {fact for item in real for fact in item["verifiedFacts"]}
    assert {
        "agent_success",
        "agent_failure",
        "feedback",
        "external_component",
        "benchmark_fail",
    } <= facts


def test_legacy_adapter_preserves_causal_nesting_and_independent_outcome(
    tmp_path,
) -> None:
    """Keep lifecycle nesting despite interleaved timestamps and split outcomes."""
    run = _write_legacy_source(tmp_path)
    envelope = LegacyBenchmarkReplayAdapter().load(run).envelope
    assert [item.kind for item in envelope.moments] == [
        "start",
        "start",
        "complete",
        "complete",
    ]
    assert [item.timestamp for item in envelope.moments] == [30, 20, 10, 5]
    assert envelope.result.status == "success"
    assert envelope.benchmark is not None
    assert envelope.benchmark.outcome == "fail"
    assert envelope.snapshot.graph_status == "not_captured"


def test_legacy_adapter_reports_sequence_damage_and_graph_mismatch(tmp_path) -> None:
    """Produce stable diagnostics and reject an inconsistent explicit graph."""
    run = _write_legacy_source(
        tmp_path,
        graph_events=[
            {"sequence": 1, "kind": "start"},
            {"sequence": 3, "kind": "complete"},
            {"sequence": 2, "kind": "complete"},
        ],
    )
    envelope = LegacyBenchmarkReplayAdapter().load(run).envelope
    assert envelope.integrity_state == "partial"
    assert {item.code for item in envelope.integrity} == {
        "studio.replay.sequence_gap",
        "studio.replay.sequence_order",
    }

    result_path = run / "benchmark-result.json"
    result = json.loads(result_path.read_text())
    result["result"]["identities"]["agent_graph"] = "sha256:" + "0" * 64
    result_path.write_text(json.dumps(result))
    graph = tmp_path / "graph.json"
    graph.write_text(
        json.dumps(make_golden_graph().model_dump(mode="json", exclude_none=True))
    )
    with pytest.raises(ReplayImportError) as captured:
        LegacyBenchmarkReplayAdapter().load(run, graph_snapshot=graph)
    assert captured.value.code == "studio.replay.graph_identity_mismatch"


def test_legacy_adapter_rejects_traversal_reference(tmp_path) -> None:
    """Reject a legacy artifact path before joining it to a trusted root."""
    run = _write_legacy_source(
        tmp_path,
        observations=[
            {
                "sequence": 0,
                "interaction_step": 0,
                "screenshot_artifact": "../private.png",
            }
        ],
    )
    with pytest.raises(ReplayImportError) as captured:
        LegacyBenchmarkReplayAdapter().load(run, artifact_root=tmp_path)
    assert captured.value.code == "studio.replay.path_unsafe"


def test_repository_artifact_restart_pagination_and_bundle_round_trip(
    tmp_path,
) -> None:
    """Persist copied content across restart and export a verifiable package."""
    database = tmp_path / "studio.sqlite3"
    root = tmp_path / "artifacts"
    repository = SQLiteReplayRepository(database)
    store = ReplayArtifactStore(root, repository)
    image = b"fixture-png"
    prompt = b"hidden prompt"
    image_descriptor = _artifact("1", image)
    prompt_descriptor = _artifact(
        "2",
        prompt,
        kind="prompt",
        content_type="text/plain",
        hidden=True,
    )
    image_source = tmp_path / "image.png"
    prompt_source = tmp_path / "prompt.txt"
    image_source.write_bytes(image)
    prompt_source.write_bytes(prompt)
    envelope = _envelope(
        "run-a",
        artifacts=(image_descriptor, prompt_descriptor),
        imported_at=20,
    )
    store.import_candidate(
        _candidate(
            envelope,
            {
                image_descriptor.artifact_id: image_source,
                prompt_descriptor.artifact_id: prompt_source,
            },
        )
    )
    image_source.unlink()
    prompt_source.unlink()

    restarted_repository = SQLiteReplayRepository(database)
    restarted_store = ReplayArtifactStore(root, restarted_repository)
    metadata, stream = restarted_store.open_artifact(
        "run-a",
        image_descriptor.artifact_id,
    )
    assert metadata.sha256 == _digest(image)
    assert stream.read() == image
    stream.close()
    with pytest.raises(ReplayArtifactNotFoundError):
        restarted_store.open_artifact("run-a", prompt_descriptor.artifact_id)
    with pytest.raises(ReplayArtifactNotFoundError):
        restarted_store.open_artifact("run-b", image_descriptor.artifact_id)

    second = _envelope("run-b", imported_at=10)
    restarted_store.import_candidate(_candidate(second, {}))
    first_page = restarted_repository.list_replays(limit=1)
    assert [item.run_id for item in first_page.items] == ["run-a"]
    assert first_page.next_cursor is not None
    assert [
        item.run_id
        for item in restarted_repository.list_replays(
            limit=1,
            cursor=first_page.next_cursor,
        ).items
    ] == ["run-b"]
    other_agent = _envelope(
        "run-c",
        imported_at=30,
        agent_id="other-agent",
    )
    restarted_store.import_candidate(_candidate(other_agent, {}))
    filtered = restarted_repository.list_replays(
        limit=10,
        agent_id="fixture-agent",
    )
    assert [item.run_id for item in filtered.items] == ["run-a", "run-b"]
    assert filtered.next_cursor is None
    with pytest.raises(ValueError, match="Agent filter"):
        restarted_repository.list_replays(limit=10, agent_id="bad identity")

    bundle_store = ReplayBundleStore(restarted_repository, restarted_store)
    bundle = bundle_store.write_bundle("run-a", tmp_path / "run-a.zip")
    assert bundle_store.verify_bundle(bundle) is True
    native = NativeReplayPackageAdapter().load(bundle)
    assert native.envelope.availability["prompt"].state == "excluded"
    assert native.envelope.artifacts[1].availability == "excluded"
    assert prompt_descriptor.artifact_id not in native.artifacts


def test_native_adapter_sanitizes_payload_device_and_host_path(tmp_path) -> None:
    """Redact package secrets and host paths and hash a raw device identity."""
    envelope = _envelope("native-safe")
    envelope = envelope.model_copy(
        update={
            "moments": (
                envelope.moments[0].model_copy(
                    update={
                        "payload": {
                            "api_key": "SECRET_CANARY_DO_NOT_PERSIST",
                            "note": "/private/replay-canary",
                        }
                    }
                ),
            ),
            "observations": (
                ReplayObservation(
                    observation_id="observation-safe",
                    sequence=0,
                    interaction_step=0,
                    device_id="RAW_SERIAL_CANARY",
                ),
            ),
        }
    )
    package = tmp_path / "native.zip"
    _write_native_package(package, envelope, {})
    imported = NativeReplayPackageAdapter().load(package).envelope
    serialized = json.dumps(imported.model_dump(mode="json", by_alias=True))
    assert "SECRET_CANARY_DO_NOT_PERSIST" not in serialized
    assert "/private/replay-canary" not in serialized
    assert "RAW_SERIAL_CANARY" not in serialized
    assert imported.observations[0].device_id.startswith("device-sha256:")
    database = tmp_path / "studio.sqlite3"
    build_default_replay_service(database).import_native_package(package)
    connection = sqlite3.connect(database)
    try:
        database_dump = "\n".join(connection.iterdump())
    finally:
        connection.close()
    assert "SECRET_CANARY_DO_NOT_PERSIST" not in database_dump
    assert "/private/replay-canary" not in database_dump
    assert "RAW_SERIAL_CANARY" not in database_dump


def test_native_adapter_rejects_hash_and_content_type(tmp_path) -> None:
    """Reject corrupt members and non-allowlisted artifact media types."""
    content = b"binary"
    descriptor = _artifact(
        "5",
        content,
        content_type="application/octet-stream",
    )
    envelope = _envelope("native-invalid", artifacts=(descriptor,))
    package = tmp_path / "invalid.zip"
    _write_native_package(package, envelope, {descriptor.artifact_id: content})
    with pytest.raises(ReplayImportError) as unsupported:
        NativeReplayPackageAdapter().load(package)
    assert unsupported.value.code == "studio.replay.content_type_unsupported"

    valid_descriptor = _artifact("6", content, content_type="text/plain")
    valid_envelope = _envelope(
        "native-corrupt",
        artifacts=(valid_descriptor,),
    )
    corrupt_package = tmp_path / "corrupt.zip"
    _write_native_package(
        corrupt_package,
        valid_envelope,
        {valid_descriptor.artifact_id: content},
    )
    with zipfile.ZipFile(corrupt_package, "r") as archive:
        package_members = {
            name: archive.read(name)
            for name in archive.namelist()
            if name != "replay-manifest.json"
        }
        corrupt_manifest = json.loads(archive.read("replay-manifest.json"))
    member = f"artifacts/{valid_descriptor.artifact_id}"
    corrupt_manifest["members"][member]["sha256"] = "sha256:" + "0" * 64
    with zipfile.ZipFile(corrupt_package, "w") as archive:
        for name, member_content in package_members.items():
            archive.writestr(name, member_content)
        archive.writestr("replay-manifest.json", json.dumps(corrupt_manifest))
    with pytest.raises(ReplayImportError) as corrupt:
        NativeReplayPackageAdapter().load(corrupt_package)
    assert corrupt.value.code in {
        "studio.replay.hash_mismatch",
        "studio.replay.members_undeclared",
    }


def test_explicit_local_cli_imports_compound_source(
    tmp_path,
    monkeypatch,
    capsys,
) -> None:
    """Import only the explicitly named local source through the CLI boundary."""
    run = _write_legacy_source(tmp_path / "source")
    database = tmp_path / "studio.sqlite3"
    monkeypatch.chdir(tmp_path)
    studio_main(
        [
            "replay-import",
            "--legacy-run",
            str(run),
            "--database",
            str(database),
            "--provenance",
            "fake_contract_fixture",
        ]
    )
    output = json.loads(capsys.readouterr().out)
    assert output["runId"] == "legacy-run"
    assert output["provenance"] == "fake_contract_fixture"
    assert SQLiteReplayRepository(database).get_replay("legacy-run").run_id == (
        "legacy-run"
    )


def test_artifact_import_is_atomic_and_detects_symlink_and_corruption(
    tmp_path,
) -> None:
    """Leave no row on unsafe source failure and detect managed corruption."""
    database = tmp_path / "studio.sqlite3"
    repository = SQLiteReplayRepository(database)
    store = ReplayArtifactStore(tmp_path / "artifacts", repository)
    content = b"safe"
    descriptor = _artifact("3", content, content_type="text/plain")
    target = tmp_path / "target.txt"
    target.write_bytes(content)
    symlink = tmp_path / "link.txt"
    symlink.symlink_to(target)
    envelope = _envelope("run-symlink", artifacts=(descriptor,))
    with pytest.raises(ReplayImportError) as captured:
        store.import_candidate(
            _candidate(envelope, {descriptor.artifact_id: symlink})
        )
    assert captured.value.code == "studio.replay.artifact_source_unsafe"
    assert repository.list_replays().items == ()

    source = tmp_path / "source.txt"
    source.write_bytes(content)
    store.import_candidate(_candidate(envelope, {descriptor.artifact_id: source}))
    managed = (
        store.root / "runs" / envelope.run_id / "artifacts" / descriptor.artifact_id
    )
    managed.write_bytes(b"corrupt")
    with pytest.raises(ReplayImportError) as corrupted:
        store.open_artifact(envelope.run_id, descriptor.artifact_id)
    assert corrupted.value.code == "studio.replay.artifact_corrupt"


@pytest.fixture
def replay_http_server(tmp_path) -> Iterator[tuple[tuple[str, int], bytes, str]]:
    """Run a Replay-enabled real HTTP server with one imported resource.

    Args:
        tmp_path (Path): Pytest temporary directory.

    Raises:
        OSError: Storage or socket setup fails.

    Yields:
        Iterator[tuple[tuple[str, int], bytes, str]]: Address, content, artifact.
    """
    database = tmp_path / "studio.sqlite3"
    replay = build_default_replay_service(database)
    content = b"opaque-image"
    descriptor = _artifact("4", content)
    source = tmp_path / "image.png"
    source.write_bytes(content)
    replay.artifact_store.import_candidate(
        _candidate(
            _envelope("http-run", artifacts=(descriptor,)),
            {descriptor.artifact_id: source},
        )
    )
    service = StudioApplicationService(
        catalog=build_studio_component_catalog(),
        repository=SQLiteAgentDocumentRepository(database),
        replay_service=replay,
    )
    server = create_http_server(
        "127.0.0.1",
        0,
        application_service=service,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield (
            ("127.0.0.1", int(server.server_address[1])),
            content,
            descriptor.artifact_id,
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


def _http_get(
    address: tuple[str, int],
    path: str,
) -> tuple[int, dict[str, str], bytes]:
    """Read one Replay HTTP resource.

    Args:
        address (tuple[str, int]): Host and port.
        path (str): Request path.

    Raises:
        OSError: HTTP transport fails.

    Returns:
        tuple[int, dict[str, str], bytes]: Status, headers, and body.
    """
    connection = http.client.HTTPConnection(*address, timeout=5)
    try:
        connection.request("GET", path)
        response = connection.getresponse()
        return response.status, dict(response.getheaders()), response.read()
    finally:
        connection.close()


def test_replay_http_list_detail_artifact_bundle_and_not_found(
    replay_http_server,
) -> None:
    """Expose only opaque read contracts under the public API prefix."""
    address, content, artifact_id = replay_http_server
    status, _headers, body = _http_get(address, "/api/studio/replays?limit=1")
    page = json.loads(body)
    assert status == 200
    assert page["items"][0]["runId"] == "http-run"
    assert page["items"][0]["agentStatus"] == "success"

    status, _headers, body = _http_get(
        address,
        "/api/studio/replays?limit=1&agentId=fixture-agent",
    )
    assert status == 200
    assert json.loads(body)["items"][0]["agentId"] == "fixture-agent"

    status, _headers, body = _http_get(
        address,
        "/api/studio/replays?limit=1&agentId=bad%20identity",
    )
    assert status == 400
    assert json.loads(body)["error"]["code"] == "studio.request.invalid"

    status, _headers, body = _http_get(
        address,
        "/api/studio/replays/http-run",
    )
    envelope = json.loads(body)
    assert status == 200
    serialized = json.dumps(envelope)
    assert str(Path.cwd()) not in serialized
    assert "storage_ref" not in serialized

    status, headers, body = _http_get(
        address,
        f"/api/studio/replays/http-run/artifacts/{artifact_id}",
    )
    assert status == 200
    assert headers["Content-Type"] == "image/png"
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert body == content

    status, headers, body = _http_get(
        address,
        "/api/studio/replays/http-run/bundle",
    )
    assert status == 200
    assert headers["Content-Type"] == "application/zip"
    bundle = Path(headers["Content-Disposition"].split('"')[1])
    assert bundle.name == "http-run.replay.zip"
    assert body.startswith(b"PK")

    status, _headers, body = _http_get(
        address,
        f"/api/studio/replays/other-run/artifacts/{artifact_id}",
    )
    assert status == 404
    assert json.loads(body)["error"]["code"] == "studio.replay.not_found"
