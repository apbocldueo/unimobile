"""Repository-independent installed Stage 5.6B Benchmark acceptance."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
EXTERNAL_DISTRIBUTION = (
    ROOT / "tests" / "packaging" / "fixtures" / "layered_acceptance_benchmark"
)


@pytest.mark.packaging_acceptance
def test_installed_external_package_completes_actual_studio_chain(
    isolated_install: tuple[Path, Path, dict[str, str]],
    tmp_path: Path,
) -> None:
    """Build/install an external Package and execute installed Studio.

    Args:
        isolated_install: Isolated core-wheel Python, unrelated cwd, and env.
        tmp_path: Build output outside the installed runtime workspace.

    Raises:
        AssertionError: Build, isolation, lifecycle, integrity, or canaries fail.

    Returns:
        None.
    """
    python, workdir, clean_env = isolated_install
    distribution_output = tmp_path / "external-dist"
    distribution_output.mkdir()
    built = subprocess.run(
        [
            str(python),
            "-m",
            "pip",
            "wheel",
            "--no-deps",
            "--no-build-isolation",
            "--wheel-dir",
            str(distribution_output),
            str(EXTERNAL_DISTRIBUTION),
        ],
        cwd=tmp_path,
        env=clean_env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert built.returncode == 0, built.stdout + built.stderr
    external_wheels = tuple(distribution_output.glob("*.whl"))
    assert len(external_wheels) == 1
    installed = subprocess.run(
        [str(python), "-m", "pip", "install", str(external_wheels[0])],
        cwd=workdir,
        env=clean_env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert installed.returncode == 0, installed.stdout + installed.stderr
    scenario_root = workdir / "layered-acceptance"
    scenario_root.mkdir()
    script = r"""
import hashlib
import http.client
import importlib.metadata
import importlib.resources
import json
import pathlib
import socket
import sys
import threading
import time

import zhixing
import zhixing.studio.device_profiles as device_profile_module
from zhixing.catalog.builtins import BuiltInComponentResolver
from zhixing.studio import (
    SQLiteAgentDocumentRepository,
    StudioApplicationService,
    StudioComponentAvailability,
    build_default_studio_benchmark_composition,
    build_default_replay_service,
    build_studio_component_catalog,
)
from zhixing.studio.device_profiles import (
    AndroidDeviceProfile,
    AndroidDeviceProfileResolver,
)
from zhixing.studio.httpd import create_http_server
from zhixing.studio.run_execution import ProductionComponentResolverFactory


runtime_root = pathlib.Path(sys.argv[1]).resolve()
repository_root = pathlib.Path(sys.argv[2]).resolve()
installed_root = pathlib.Path(sys.prefix).resolve()
assert pathlib.Path(zhixing.__file__).resolve().is_relative_to(installed_root)
assert not any(
    pathlib.Path(item or ".").resolve() == repository_root
    for item in sys.path
)
calls = {
    "adb_discovery": 0,
    "real_device_construction": 0,
    "external_network": 0,
    "model_resolution": 0,
    "secret_resolution": 0,
    "repository_source_fallback": 0,
}


def forbidden(name):
    '''Build one counted fail-fast forbidden-boundary canary.

    Args:
        name: Stable canary counter key.

    Returns:
        Callable that records and rejects one forbidden invocation.
    '''
    def canary(*args, **kwargs):
        '''Record and reject one forbidden installed-product effect.'''
        del args, kwargs
        calls[name] += 1
        raise AssertionError("forbidden acceptance boundary crossed")

    return canary


class ShellResult:
    '''Bounded fake Android shell response.'''

    def __init__(self, output="", exit_code=0):
        '''Store deterministic shell output and exit status.'''
        self.output = output
        self.exit_code = exit_code
        self.error = ""


