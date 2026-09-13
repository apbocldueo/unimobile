#!/usr/bin/env python3
"""Run the gated Stage 5.6C-2 real-Android Studio acceptance server.

The launcher validates the complete C-1 proof before it loads trusted profile
configuration or constructs any backend, Worker, model dependency, or device
authority.  It reuses the two immutable C-1 Agent revisions through the normal
repository protocol and emits one bounded loopback bootstrap object.
"""

from __future__ import annotations

import argparse
import contextlib
from dataclasses import dataclass
import json
from pathlib import Path
import signal
import sys
import threading
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.studio_benchmark_android_service_acceptance import (  # noqa: E402
    PACKAGE_IDENTITY,
    SPLIT,
    TASK_ID,
    AndroidServiceScenarioId,
)
from scripts.studio_benchmark_android_view_acceptance import (  # noqa: E402
    BrowserPrerequisiteEvidence,
    start_after_prerequisite,
)


@dataclass(frozen=True)
class AndroidViewCampaignInputs:
    """Private process-local inputs retained outside the public bootstrap."""

    receipt: BrowserPrerequisiteEvidence
    service_summary: Path
    device_profile_config: Path
    workspace: Path
    port: int
    x: int
    y: int


class SequentialBrowserCampaignLLM:
    """Serve the fixed positive actions then the controlled normal finish.

    The accepted browser campaign is strictly ordered.  The first immutable
    Agent has a four-step bound and consumes the camera action script; the
    second Agent has a one-step bound and consumes the fifth normal-finish
    response.  Any retry or reexecution therefore fails closed.
    """

    def __init__(self, *, x: int, y: int) -> None:
        """Create one campaign-scoped deterministic decision dependency.

        Args:
            x: Non-negative shutter horizontal coordinate.
            y: Non-negative shutter vertical coordinate.

        Raises:
            ValueError: A coordinate is negative.

        Returns:
            None.
        """
        if x < 0 or y < 0:
            raise ValueError("camera coordinates must be non-negative")
        self.x = x
        self.y = y
        self.calls = 0

    def generate(
        self,
        prompt: str,
        images: list[str] | None = None,
    ) -> str:
        """Return the fixed positive sequence followed by normal control finish.

        Args:
            prompt: Rendered Agent reasoning prompt.
            images: Current screenshot references.

        Raises:
            RuntimeError: The campaign requests an unexpected extra decision.

        Returns:
            One parser-compatible deterministic Mobile Agent action.
        """
        del prompt, images
        self.calls += 1
        if self.calls == 1:
            return (
                '{"action":"start_app","arguments":{"app":"camera"},'
                '"thought":"open the selected camera app"}'
            )
        if self.calls == 2:
            return (
                '{"action":"wait","arguments":{"seconds":3},'
                '"thought":"wait for the camera preview"}'
            )
        if self.calls == 3:
            return (
                '{"action":"tap","arguments":'
                f'{{"x":{self.x},"y":{self.y}}},'
                '"thought":"press the shutter"}'
            )
        if self.calls == 4:
            return (
                '{"action":"wait","arguments":{"seconds":3},'
                '"thought":"allow MediaStore to publish the captured photo"}'
            )
        if self.calls == 5:
            return (
                '{"action":"DONE","params":{},'
                '"thought":"controlled normal finish"}'
            )
        raise RuntimeError(
            "browser campaign requested a second execution or parser retry"
        )


