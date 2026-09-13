"""Reusable actual-composition fixtures for Stage 5.6B acceptance."""

from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from zhixing.studio import (
    SQLiteAgentDocumentRepository,
    StudioApplicationService,
    StudioBenchmarkComposition,
    build_default_studio_benchmark_composition,
    build_default_replay_service,
    build_studio_component_catalog,
)
from zhixing.studio.benchmark_experiment_models import (
    StudioBenchmarkExperimentLifecycle,
    StudioBenchmarkExperimentResourceV1,
)
from zhixing.studio.benchmark_experiment_service import (
    StudioBenchmarkExperimentApplicationService,
)
from zhixing.studio.benchmark_service import StudioBenchmarkSource
from zhixing.studio.httpd import StudioHTTPServer, create_http_server
from zhixing.studio.run_execution import (
    AndroidDeviceProfile,
    AndroidDeviceProfileResolver,
    ProductionComponentResolverFactory,
)
from zhixing.studio.flow_template_loader import get_flow_template_document

from .benchmark_fixtures import write_studio_benchmark_package
from .test_benchmark_composer import _preview_payload


class AcceptanceShellResult:
    """Small Android-shell response used only by the fake acceptance device."""

    def __init__(self, output: str = "", exit_code: int = 0) -> None:
        """Create one bounded fake shell result.

        Args:
            output: Deterministic standard output.
            exit_code: Deterministic process exit code.

        Raises:
            None.

        Returns:
            None.
        """
        self.output = output
        self.exit_code = exit_code
        self.error = ""


class LayeredAcceptanceFakeDevice:
    """Deterministic fake Android boundary for the actual Studio composition."""

    serial = "fake-layered-acceptance"
    platform = "android"
    locale = "en-US"
    orientation = "portrait"
    w = 100
    h = 200
    app_package_names = {"files": "com.android.documentsui"}

    def __init__(
        self,
        *,
        expose_pushed_files: bool = True,
        block_push: bool = False,
        locale: str = "en-US",
    ) -> None:
        """Configure deterministic evaluator and cancellation behavior.

        Args:
            expose_pushed_files: Whether ``ls`` can observe pushed paths.
            block_push: Whether the first push waits for explicit release.
            locale: Fake runtime locale used by Core device preflight.

        Raises:
            None.

        Returns:
            None.
        """
        self.expose_pushed_files = expose_pushed_files
        self.block_push = block_push
        self.locale = locale
        self.calls: list[tuple[Any, ...]] = []
        self.files: set[str] = set()
        self.push_started = threading.Event()
        self.release_push = threading.Event()

    def screenshot(self, path: str) -> str:
        """Write one bounded synthetic PNG-shaped artifact.

        Args:
            path: Runtime-owned artifact destination.

        Raises:
            OSError: The artifact destination cannot be written.

        Returns:
            The unchanged destination path.
        """
        Path(path).write_bytes(b"\x89PNG\r\n\x1a\n" + b"x" * 64)
        self.calls.append(("screenshot",))
        return path

    def go_home(self) -> None:
        """Record one fake HOME request without contacting a device."""
        self.calls.append(("home",))

    def go_back(self) -> None:
        """Record one fake BACK request without contacting a device."""
        self.calls.append(("back",))

    def wait(self, seconds: float) -> None:
        """Record a requested fake device wait.

        Args:
            seconds: Requested logical wait duration.

        Raises:
            None.

        Returns:
            None.
        """
        self.calls.append(("wait", seconds))

    def push_file(self, local_path: str, device_path: str) -> bool:
        """Record one fake push and optionally expose its destination.

        Args:
            local_path: Materialized Package resource path.
            device_path: Logical Android destination path.

        Raises:
            TimeoutError: A blocking fixture is not released in time.

        Returns:
            Always ``True`` after the bounded fake operation.
        """
        self.calls.append(("push_file", Path(local_path).name, device_path))
        self.push_started.set()
        if self.block_push and not self.release_push.wait(timeout=5):
            raise TimeoutError("fake acceptance push was not released")
        if self.expose_pushed_files:
            self.files.add(device_path)
        return True

    def shell(
        self,
        command: str,
        error_raise: bool = False,
    ) -> AcceptanceShellResult:
        """Return deterministic fake shell output for Package plugins.

        Args:
            command: Requested Android shell command.
            error_raise: Legacy compatibility flag; ignored by the fake.

        Raises:
            None.

        Returns:
            Successful output or one deterministic missing-path response.
        """
        del error_raise
        self.calls.append(("shell", command))
        if command.startswith("rm -rf "):
            self.files.clear()
            return AcceptanceShellResult("ok")
        if command.startswith("ls "):
            target = command[3:].strip()
            if target == "/storage/emulated/0/Download":
                return AcceptanceShellResult(target)
            if target in self.files:
                return AcceptanceShellResult(target)
            return AcceptanceShellResult("No such file or directory", 1)
        return AcceptanceShellResult("ok")