class FakeDevice:
    '''Explicit fake authority used by installed Studio only.'''

    serial = "fake-installed-acceptance"
    platform = "android"
    locale = "en-US"
    orientation = "portrait"
    w = 100
    h = 200
    app_package_names = {"files": "com.android.documentsui"}

    def __init__(self):
        '''Create empty call and installed-file evidence.'''
        self.calls = []
        self.files = set()

    def shell(self, command, error_raise=False):
        '''Return deterministic Package-plugin shell output.'''
        del error_raise
        self.calls.append(("shell", command))
        if command.startswith("rm -rf "):
            self.files.clear()
            return ShellResult("ok")
        if command.startswith("ls "):
            target = command[3:].strip()
            if target == "/storage/emulated/0/Download" or target in self.files:
                return ShellResult(target)
            return ShellResult("No such file or directory", 1)
        return ShellResult("ok")

    def push_file(self, local_path, device_path):
        '''Expose one distribution-materialized resource to the fake evaluator.'''
        assert pathlib.Path(local_path).is_file()
        self.calls.append(("push_file", pathlib.Path(local_path).name, device_path))
        self.files.add(device_path)
        return True

    def screenshot(self, path):
        '''Write one bounded synthetic observation when requested.'''
        pathlib.Path(path).write_bytes(b"\x89PNG\r\n\x1a\n" + b"x" * 64)
        self.calls.append(("screenshot",))
        return path

    def go_home(self):
        '''Record a fake HOME action.'''
        self.calls.append(("home",))

    def go_back(self):
        '''Record a fake BACK action.'''
        self.calls.append(("back",))

    def wait(self, seconds):
        '''Record a fake wait without sleeping.'''
        self.calls.append(("wait", seconds))


class FakePlannerLLM:
    '''Pure planner dependency that never resolves a model or network.'''

    def __init__(self):
        '''Create an invocation counter.'''
        self.calls = 0

    def generate(self, prompt, images=None):
        '''Return one parser-compatible terminal action.'''
        del prompt, images
        self.calls += 1
        return '{"action":"DONE","params":{},"thought":"fixture complete"}'


original_create_connection = socket.create_connection


def loopback_only(address, *args, **kwargs):
    '''Permit only the acceptance loopback HTTP transport.'''
    host = str(address[0]).lower()
    if host not in {"127.0.0.1", "localhost", "::1"}:
        calls["external_network"] += 1
        raise AssertionError("external network is forbidden")
    return original_create_connection(address, *args, **kwargs)


original_dependency = BuiltInComponentResolver._dependency


def guarded_dependency(self, name, specification):
    '''Count only an attempted unresolved model dependency.'''
    if name in {"llm", "llm_client"} and name not in self.dependency_provider:
        calls["model_resolution"] += 1
        raise AssertionError("model resolution is forbidden")
    return original_dependency(self, name, specification)


device_profile_module.AndroidDevice.list_device_states = classmethod(
    forbidden("adb_discovery")
)
device_profile_module.AndroidDevice.__init__ = forbidden(
    "real_device_construction"
)
socket.create_connection = loopback_only
BuiltInComponentResolver._dependency = guarded_dependency

distribution = importlib.metadata.distribution(
    "zhixing-layered-acceptance-benchmark"
)
manifest_member = next(
    item
    for item in distribution.files
    if str(item).replace("\\", "/")
    == "layered_acceptance_benchmark/package/benchmark.yaml"
)
manifest_path = pathlib.Path(distribution.locate_file(manifest_member)).resolve()
assert manifest_path.is_relative_to(installed_root)
agent_document = json.loads(
    importlib.resources.files("layered_acceptance_benchmark")
    .joinpath("agent.json")
    .read_text(encoding="utf-8")
)