class CompositeReadOnlyAgentRepository:
    """Expose exact C-1 revisions from two repositories through one boundary."""

    def __init__(self, repositories: tuple[Any, ...]) -> None:
        """Index distinct immutable C-1 Agents without copying their rows.

        Args:
            repositories: Existing C-1 repository instances.

        Raises:
            ValueError: An Agent identity appears in more than one repository.

        Returns:
            None.
        """
        agents: dict[str, tuple[Any, Any]] = {}
        for repository in repositories:
            page = repository.list_agents(limit=100)
            if page.next_cursor is not None:
                raise ValueError("C-1 Agent repository exceeds acceptance bound")
            for agent in page.items:
                if agent.agent_id in agents:
                    raise ValueError("C-1 Agent identity is duplicated")
                agents[agent.agent_id] = (repository, agent)
        self._agents = agents

    def create_agent(self, name: str, document: Any, snapshot: Any) -> Any:
        """Reject writes to immutable C-1 Agent evidence.

        Args:
            name: Unused requested display name.
            document: Unused requested document.
            snapshot: Unused requested compile snapshot.

        Raises:
            ValueError: Always; C-2 must not mutate C-1 Agents.

        Returns:
            Never returns.
        """
        del name, document, snapshot
        raise ValueError("C-2 acceptance Agent repository is read-only")

    def list_agents(
        self,
        *,
        limit: int = 50,
        cursor: str | None = None,
    ) -> Any:
        """List the two immutable Agents with a bounded acceptance cursor.

        Args:
            limit: Requested page size from one through 100.
            cursor: Optional decimal acceptance cursor.

        Raises:
            ValueError: Limit or cursor is invalid.

        Returns:
            Normal ``AgentPage`` over the existing records.
        """
        from zhixing.studio.repository import AgentPage

        if not 1 <= limit <= 100:
            raise ValueError("Agent page limit must be between 1 and 100")
        try:
            offset = 0 if cursor is None else int(cursor)
        except ValueError as error:
            raise ValueError("invalid acceptance Agent cursor") from error
        ordered = sorted(
            (item[1] for item in self._agents.values()),
            key=lambda item: (-item.updated_at, item.agent_id),
        )
        if offset < 0 or offset > len(ordered):
            raise ValueError("invalid acceptance Agent cursor")
        items = tuple(ordered[offset: offset + limit])
        next_offset = offset + len(items)
        return AgentPage(
            items=items,
            nextCursor=(str(next_offset) if next_offset < len(ordered) else None),
        )

    def get_agent(self, agent_id: str) -> Any:
        """Read one exact C-1 Agent.

        Args:
            agent_id: Stable C-1 Agent identity.

        Raises:
            KeyError: Agent is not part of the accepted pair.

        Returns:
            Existing immutable Agent metadata record.
        """
        try:
            return self._agents[agent_id][1]
        except KeyError as error:
            raise KeyError("acceptance Agent was not found") from error

    def rename_agent(self, agent_id: str, name: str) -> Any:
        """Reject metadata mutation of C-1 Agents.

        Args:
            agent_id: Unused Agent identity.
            name: Unused requested name.

        Raises:
            ValueError: Always; the evidence repository is read-only.

        Returns:
            Never returns.
        """
        del agent_id, name
        raise ValueError("C-2 acceptance Agent repository is read-only")

    def get_revision(self, agent_id: str, revision_id: str) -> Any:
        """Read one exact immutable C-1 revision from its owning repository.

        Args:
            agent_id: Stable owning Agent identity.
            revision_id: Exact immutable revision identity.

        Raises:
            KeyError: Agent is not part of the accepted pair.
            ValueError: Revision does not belong to the Agent.

        Returns:
            Existing immutable Agent revision record.
        """
        try:
            repository = self._agents[agent_id][0]
        except KeyError as error:
            raise KeyError("acceptance Agent was not found") from error
        return repository.get_revision(agent_id, revision_id)

    def save_revision(
        self,
        agent_id: str,
        *,
        base_revision_id: str | None,
        document: Any,
        snapshot: Any,
    ) -> Any:
        """Reject appending revisions to the accepted C-1 evidence.

        Args:
            agent_id: Unused owning Agent identity.
            base_revision_id: Unused optimistic base identity.
            document: Unused requested document.
            snapshot: Unused requested compile snapshot.

        Raises:
            ValueError: Always; the evidence repository is read-only.

        Returns:
            Never returns.
        """
        del agent_id, base_revision_id, document, snapshot
        raise ValueError("C-2 acceptance Agent repository is read-only")


@dataclass(frozen=True)
class AndroidViewCampaignServer:
    """Owned production-composed server, Worker, and safe bootstrap facts."""

    server: Any
    thread: threading.Thread
    composition: Any
    bootstrap: dict[str, Any]
    llm: SequentialBrowserCampaignLLM

    def close(self) -> None:
        """Stop subscribers/server first, then deterministically stop Worker.

        Raises:
            TimeoutError: HTTP thread does not terminate.

        Returns:
            None.
        """
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        if self.thread.is_alive():
            raise TimeoutError("Android view acceptance HTTP server did not stop")
        self.composition.shutdown(wait=True)