class DeterministicTerminalLLM:
    """Pure fixture dependency that returns one terminal Agent decision."""

    def __init__(self) -> None:
        """Create a call counter without network or model authority."""
        self.calls = 0

    def generate(
        self,
        prompt: str,
        images: list[str] | None = None,
    ) -> str:
        """Return a parser-compatible DONE response without external I/O.

        Args:
            prompt: Rendered built-in reasoning prompt.
            images: Optional fake observation artifact paths.

        Raises:
            None.

        Returns:
            Deterministic terminal JSON action.
        """
        del prompt, images
        self.calls += 1
        return '{"action":"DONE","params":{},"thought":"fixture complete"}'


def deterministic_terminal_agent_document() -> dict[str, Any]:
    """Return a Catalog-backed deterministic terminal Agent document.

    Args:
        None.

    Raises:
        None.

    Returns:
        Schema-2 Studio document using framework perception, reasoning, and
        action-executor contracts with a runtime-injected pure fixture LLM.
    """
    return {
        "schemaVersion": 2,
        "contractVersion": "1.1",
        "documentId": "document-layered-acceptance",
        "agentId": "agent-layered-acceptance",
        "name": "Layered Acceptance Agent",
        "semantic": {
            "profile": "mobile_agent",
            "policies": {"max_steps": 2, "max_feedback_iterations": 1},
            "nodes": [
                {
                    "canvasId": "canvas-input",
                    "logicalId": "input",
                    "kind": "input",
                    "lifecycle": "on_run_start",
                },
                {
                    "canvasId": "canvas-observe",
                    "logicalId": "observe",
                    "kind": "component",
                    "lifecycle": "on_run_start",
                    "contract": {
                        "id": "zhixing.service.device_observe",
                        "version": "2.0",
                    },
                    "component": {
                        "policy": "single",
                        "candidates": [
                            {
                                "namespace": "zhixing.runtime",
                                "name": "device_observe",
                                "version": "1",
                                "params": {},
                                "dependencies": {},
                            }
                        ],
                    },
                },
                {
                    "canvasId": "canvas-perception",
                    "logicalId": "perception",
                    "kind": "component",
                    "lifecycle": "on_run_start",
                    "role": "perception",
                    "contract": {
                        "id": "zhixing.core.perception",
                        "version": "1.0",
                    },
                    "component": {
                        "policy": "single",
                        "candidates": [
                            {
                                "namespace": "agent.perception",
                                "name": "screenshot_perception",
                                "version": "1",
                                "params": {},
                                "dependencies": {},
                            }
                        ],
                    },
                },
                {
                    "canvasId": "canvas-reasoning",
                    "logicalId": "reasoning",
                    "kind": "component",
                    "lifecycle": "on_run_start",
                    "role": "reasoning",
                    "contract": {
                        "id": "zhixing.core.reasoning",
                        "version": "1.0",
                    },
                    "component": {
                        "policy": "single",
                        "candidates": [
                            {
                                "namespace": "agent.reasoning",
                                "name": "universal_reasoning",
                                "version": "1",
                                "params": {
                                    "preset": "general_vlm_type",
                                    "input_mode": "text",
                                    "parser_name": "json_action_parser",
                                    "parse_max_retries": 0,
                                },
                                "dependencies": {
                                    "llm": {
                                        "namespace": "llm",
                                        "name": "openai_llm",
                                        "version": "1",
                                        "params": {},
                                    }
                                },
                            }
                        ],
                    },
                },
                {
                    "canvasId": "canvas-action-request",
                    "logicalId": "action_request",
                    "kind": "component",
                    "lifecycle": "on_run_start",
                    "contract": {
                        "id": "zhixing.control.action_request",
                        "version": "1.0",
                    },
                    "component": {
                        "policy": "single",
                        "candidates": [
                            {
                                "namespace": "zhixing.control",
                                "name": "action_request",
                                "version": "1",
                                "params": {},
                                "dependencies": {},
                            }
                        ],
                    },
                },
                {
                    "canvasId": "canvas-action",
                    "logicalId": "action",
                    "kind": "component",
                    "lifecycle": "on_run_start",
                    "contract": {
                        "id": "zhixing.service.action_executor",
                        "version": "1.0",
                    },
                    "component": {
                        "policy": "single",
                        "candidates": [
                            {
                                "namespace": "zhixing.runtime",
                                "name": "action_executor",
                                "version": "1",
                                "params": {},
                                "dependencies": {},
                            }
                        ],
                    },
                },
                {
                    "canvasId": "canvas-output",
                    "logicalId": "output",
                    "kind": "output",
                    "lifecycle": "terminal",
                },
            ],
            "edges": [
                {
                    "canvasId": "edge-observe-request",
                    "source": {"canvasId": "canvas-input", "portId": "value"},
                    "target": {
                        "canvasId": "canvas-observe",
                        "portId": "request",
                    },
                    "kind": "data",
                },
                {
                    "canvasId": "edge-observation-perception",
                    "source": {
                        "canvasId": "canvas-observe",
                        "portId": "observation",
                    },
                    "target": {
                        "canvasId": "canvas-perception",
                        "portId": "observation",
                    },
                    "kind": "data",
                },
                {
                    "canvasId": "edge-task-reasoning",
                    "source": {"canvasId": "canvas-input", "portId": "task"},
                    "target": {
                        "canvasId": "canvas-reasoning",
                        "portId": "task",
                    },
                    "kind": "data",
                },
                {
                    "canvasId": "edge-perception-reasoning",
                    "source": {
                        "canvasId": "canvas-perception",
                        "portId": "perception",
                    },
                    "target": {
                        "canvasId": "canvas-reasoning",
                        "portId": "perception",
                    },
                    "kind": "data",
                },
                {
                    "canvasId": "edge-reasoning-action",
                    "source": {
                        "canvasId": "canvas-reasoning",
                        "portId": "action",
                    },
                    "target": {
                        "canvasId": "canvas-action-request",
                        "portId": "action",
                    },
                    "kind": "data",
                },
                {
                    "canvasId": "edge-observation-action",
                    "source": {
                        "canvasId": "canvas-observe",
                        "portId": "observation",
                    },
                    "target": {
                        "canvasId": "canvas-action-request",
                        "portId": "observation",
                    },
                    "kind": "data",
                },
                {
                    "canvasId": "edge-action-request",
                    "source": {
                        "canvasId": "canvas-action-request",
                        "portId": "request",
                    },
                    "target": {
                        "canvasId": "canvas-action",
                        "portId": "request",
                    },
                    "kind": "data",
                },
                {
                    "canvasId": "edge-action-result",
                    "source": {"canvasId": "canvas-action", "portId": "result"},
                    "target": {"canvasId": "canvas-output", "portId": "result"},
                    "kind": "data",
                }
            ],
        },
        "presentation": {
            "nodes": {
                "canvas-input": {"x": 0, "y": 0, "label": "Input"},
                "canvas-observe": {"x": 180, "y": 0, "label": "Observe"},
                "canvas-perception": {
                    "x": 360,
                    "y": 0,
                    "label": "Perception",
                },
                "canvas-reasoning": {
                    "x": 540,
                    "y": 0,
                    "label": "Reasoning",
                },
                "canvas-action-request": {
                    "x": 720,
                    "y": 0,
                    "label": "Action Request",
                },
                "canvas-action": {"x": 900, "y": 0, "label": "Action"},
                "canvas-output": {"x": 1080, "y": 0, "label": "Output"},
            },
            "viewport": {"x": 0, "y": 0, "zoom": 1},
        },
        "authoring": {
            "description": "deterministic fake acceptance agent",
            "createdAt": 0,
            "updatedAt": 0,
        },
    }


