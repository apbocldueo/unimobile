"""Run a deterministic fake-device Studio server for browser smoke testing.

This developer-only harness intentionally reuses verified test fixtures. It is
not part of the installed ``zhixing`` wheel and must never be cited as real
Android evidence.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any, Sequence

from PIL import Image

from tests.runtime.test_android_graph_runtime import FakeAndroidDevice
from tests.studio.helpers import (
    graph_with_exact_component_versions,
    studio_document_from_graph,
)
from tests.studio.test_run_execution import (
    MappingResolverFactory,
    _android_task_graph,
)
from zhixing.components import Action, ActionType
from zhixing.graph import BUILTIN_NODE_CONTRACT_CATALOG
from zhixing.studio import (
    CompileSnapshot,
    SQLiteAgentDocumentRepository,
    StudioApplicationService,
    StudioComponentCatalog,
    StudioFlowDocument,
    build_studio_component_catalog,
)
from zhixing.studio.catalog import StudioComponentDescriptor
from zhixing.studio.httpd import create_http_server
from zhixing.studio.replay_service import build_default_replay_service
from zhixing.studio.run_composition import build_default_studio_run_composition
from zhixing.studio.run_execution import (
    AndroidDeviceProfile,
    AndroidDeviceProfileResolver,
)


class SlowBrowserSmokeDevice(FakeAndroidDevice):
    """Delay fake observations so a browser can inspect and cancel a live Run."""

    def screenshot(self, path: str) -> str:
        """Write one deterministic fake screenshot after a short delay.

        Args:
            path (str): Host destination allocated by the runtime.

        Raises:
            OSError: Writing the fake artifact fails.

        Returns:
            str: The destination path.
        """
        time.sleep(0.25)
        Image.new("RGB", (self.w, self.h), (24, 36, 58)).save(
            path,
            format="PNG",
        )
        self.calls.append(("screenshot", path))
        return path


class DelayedComponent:
    """Delay one fake component activation to expose a stable live UI window."""

    def __init__(self, target: object, delay_seconds: float) -> None:
        """Store the wrapped component and deterministic delay.

        Args:
            target (object): Component exposing ``invoke``.
            delay_seconds (float): Pre-invocation delay.

        Raises:
            ValueError: Delay is negative.

        Returns:
            None.
        """
        if delay_seconds < 0:
            raise ValueError("component delay cannot be negative")
        self.target = target
        self.delay_seconds = delay_seconds

    def invoke(self, input: Any, runtime: Any) -> Any:
        """Wait and delegate one invocation without changing its result.

        Args:
            input (Any): Contract input forwarded to the wrapped component.
            runtime (Any): Runtime context forwarded to the wrapped component.

        Raises:
            AttributeError: The wrapped component has no ``invoke`` method.
            Exception: The wrapped invocation fails.

        Returns:
            Any: Wrapped component result.
        """
        time.sleep(self.delay_seconds)
        return self.target.invoke(input, runtime)


def _parser() -> argparse.ArgumentParser:
    """Build command-line options for the local smoke server.

    Returns:
        argparse.ArgumentParser: Configured parser.
    """
    parser = argparse.ArgumentParser(
        description="Serve Studio with a deterministic slow fake Android device.",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument(
        "--browser-origin",
        default="http://127.0.0.1:5173",
        help="single explicit browser origin allowed by the smoke server",
    )
    parser.add_argument(
        "--database",
        type=Path,
        default=Path("temp/studio-live-browser-smoke/studio.sqlite3"),
    )
    parser.add_argument(
        "--profile-count",
        type=int,
        choices=(0, 1, 2),
        default=1,
        help="expose zero, one, or two safe fake Device Profiles",
    )
    parser.add_argument(
        "--component-delay",
        type=float,
        default=60.0,
        help="delay the fake action component for live or terminal inspection",
    )
    return parser


def _seed_agent(
    database: Path,
    *,
    component_delay: float,
) -> tuple[SQLiteAgentDocumentRepository, str, str, dict[str, object]]:
    """Persist one exact-version looping AgentGraph for the smoke browser.

    Args:
        database (Path): SQLite database path.
        component_delay (float): Deterministic fake action delay in seconds.

    Raises:
        ValueError: The graph or Studio document violates its contract.
        OSError: The database parent cannot be created.

    Returns:
        tuple: Repository, Agent ID, revision ID, and component mappings.
    """
    database.parent.mkdir(parents=True, exist_ok=True)
    graph, components = _android_task_graph(
        Action(ActionType.KEY, {"code": "home"}),
        max_steps=100,
    )
    components["build_action"] = DelayedComponent(
        components["build_action"],
        component_delay,
    )
    exact = graph_with_exact_component_versions(graph)
    document = StudioFlowDocument.model_validate(
        studio_document_from_graph(
            exact,
            document_id="live-browser-smoke",
            agent_id="live-browser-smoke",
        )
    )
    agents = SQLiteAgentDocumentRepository(database)
    agent, revision = agents.create_agent(
        "Live fake-device browser smoke",
        document,
        CompileSnapshot(
            status="valid",
            agent_graph=exact.model_dump(mode="json", exclude_none=True),
            canonical_hash=exact.canonical_hash(),
        ),
    )
    return agents, agent.agent_id, revision.revision_id, components


def _smoke_catalog() -> StudioComponentCatalog:
    """Extend the production Catalog with explicit fake-only fixture entries.

    Raises:
        RuntimeError: A built-in NodeContract used by the fixture is absent.

    Returns:
        StudioComponentCatalog: Production entries plus four test-only
            components whose identities match the seeded graph.
    """
    catalog = build_studio_component_catalog()
    graph, _components = _android_task_graph(
        Action(ActionType.KEY, {"code": "home"}),
        max_steps=100,
    )
    additions: list[StudioComponentDescriptor] = []
    for node in graph.nodes:
        if node.component is None or node.contract is None:
            continue
        contract = BUILTIN_NODE_CONTRACT_CATALOG.resolve(node.contract)
        if contract is None:
            raise RuntimeError(
                f"missing smoke NodeContract {node.contract.id}@{node.contract.version}"
            )
        reference = node.component.candidates[0]
        additions.append(
            StudioComponentDescriptor(
                identifier=(
                    f"{reference.namespace}:{reference.name}@"
                    f"{reference.version or '1.0.0'}"
                ),
                namespace=reference.namespace,
                name=reference.name,
                version=reference.version or "1.0.0",
                provider_id="zhixing.fake-browser-smoke",
                contract=contract,
                category="runtime_service",
                config_schema={
                    "type": "object",
                    "properties": {},
                    "additionalProperties": False,
                },
                capabilities={"fake_device": True},
                provenance={"kind": "test_fixture"},
                display={
                    "label": f"Fake {reference.name}",
                    "group": "fake browser smoke",
                },
            )
        )
    return catalog.model_copy(
        update={
            "catalog_version": f"{catalog.catalog_version}-fake-browser-smoke",
            "components": tuple((*catalog.components, *additions)),
        }
    )


def main(argv: Sequence[str] | None = None) -> None:
    """Serve the complete Studio HTTP stack with a slow deterministic fake.

    Args:
        argv (Sequence[str] | None): Optional command arguments.

    Raises:
        OSError: Database or local socket setup fails.
        ValueError: Seed contracts or server options are invalid.

    Returns:
        None.
    """
    args = _parser().parse_args(argv)
    agents, agent_id, revision_id, components = _seed_agent(
        args.database,
        component_delay=args.component_delay,
    )
    catalog = _smoke_catalog()
    replay = build_default_replay_service(args.database)
    authoring = StudioApplicationService(
        catalog=catalog,
        repository=agents,
        replay_service=replay,
    )
    profile_entries: dict[str, AndroidDeviceProfile] = {}
    if args.profile_count >= 1:
        profile_entries["local-android"] = AndroidDeviceProfile(
            "local-android",
            device=SlowBrowserSmokeDevice(),
        )
    if args.profile_count >= 2:
        profile_entries["backup-android"] = AndroidDeviceProfile(
            "backup-android",
            device=SlowBrowserSmokeDevice(),
        )
    composition = build_default_studio_run_composition(
        args.database,
        agents=agents,
        replay_service=replay,
        profiles=AndroidDeviceProfileResolver(profile_entries),
        components=MappingResolverFactory(components),
        component_catalog=catalog,
        enforce_readiness=True,
    )
    server = create_http_server(
        args.host,
        args.port,
        application_service=authoring,
        run_composition=composition,
        allowed_origins=frozenset({args.browser_origin}),
        sse_heartbeat_seconds=0.5,
        sse_write_timeout_seconds=3,
    )
    print(
        json.dumps(
            {
                "schemaVersion": 1,
                "kind": "fake_device_browser_smoke",
                "apiBase": f"http://{args.host}:{args.port}",
                "agentId": agent_id,
                "revisionId": revision_id,
                "designPath": f"/agents/{agent_id}/design",
                "launchPath": (
                    f"/agents/{agent_id}/run?revisionId={revision_id}"
                ),
                "warning": "fake device only; not real Android evidence",
            },
            ensure_ascii=False,
        ),
        flush=True,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