def _safe_disposable_workspace(path: Path) -> Path:
    """Require a new campaign workspace beneath repository ``temp/``.

    Args:
        path: Candidate C-2 durable root.

    Raises:
        ValueError: Path is outside the disposable root or already exists.

    Returns:
        Resolved safe workspace.
    """
    resolved = path.expanduser().resolve()
    allowed = (ROOT / "temp").resolve()
    if resolved == allowed or allowed not in resolved.parents:
        raise ValueError("C-2 workspace must be a child of repository temp/")
    if resolved.exists():
        raise ValueError("C-2 workspace must be new")
    return resolved


def _scenario_databases(service_summary: Path) -> tuple[Path, Path]:
    """Resolve the two retained C-1 Agent repositories beside its summary.

    Args:
        service_summary: Strict summary written at the C-1 campaign root.

    Raises:
        FileNotFoundError: A retained scenario database is unavailable.

    Returns:
        Positive and controlled-negative database paths in stable order.
    """
    root = service_summary.expanduser().resolve().parent
    paths = tuple(
        root / scenario.value / "studio.sqlite3"
        for scenario in (
            AndroidServiceScenarioId.POSITIVE,
            AndroidServiceScenarioId.CONTROLLED_FAIL,
        )
    )
    for path in paths:
        if not path.is_file():
            raise FileNotFoundError(
                "retained C-1 scenario Agent repository is unavailable"
            )
    return paths  # type: ignore[return-value]


def _verify_prerequisite_agents(
    repository: CompositeReadOnlyAgentRepository,
    receipt: BrowserPrerequisiteEvidence,
) -> None:
    """Require the retained repositories to match every receipt identity.

    Args:
        repository: Read-only composite over the C-1 databases.
        receipt: Strict C-1 completion receipt.

    Raises:
        ValueError: An Agent/revision is missing, invalid, or mismatched.

    Returns:
        None.
    """
    for scenario in receipt.scenarios:
        agent = repository.get_agent(scenario.agent_id)
        revision = repository.get_revision(
            scenario.agent_id,
            scenario.agent_revision_id,
        )
        if (
            agent.agent_id != scenario.agent_id
            or revision.agent_id != scenario.agent_id
            or revision.revision_id != scenario.agent_revision_id
            or revision.compile_snapshot.status != "valid"
        ):
            raise ValueError("retained C-1 Agent revision does not match receipt")


def _safe_bootstrap(
    *,
    api_base_url: str,
    receipt: BrowserPrerequisiteEvidence,
    catalog_entry_id: str,
) -> dict[str, Any]:
    """Build the only public launcher output without private target authority.

    Args:
        api_base_url: Loopback HTTP origin.
        receipt: Strict C-1 prerequisite receipt.
        catalog_entry_id: Actual selected Catalog identity.

    Raises:
        ValueError: Loopback origin is not explicitly local.

    Returns:
        Bounded JSON-compatible bootstrap projection.
    """
    if not (
        api_base_url.startswith("http://127.0.0.1:")
        or api_base_url.startswith("http://localhost:")
    ):
        raise ValueError("acceptance bootstrap must be loopback-only")
    return {
        "schemaVersion": 1,
        "campaignVersion": "studio-benchmark-android-view-5.6c2-v1",
        "apiBaseUrl": api_base_url,
        "serviceSummarySha256": receipt.service_summary_sha256,
        "catalogEntryId": catalog_entry_id,
        "packageIdentity": receipt.selection.package_identity,
        "taskId": receipt.selection.task_id,
        "split": receipt.selection.split,
        "protocolSeed": receipt.selection.protocol_seed,
        "repeats": receipt.selection.repeats,
        "deviceProfileId": receipt.selection.device_profile_id,
        "agents": [
            {
                "scenarioId": scenario.scenario_id.value,
                "agentId": scenario.agent_id,
                "revisionId": scenario.agent_revision_id,
            }
            for scenario in receipt.scenarios
        ],
        "warning": (
            "real Android effects require operator-controlled positive then "
            "restored-precondition controlled-negative execution"
        ),
    }