@dataclass(frozen=True)
class LayeredAcceptanceHarness:
    """Owned actual Studio composition and its exact selected identities."""

    composition: StudioBenchmarkComposition
    application_service: StudioApplicationService
    device: LayeredAcceptanceFakeDevice
    terminal_llm: DeterministicTerminalLLM
    workspace: Path
    package_path: Path
    database: Path
    definition: dict[str, Any]
    agent_id: str
    revision_id: str
    catalog_entry_id: str
    task_id: str
    profile_id: str = "acceptance-fake"

    def detached_experiment_service(
        self,
    ) -> StudioBenchmarkExperimentApplicationService:
        """Build an authoritative resource service without worker dispatch.

        This boundary is used only to model a lost response, accepted-only
        cancellation, or a durable crash window before another process starts.

        Args:
            None.

        Raises:
            AssertionError: Durable repositories are unavailable.

        Returns:
            Experiment service sharing the actual composition repositories.
        """
        assert self.composition.repository is not None
        return StudioBenchmarkExperimentApplicationService(
            definitions=self.composition.service,
            repository=self.composition.repository,
            publication_repository=self.composition.publications,
            execution_enabled=True,
            event_transport_enabled=True,
            publication_enabled=True,
        )

    def start_http_server(self, *, port: int = 0) -> "LayeredAcceptanceServer":
        """Start the actual bounded Studio HTTP/SSE surface on loopback.

        Args:
            port: Explicit loopback port, or zero for an ephemeral test port.

        Raises:
            OSError: The loopback listener cannot be created.

        Returns:
            Running server fixture with one safe bootstrap projection.
        """
        server = create_http_server(
            "127.0.0.1",
            port,
            application_service=self.application_service,
            benchmark_composition=self.composition,
            sse_heartbeat_seconds=0.05,
            sse_write_timeout_seconds=0.25,
            benchmark_sse_max_connections=4,
        )
        thread = threading.Thread(
            target=server.serve_forever,
            name="zhixing-layered-acceptance-http",
            daemon=True,
        )
        thread.start()
        port = int(server.server_address[1])
        return LayeredAcceptanceServer(
            server=server,
            thread=thread,
            bootstrap={
                "schemaVersion": 1,
                "apiBaseUrl": f"http://127.0.0.1:{port}",
                "catalogEntryId": self.catalog_entry_id,
                "taskId": self.task_id,
                "agentId": self.agent_id,
                "revisionId": self.revision_id,
                "deviceProfileId": self.profile_id,
                "warning": "fake device only; not real Android evidence",
            },
        )

    def create_payload(self, client_request_id: str) -> dict[str, Any]:
        """Build an exact create payload from the authoritative preview.

        Args:
            client_request_id: Stable request-scoped idempotency identity.

        Raises:
            ValueError: The current definition no longer previews.

        Returns:
            Complete create request accepted by the actual service.
        """
        preview = self.composition.service.preview(self.definition)
        return {
            "schemaVersion": 1,
            "clientRequestId": client_request_id,
            "previewFingerprint": preview.preview_fingerprint,
            "definition": json.loads(json.dumps(self.definition)),
        }

    def wait_terminal(
        self,
        experiment_id: str,
        *,
        timeout: float = 8.0,
    ) -> StudioBenchmarkExperimentResourceV1:
        """Wait for one actual worker-owned Experiment to become terminal.

        Args:
            experiment_id: Opaque durable Experiment identity.
            timeout: Bounded polling duration in seconds.

        Raises:
            TimeoutError: The Experiment does not become terminal in time.

        Returns:
            Current terminal Experiment resource.
        """
        assert self.composition.experiments is not None
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            current = self.composition.experiments.get_experiment(experiment_id)
            if current.lifecycle is StudioBenchmarkExperimentLifecycle.TERMINAL:
                return current
            time.sleep(0.01)
        raise TimeoutError("actual fake Experiment did not become terminal")