database = runtime_root / "studio.sqlite3"
agents = SQLiteAgentDocumentRepository(database)
catalog = build_studio_component_catalog()
# The exact test Catalog must describe the injected fake LLM as available;
# this avoids pretending the optional OpenAI distribution exists in the wheel.
catalog = catalog.model_copy(
    update={
        "catalog_version": f"{catalog.catalog_version}-installed-fake-llm",
        "components": tuple(
            item.model_copy(
                update={
                    "availability": StudioComponentAvailability(available=True),
                    "provider_id": "zhixing.installed-fake-llm",
                }
            )
            if (item.namespace, item.name) == ("llm", "openai_llm")
            else item
            for item in catalog.components
        ),
    }
)
replay_service = build_default_replay_service(database)
authoring = StudioApplicationService(
    catalog=catalog,
    repository=agents,
    replay_service=replay_service,
)
agent, revision = authoring.create_agent(
    "Installed Layered Acceptance Agent",
    initial_document=agent_document,
)
assert revision.compile_snapshot.status == "valid", [
    (item.code, list(item.path))
    for item in revision.compile_snapshot.diagnostics
]
fake_device = FakeDevice()
profiles = AndroidDeviceProfileResolver(
    {
        "installed-fake": AndroidDeviceProfile(
            "installed-fake",
            device=fake_device,
            label="Installed Fake Device",
            environment_candidate="fake_device",
        )
    }
)
fake_llm = FakePlannerLLM()
composition = build_default_studio_benchmark_composition(
    runtime_root,
    agents=agents,
    profiles=profiles,
    contract_catalog=catalog.node_contract_catalog(),
    component_catalog=catalog,
    include_installed=True,
    database_path=database,
    component_resolvers=ProductionComponentResolverFactory(
        secret_provider=forbidden("secret_resolution"),
        dependency_provider={"llm": fake_llm},
    ),
)
server = None
thread = None
try:
    entries = composition.catalog.list_entries().items
    assert len(entries) == 1
    entry = entries[0]
    assert entry.source_kind == "installed"
    assert entry.package_identity == (
        "zhixing-tests/layered-acceptance-external@1.0.0"
    )
    task = composition.catalog.list_tasks(
        entry.catalog_entry_id,
        split="test",
    ).items[0]
    definition = {
        "schemaVersion": 1,
        "agentRevisions": [
            {"agentId": agent.agent_id, "revisionId": revision.revision_id}
        ],
        "benchmark": {
            "catalogEntryId": entry.catalog_entry_id,
            "split": "test",
            "taskIds": [task.task_id],
        },
        "protocol": {
            "schemaVersion": "1.0",
            "seed": 29,
            "repeats": 1,
            "taskOrder": {"strategy": "fixed"},
            "taskMaterialization": {
                "reuseAcrossAgents": True,
                "strictFairness": False,
            },
            "device": {
                "platform": "android",
                "locale": "en-US",
                "orientation": "portrait",
                "versionPolicy": "compatible",
            },
            "apps": [],
            "budget": {
                "maxInteractions": 2,
                "maxActivations": 20,
                "timeoutSeconds": 30,
                "requireObservableTokens": False,
            },
            "isolation": {
                "reset": "before_each_agent",
                "cleanup": "after_each_run",
                "requireVerifiedReset": True,
            },
            "failure": {
                name: {
                    "outcome": (
                        "evaluate_if_possible" if name == "agent" else "invalidate"
                    ),
                    "continueSuite": True,
                    "preserveEvidence": True,
                }
                for name in ("initializer", "agent", "evaluator", "cleanup")
            },
        },
        "deviceProfileId": "installed-fake",
    }
    preview = composition.service.preview(definition)
    payload = {
        "schemaVersion": 1,
        "clientRequestId": "installed-layered-acceptance-create",
        "previewFingerprint": preview.preview_fingerprint,
        "definition": definition,
    }
    created = composition.experiments.create_experiment(payload).experiment
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        terminal = composition.experiments.get_experiment(created.experiment_id)
        if terminal.lifecycle.value == "terminal":
            break
        time.sleep(0.01)
    else:
        raise TimeoutError("installed fake Experiment did not terminate")
    assert terminal.terminal_reason.value == "completed"
    task_run = composition.experiments.list_task_runs(
        created.experiment_id
    ).items[0]
    assert task_run.result.agent_status.value == "success", (
        task_run.result.model_dump_json(by_alias=True, exclude_none=True)
    )
    assert task_run.result.benchmark_outcome.value == "pass", (
        task_run.result.model_dump_json(by_alias=True, exclude_none=True)
    )
    assert task_run.result.evidence_origin.acquisition == "contract_fixture"
    assert task_run.result.evidence_origin.environment == "fake_device"
    assert task_run.result.evidence_origin.real_device_evidence is False
    assert fake_llm.calls == 1
    publication = composition.publications.get_publication(created.experiment_id)
    assert publication is not None
    assert publication.replay_id == task_run.replay_id
    records = composition.publications.list_artifacts(created.experiment_id)
    kinds = {record.descriptor.kind for record in records}
    assert {
        "publication_manifest",
        "studio_publication_manifest",
        "experiment_report",
        "task_trajectory",
        "experiment_bundle",
    } <= kinds

    server = create_http_server(
        "127.0.0.1",
        0,
        application_service=authoring,
        benchmark_composition=composition,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    address = ("127.0.0.1", int(server.server_address[1]))

    def request(path, method="GET"):
        '''Read one exact installed Studio resource over loopback.'''
        connection = http.client.HTTPConnection(*address, timeout=5)
        connection.request(method, path, headers={"Host": "127.0.0.1"})
        response = connection.getresponse()
        body = response.read()
        headers = {key.lower(): value for key, value in response.getheaders()}
        status = response.status
        connection.close()
        return status, headers, body

    for record in records:
        descriptor = record.descriptor
        path = (
            f"/studio/benchmark-experiments/{created.experiment_id}/artifacts/"
            f"{descriptor.artifact_id}"
            if descriptor.task_run_id is None
            else (
                f"/studio/benchmark-experiments/{created.experiment_id}"
                f"/task-runs/{task_run.task_run_id}/artifacts/"
                f"{descriptor.artifact_id}"
            )
        )
        status, headers, body = request(path)
        assert status == 200
        assert len(body) == descriptor.size
        assert headers["content-length"] == str(descriptor.size)
        assert "sha256:" + hashlib.sha256(body).hexdigest() == descriptor.sha256
        head_status, head_headers, head_body = request(path, "HEAD")
        assert head_status == 200
        assert head_body == b""
        assert head_headers["content-length"] == headers["content-length"]
        assert head_headers["content-type"] == headers["content-type"]
    replay_status, _replay_headers, replay_body = request(task_run.links.replay)
    assert replay_status == 200, (replay_status, replay_body.decode(errors="replace"))
    replay = json.loads(replay_body)
    assert replay["runId"] == publication.replay_id == task_run.replay_id
    assert replay["benchmark"]["agentId"] == task_run.agent_id
    assert replay["benchmark"]["taskId"] == task_run.task_id
    assert calls == {key: 0 for key in calls}
    public = json.dumps(
        {
            "experiment": terminal.model_dump(
                mode="json", by_alias=True, exclude_none=True
            ),
            "taskRun": task_run.model_dump(
                mode="json", by_alias=True, exclude_none=True
            ),
            "replay": replay,
        },
        sort_keys=True,
    )
    assert str(repository_root) not in public
    assert str(runtime_root) not in public
    print(
        json.dumps(
            {
                "artifactCount": len(records),
                "benchmarkOutcome": task_run.result.benchmark_outcome.value,
                "canaries": calls,
                "environment": task_run.result.evidence_origin.environment,
                "realDeviceEvidence": False,
                "sourceIsInstalledWheel": True,
                "sourceKind": entry.source_kind,
                "terminalReason": terminal.terminal_reason.value,
            },
            sort_keys=True,
        )
    )
finally:
    if server is not None:
        server.shutdown()
        server.server_close()
    if thread is not None:
        thread.join(timeout=3)
    composition.shutdown()
"""
    completed = subprocess.run(
        [str(python), "-c", script, str(scenario_root), str(ROOT)],
        cwd=scenario_root,
        env=clean_env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    payload = json.loads(completed.stdout.splitlines()[-1])
    artifact_count = payload.pop("artifactCount")
    assert 10 <= artifact_count <= 64
    assert payload == {
        "benchmarkOutcome": "pass",
        "canaries": {
            "adb_discovery": 0,
            "external_network": 0,
            "model_resolution": 0,
            "real_device_construction": 0,
            "repository_source_fallback": 0,
            "secret_resolution": 0,
        },
        "environment": "fake_device",
        "realDeviceEvidence": False,
        "sourceIsInstalledWheel": True,
        "sourceKind": "installed",
        "terminalReason": "completed",
    }