def start_campaign_server(inputs: AndroidViewCampaignInputs) -> AndroidViewCampaignServer:
    """Load trusted authority and start one production-composed C-2 backend.

    This function must only be called through ``start_after_prerequisite``.

    Args:
        inputs: Private inputs containing an already validated receipt.

    Raises:
        OSError: Profile, database, package, or listener setup fails.
        ValueError: Target, Agent, Catalog, or selected matrix drifts.

    Returns:
        Owned running server with a safe public bootstrap.
    """
    from zhixing.studio import (
        SQLiteAgentDocumentRepository,
        StudioApplicationService,
        build_default_replay_service,
        build_default_studio_benchmark_composition,
        build_studio_component_catalog,
    )
    from zhixing.studio.benchmark_service import StudioBenchmarkSource
    from zhixing.studio.device_profiles import (
        load_android_device_profiles,
        resolve_exact_android_session,
    )
    from zhixing.studio.httpd import create_http_server
    from zhixing.studio.run_execution import ProductionComponentResolverFactory

    profiles = load_android_device_profiles(inputs.device_profile_config)
    profile = profiles.resolve(inputs.receipt.selection.device_profile_id)
    session = resolve_exact_android_session(profile)
    if session.environment_candidate != "real_android" or session.serial is None:
        raise ValueError("C-2 acceptance requires an exact real Android target")

    source_databases = _scenario_databases(inputs.service_summary)
    source_repositories = tuple(
        SQLiteAgentDocumentRepository(path) for path in source_databases
    )
    agents = CompositeReadOnlyAgentRepository(source_repositories)
    _verify_prerequisite_agents(agents, inputs.receipt)

    inputs.workspace.mkdir(parents=True, exist_ok=False)
    database = inputs.workspace / "studio.sqlite3"
    graph_catalog = build_studio_component_catalog()
    application_service = StudioApplicationService(
        catalog=graph_catalog,
        repository=agents,
        replay_service=build_default_replay_service(database),
    )
    llm = SequentialBrowserCampaignLLM(x=inputs.x, y=inputs.y)
    package_root = ROOT / "benchmarks" / "android_world"
    composition = build_default_studio_benchmark_composition(
        inputs.workspace,
        agents=agents,
        profiles=profiles,
        contract_catalog=graph_catalog.node_contract_catalog(),
        sources=(
            StudioBenchmarkSource(
                source_id="android-view-acceptance-package",
                kind="package",
                locator=package_root,
            ),
        ),
        include_installed=False,
        database_path=database,
        component_resolvers=ProductionComponentResolverFactory(
            dependency_provider={"llm": llm}
        ),
    )
    try:
        entries = composition.catalog.list_entries(limit=100).items
        entry = next(
            (item for item in entries if item.package_identity == PACKAGE_IDENTITY),
            None,
        )
        if entry is None:
            raise ValueError("approved AndroidWorld Package is unavailable")
        tasks = composition.catalog.list_tasks(
            entry.catalog_entry_id,
            split=SPLIT,
            limit=100,
        ).items
        if not any(item.task_id == TASK_ID for item in tasks):
            raise ValueError("approved AndroidWorld_6 task is unavailable")
        server = create_http_server(
            "127.0.0.1",
            inputs.port,
            application_service=application_service,
            benchmark_composition=composition,
            sse_heartbeat_seconds=0.25,
            sse_write_timeout_seconds=1.0,
            benchmark_sse_max_connections=4,
        )
    except Exception:
        composition.shutdown(wait=True)
        raise
    thread = threading.Thread(
        target=server.serve_forever,
        name="zhixing-android-view-acceptance-http",
        daemon=True,
    )
    thread.start()
    api_base_url = f"http://127.0.0.1:{int(server.server_address[1])}"
    return AndroidViewCampaignServer(
        server=server,
        thread=thread,
        composition=composition,
        bootstrap=_safe_bootstrap(
            api_base_url=api_base_url,
            receipt=inputs.receipt,
            catalog_entry_id=entry.catalog_entry_id,
        ),
        llm=llm,
    )


