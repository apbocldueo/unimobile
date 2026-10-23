"""Clean-wheel acceptance for Studio Benchmark managed export downloads."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tests.studio.test_benchmark_publication_replay import (
    _publisher,
    _ready_core_result,
)


@pytest.mark.packaging_acceptance
def test_installed_wheel_serves_verified_benchmark_export_contract(
    isolated_install: tuple[Path, Path, dict[str, str]],
) -> None:
    """Exercise packaged GET/HEAD export and read-time integrity closure.

    Args:
        isolated_install: Isolated Python, unrelated working directory, and
            clean subprocess environment containing the built wheel.

    Raises:
        AssertionError: Publication setup, import isolation, HTTP parity, or
            managed-content integrity closure fails.

    Returns:
        None.
    """
    python, workdir, clean_env = isolated_install
    service, repository, suite, task = _ready_core_result(workdir)
    preparer, _publications, _artifacts, publisher = _publisher(
        workdir,
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
    publisher.publish(
        suite.experiment_id,
        task.task_run_id,
        timestamp=14,
    )
    service._publication_enabled = True

    script = r"""
import http.client
import json
import pathlib
import sys
import threading
import zipfile

import zhixing
from zhixing.studio.benchmark_artifacts import (
    LocalStudioBenchmarkManagedArtifactStore,
)
from zhixing.studio.benchmark_composition import StudioBenchmarkComposition
from zhixing.studio.benchmark_experiment_repository import (
    SQLiteStudioBenchmarkExperimentRepository,
)
from zhixing.studio.benchmark_experiment_service import (
    StudioBenchmarkExperimentApplicationService,
)
from zhixing.studio.benchmark_publication_repository import (
    SQLiteStudioBenchmarkPublicationRepository,
)
from zhixing.studio.httpd import create_http_server
from zhixing.studio.replay_storage import default_studio_artifact_directory

database = pathlib.Path(sys.argv[1])
experiment_id = sys.argv[2]
task_run_id = sys.argv[3]
assert pathlib.Path(zhixing.__file__).resolve().is_relative_to(
    pathlib.Path(sys.prefix).resolve()
)
repository = SQLiteStudioBenchmarkExperimentRepository(database)
publications = SQLiteStudioBenchmarkPublicationRepository(database)
artifacts = LocalStudioBenchmarkManagedArtifactStore(
    default_studio_artifact_directory(database),
    publications,
)
experiments = StudioBenchmarkExperimentApplicationService(
    definitions=None,
    repository=repository,
    publication_repository=publications,
    publication_enabled=True,
)
composition = StudioBenchmarkComposition(
    service=None,
    catalog=None,
    profiles=None,
    experiments=experiments,
    repository=repository,
    publications=publications,
    artifacts=artifacts,
)
server = create_http_server(
    "127.0.0.1",
    0,
    application_service=None,
    benchmark_composition=composition,
)
thread = threading.Thread(target=server.serve_forever, daemon=True)
thread.start()
address = ("127.0.0.1", int(server.server_address[1]))


def request(path, method="GET"):
    '''Issue one local managed-content request.

    Args:
        path: Exact public Studio capability.
        method: GET or HEAD.

    Raises:
        OSError: The local HTTP exchange fails.

    Returns:
        Response status, normalized headers, and body bytes.
    '''
    connection = http.client.HTTPConnection(*address, timeout=5)
    connection.request(
        method,
        path,
        headers={
            "Host": "127.0.0.1",
            "Origin": "http://127.0.0.1:5173",
        },
    )
    response = connection.getresponse()
    body = response.read()
    headers = {key.lower(): value for key, value in response.getheaders()}
    status = response.status
    connection.close()
    return status, headers, body


try:
    publication = publications.get_publication(experiment_id)
    assert publication is not None
    records = publications.list_artifacts(experiment_id)
    by_kind = {record.descriptor.kind: record for record in records}
    report = by_kind["experiment_report"]
    bundle = by_kind["experiment_bundle"]
    manifest = by_kind["studio_publication_manifest"]
    trajectory = by_kind["task_trajectory"]
    routes = {
        "report": (
            f"/studio/benchmark-experiments/{experiment_id}/report",
            report,
        ),
        "bundle": (
            f"/studio/benchmark-experiments/{experiment_id}/bundle",
            bundle,
        ),
        "manifest": (
            f"/studio/benchmark-experiments/{experiment_id}/artifacts/"
            f"{manifest.descriptor.artifact_id}",
            manifest,
        ),
        "trajectory": (
            f"/studio/benchmark-experiments/{experiment_id}/task-runs/"
            f"{task_run_id}/artifacts/{trajectory.descriptor.artifact_id}",
            trajectory,
        ),
    }
    bodies = {}
    for name, (route, record) in routes.items():
        get_status, get_headers, get_body = request(route)
        head_status, head_headers, head_body = request(route, "HEAD")
        assert get_status == head_status == 200
        assert head_body == b""
        assert len(get_body) == record.descriptor.size
        for header in (
            "content-type",
            "content-length",
            "content-disposition",
            "cache-control",
            "x-content-type-options",
        ):
            assert head_headers[header] == get_headers[header]
        assert head_headers["access-control-allow-origin"] == (
            "http://127.0.0.1:5173"
        )
        assert "Content-Length" in (
            head_headers["access-control-expose-headers"]
        )
        bodies[name] = get_body

    assert json.loads(bodies["report"])["experiment_id"] == experiment_id
    manifest_payload = json.loads(bodies["manifest"])
    assert manifest_payload["experimentId"] == experiment_id
    assert manifest_payload["members"]
    assert manifest_payload["excludedEvidence"] == [
        {
            "availability": "hidden",
            "kind": "prompt",
            "reason": "hidden_by_default_policy",
        }
    ]
    bundle_path = database.parent / "downloaded-bundle.zip"
    bundle_path.write_bytes(bodies["bundle"])
    with zipfile.ZipFile(bundle_path) as archive:
        assert archive.testzip() is None

    missing_path = artifacts.storage_path(trajectory)
    missing_path.unlink()
    missing_status, _missing_headers, missing_body = request(
        routes["trajectory"][0]
    )
    assert missing_status == 404
    assert json.loads(missing_body)["error"]["code"] == (
        "benchmark.artifact.missing"
    )

    corrupt_path = artifacts.storage_path(report)
    with corrupt_path.open("ab") as stream:
        stream.write(b"tamper")
    corrupt_status, _corrupt_headers, corrupt_body = request(
        routes["report"][0]
    )
    assert corrupt_status == 409
    assert json.loads(corrupt_body)["error"]["code"] == (
        "benchmark.artifact.corrupt"
    )
finally:
    server.shutdown()
    server.server_close()
    thread.join(timeout=5)
"""
    completed = subprocess.run(
        [
            str(python),
            "-c",
            script,
            str(workdir / "studio.sqlite3"),
            suite.experiment_id,
            task.task_run_id,
        ],
        cwd=workdir,
        env=clean_env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