@dataclass(frozen=True)
class LayeredAcceptanceServer:
    """Running actual HTTP server and its bounded safe bootstrap object."""

    server: StudioHTTPServer
    thread: threading.Thread
    bootstrap: dict[str, Any]

    def close(self) -> None:
        """Stop the loopback server and wait for bounded handler teardown.

        Args:
            None.

        Raises:
            OSError: Listener shutdown fails.

        Returns:
            None.
        """
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)
        if self.thread.is_alive():
            raise TimeoutError("layered acceptance HTTP server did not stop")


def build_layered_acceptance_harness(
    root: Path,
    *,
    expose_pushed_files: bool = True,
    block_push: bool = False,
    device_locale: str = "en-US",
) -> LayeredAcceptanceHarness:
    """Build the product default composition over one explicit fake Package.

    Args:
        root: Temporary acceptance workspace.
        expose_pushed_files: Whether the evaluator observes the pushed file.
        block_push: Whether fake initialization pauses for cancellation.
        device_locale: Fake runtime locale for context-preflight scenarios.

    Raises:
        ValueError: Agent, Package, or composition contracts are invalid.
        OSError: Temporary durable resources cannot be created.

    Returns:
        Owned actual-composition harness; caller must shut it down.
    """
    root.mkdir(parents=True, exist_ok=True)
    database = root / "studio.sqlite3"
    package = write_studio_benchmark_package(
        root / "catalog" / "fixture",
        name="layered-acceptance",
    )
    task_path = package / "tasks" / "test.json"
    task_payload = json.loads(task_path.read_text(encoding="utf-8"))
    task_payload[0]["environment_initializer"] = [
        {
            "name": "android_reset_clear_directory",
            "params": {
                "phone_folder_path": "/storage/emulated/0/Download",
                "media_scan": False,
            },
        },
        {
            "name": "android_injection_push_file",
            "params": {
                "files": [
                    {
                        "local_path": "asset://fixture",
                        "device_path": (
                            "/storage/emulated/0/Download/fixture.txt"
                        ),
                        "media_scan": False,
                    }
                ]
            },
        }
    ]
    task_path.write_text(
        json.dumps(task_payload, ensure_ascii=False),
        encoding="utf-8",
    )
    manifest_path = package / "benchmark.yaml"
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    manifest["plugins"] = [
        {"id": "android_reset_clear_directory", "optional": False},
        {"id": "android_injection_push_file", "optional": False},
        {"id": "file_exist", "optional": False},
    ]
    manifest_path.write_text(
        yaml.safe_dump(manifest, sort_keys=False),
        encoding="utf-8",
    )
    graph_catalog = build_studio_component_catalog()
    agents = SQLiteAgentDocumentRepository(database)
    replay_service = build_default_replay_service(database)
    authoring = StudioApplicationService(
        catalog=graph_catalog,
        repository=agents,
        replay_service=replay_service,
    )
    agent, revision = authoring.create_agent(
        "Layered Acceptance Agent",
        initial_document=get_flow_template_document("modular_baseline"),
    )
    if revision.compile_snapshot.status != "valid":
        raise ValueError("capability acceptance Agent did not compile")
    device = LayeredAcceptanceFakeDevice(
        expose_pushed_files=expose_pushed_files,
        block_push=block_push,
        locale=device_locale,
    )
    profiles = AndroidDeviceProfileResolver(
        {
            "acceptance-fake": AndroidDeviceProfile(
                "acceptance-fake",
                device=device,
                label="Acceptance Fake Device",
                environment_candidate="fake_device",
            )
        }
    )
    terminal_llm = DeterministicTerminalLLM()
    composition = build_default_studio_benchmark_composition(
        root,
        agents=agents,
        profiles=profiles,
        contract_catalog=graph_catalog.node_contract_catalog(),
        sources=(
            StudioBenchmarkSource(
                source_id="layered-acceptance-package",
                kind="package",
                locator=package,
            ),
        ),
        include_installed=False,
        database_path=database,
        component_resolvers=ProductionComponentResolverFactory(
            dependency_provider={"llm": terminal_llm}
        ),
    )
    entry = composition.catalog.list_entries().items[0]
    task = composition.catalog.list_tasks(
        entry.catalog_entry_id,
        split="test",
    ).items[0]
    definition = _preview_payload(
        entry.catalog_entry_id,
        task.task_id,
        agent.agent_id,
        revision.revision_id,
    )
    definition["deviceProfileId"] = "acceptance-fake"
    return LayeredAcceptanceHarness(
        composition=composition,
        application_service=authoring,
        device=device,
        terminal_llm=terminal_llm,
        workspace=root,
        package_path=package,
        database=database,
        definition=definition,
        agent_id=agent.agent_id,
        revision_id=revision.revision_id,
        catalog_entry_id=entry.catalog_entry_id,
        task_id=task.task_id,
    )