def launch_campaign_server(
    *,
    confirm_real_android: bool,
    service_summary: Path,
    device_profile_id: str,
    device_profile_config: Path,
    workspace: Path,
    port: int,
    x: int,
    y: int,
    starter: Callable[[AndroidViewCampaignInputs], AndroidViewCampaignServer] = (
        start_campaign_server
    ),
) -> AndroidViewCampaignServer:
    """Gate and launch the real campaign with observable effect ordering.

    Args:
        confirm_real_android: Explicit operator acknowledgement.
        service_summary: Strict C-1 summary at its retained campaign root.
        device_profile_id: Safe public profile identity.
        device_profile_config: Trusted local private profile configuration.
        workspace: New disposable C-2 durable root.
        port: Loopback listener port, zero for an ephemeral port.
        x: Positive shutter horizontal coordinate.
        y: Positive shutter vertical coordinate.
        starter: Injectable effectful server builder for no-device tests.

    Raises:
        OSError: Required local resources cannot be read.
        ValueError: Confirmation, prerequisite, path, or matrix is invalid.

    Returns:
        Owned running campaign server.
    """
    if not 0 <= port <= 65535:
        raise ValueError("acceptance server port must be between 0 and 65535")

    def start(receipt: BrowserPrerequisiteEvidence) -> AndroidViewCampaignServer:
        """Resolve private launch inputs only after prerequisite validation.

        Args:
            receipt: Complete validated C-1 receipt.

        Raises:
            ValueError: Workspace or profile configuration path is invalid.

        Returns:
            Owned server returned by the injected effectful builder.
        """
        safe_workspace = _safe_disposable_workspace(workspace)
        config = device_profile_config.expanduser().resolve()
        if not config.is_file():
            raise FileNotFoundError("trusted device profile configuration is unavailable")
        return starter(
            AndroidViewCampaignInputs(
                receipt=receipt,
                service_summary=service_summary.expanduser().resolve(),
                device_profile_config=config,
                workspace=safe_workspace,
                port=port,
                x=x,
                y=y,
            )
        )

    return start_after_prerequisite(
        confirm_real_android=confirm_real_android,
        service_summary=service_summary,
        device_profile_id=device_profile_id,
        starter=start,
    )


def _parser() -> argparse.ArgumentParser:
    """Build the explicit gated real-server command parser.

    Returns:
        Configured narrow launcher parser.
    """
    parser = argparse.ArgumentParser(
        description="Run the gated Stage 5.6C-2 real Android acceptance server."
    )
    parser.add_argument("--confirm-real-android", action="store_true", required=True)
    parser.add_argument("--service-summary", type=Path, required=True)
    parser.add_argument("--device-profile-id", required=True)
    parser.add_argument("--device-profile-config", type=Path, required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--x", type=int, default=540)
    parser.add_argument("--y", type=int, default=2052)
    return parser


def _install_signal_handlers(stopped: threading.Event) -> None:
    """Install bounded SIGINT/SIGTERM shutdown handlers.

    Args:
        stopped: Event set when a shutdown signal arrives.

    Raises:
        ValueError: Signal handlers cannot be installed in this thread.

    Returns:
        None.
    """

    def stop(_signum: int, _frame: Any) -> None:
        """Request graceful teardown without signal-handler I/O.

        Args:
            _signum: Received signal number.
            _frame: Interrupted interpreter frame.

        Returns:
            None.
        """
        stopped.set()

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)


def main(argv: list[str] | None = None) -> int:
    """Start the gated server, emit one safe bootstrap, and await teardown.

    Args:
        argv: Optional arguments excluding the executable name.

    Raises:
        OSError: Required trusted or durable resources are unavailable.
        ValueError: Prerequisite, target, Agent, or Catalog facts drift.

    Returns:
        Zero after deterministic graceful teardown.
    """
    args = _parser().parse_args(argv)
    with contextlib.redirect_stdout(sys.stderr):
        campaign = launch_campaign_server(
            confirm_real_android=args.confirm_real_android,
            service_summary=args.service_summary,
            device_profile_id=args.device_profile_id,
            device_profile_config=args.device_profile_config,
            workspace=args.workspace,
            port=args.port,
            x=args.x,
            y=args.y,
        )
    print(json.dumps(campaign.bootstrap, sort_keys=True), flush=True)
    stopped = threading.Event()
    _install_signal_handlers(stopped)
    try:
        while not stopped.wait(timeout=0.5):
            continue
    finally:
        campaign.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