def reopen_layered_acceptance_harness(
    previous: LayeredAcceptanceHarness,
) -> LayeredAcceptanceHarness:
    """Reopen one stopped workspace through production startup recovery.

    Args:
        previous: Stopped harness whose durable database and Package remain.

    Raises:
        OSError: Durable composition resources cannot be reopened.
        ValueError: Stored Agent or Package identities no longer resolve.

    Returns:
        New process-scoped composition over the same durable facts and fakes.
    """
    graph_catalog = build_studio_component_catalog()
    agents = SQLiteAgentDocumentRepository(previous.database)
    replay_service = build_default_replay_service(previous.database)
    application_service = StudioApplicationService(
        catalog=graph_catalog,
        repository=agents,
        replay_service=replay_service,
    )
    profiles = AndroidDeviceProfileResolver(
        {
            previous.profile_id: AndroidDeviceProfile(
                previous.profile_id,
                device=previous.device,
                label="Acceptance Fake Device",
                environment_candidate="fake_device",
            )
        }
    )
    composition = build_default_studio_benchmark_composition(
        previous.workspace,
        agents=agents,
        profiles=profiles,
        contract_catalog=graph_catalog.node_contract_catalog(),
        sources=(
            StudioBenchmarkSource(
                source_id="layered-acceptance-package",
                kind="package",
                locator=previous.package_path,
            ),
        ),
        include_installed=False,
        database_path=previous.database,
        component_resolvers=ProductionComponentResolverFactory(
            dependency_provider={"llm": previous.terminal_llm}
        ),
    )
    entry = composition.catalog.list_entries().items[0]
    task = composition.catalog.list_tasks(
        entry.catalog_entry_id,
        split="test",
    ).items[0]
    if entry.catalog_entry_id != previous.catalog_entry_id:
        raise ValueError("Catalog identity changed across acceptance restart")
    if task.task_id != previous.task_id:
        raise ValueError("Task identity changed across acceptance restart")
    return LayeredAcceptanceHarness(
        composition=composition,
        application_service=application_service,
        device=previous.device,
        terminal_llm=previous.terminal_llm,
        workspace=previous.workspace,
        package_path=previous.package_path,
        database=previous.database,
        definition=json.loads(json.dumps(previous.definition)),
        agent_id=previous.agent_id,
        revision_id=previous.revision_id,
        catalog_entry_id=previous.catalog_entry_id,
        task_id=previous.task_id,
        profile_id=previous.profile_id,
    )


__all__ = [
    "LayeredAcceptanceFakeDevice",
    "LayeredAcceptanceHarness",
    "LayeredAcceptanceServer",
    "build_layered_acceptance_harness",
    "deterministic_terminal_agent_document",
    "reopen_layered_acceptance_harness",
]
