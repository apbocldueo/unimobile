"""Developer-only schema-3 ordinary Run acceptance with production gates enabled."""

from __future__ import annotations

import threading
import socket
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from unittest.mock import patch

from PIL import Image, ImageDraw

from tests.runtime.test_android_graph_runtime import FakeAndroidDevice
from tests.studio.test_run_execution import SequentialActionLLM
from zhixing.studio import SQLiteAgentDocumentRepository, StudioApplicationService
from zhixing.studio.catalog import build_studio_component_catalog
from zhixing.studio.eligibility import evaluate_revision_eligibility
from zhixing.studio.flow_template_loader import get_flow_template_document
from zhixing.studio.replay_service import build_default_replay_service
from zhixing.studio.run_composition import StudioRunComposition, build_default_studio_run_composition
from zhixing.studio.run_execution import (
    AndroidDeviceProfile, AndroidDeviceProfileResolver, ProductionComponentResolverFactory,
)


@contextmanager
def forbid_real_effects():
    """Deny real device construction/discovery, subprocesses and non-loopback TCP.

    This is an acceptance canary, not an untrusted-plugin security sandbox.
    Raises:
        RuntimeError: An instrumented forbidden boundary is attempted.
    Yields:
        Mutable attempted-effect counters, including violations caught by runtime.
    """
    counts = {"real-device": 0, "external-network": 0, "real-secret": 0}
    original_connect = socket.socket.connect

    def deny_device(*args, **kwargs):
        """Count and reject device/subprocess operations without performing them."""
        del args, kwargs
        counts["real-device"] += 1
        raise RuntimeError("FAKE acceptance forbids real device or subprocess effects")

    def connect(sock, address):
        """Allow literal loopback HTTP/SSE while rejecting external connections.

        Args:
            sock: Socket whose original connector is delegated only for loopback.
            address: Requested socket address.
        Raises:
            RuntimeError: A non-loopback connection was attempted.
        Returns:
            Original loopback connection result.
        """
        if not isinstance(address, tuple) or address[0] not in {"127.0.0.1", "::1"}:
            counts["external-network"] += 1
            raise RuntimeError("FAKE acceptance forbids external connections")
        return original_connect(sock, address)

    with ExitStack() as stack:
        stack.enter_context(patch("zhixing.studio.device_profiles.AndroidDevice.__init__", deny_device))
        stack.enter_context(patch("zhixing.studio.device_profiles.AndroidDevice.list_device_states", deny_device))
        stack.enter_context(patch("subprocess.Popen", deny_device))
        stack.enter_context(patch.object(socket.socket, "connect", connect))
        yield counts


@dataclass
class RunControl:
    """One bounded fake execution window; counters never retain prompts or secrets."""

    hold: bool = False
    fail_at: int | None = None
    timeout: float = 120
    started: threading.Event = field(default_factory=threading.Event)
    release: threading.Event = field(default_factory=threading.Event)
    model_calls: int = 0
    executions: int = 0
    secret_attempts: int = 0

    def deny_secret(self, reference: str):
        """Reject any secret resolution; the injected scripted model needs none.

        Args:
            reference: Unlogged SecretRef name.
        Raises:
            RuntimeError: Any secret lookup is attempted.
        """
        del reference
        self.secret_attempts += 1
        raise RuntimeError("FAKE acceptance does not resolve real secrets")


class AcceptanceLLM(SequentialActionLLM):
    """TAP then DONE without a provider client, network, or stored prompt."""

    def __init__(self, control: RunControl) -> None:
        """Initialize a fresh bounded response script for a single Run.

        Args:
            control: Shared test-only hold and safe counter authority.
        """
        super().__init__()
        self.control = control
        self.index = 0

    def generate(self, prompt: str, images: list[str] | None = None) -> str:
        """Return one scripted response, optionally holding or failing deterministically.

        Args:
            prompt: Ignored model input; never retained by this fake.
            images: Ignored observation inputs.
        Raises:
            TimeoutError: The explicit acceptance hold was not released in time.
            RuntimeError: A selected controlled failure or extra invocation occurs.
        Returns:
            Parser-compatible TAP or DONE response.
        """
        del prompt, images
        self.index += 1
        self.control.model_calls += 1
        self.control.started.set()
        if self.control.hold and not self.control.release.wait(self.control.timeout):
            raise TimeoutError("FAKE acceptance hold timed out")
        if self.index == self.control.fail_at:
            raise RuntimeError("FAKE controlled reasoning failure")
        if not self.responses:
            raise RuntimeError("FAKE bounded script exhausted")
        return self.responses.pop(0)


class AcceptanceDevice(FakeAndroidDevice):
    """Fake device with visibly synthetic, valid PNG observations."""

    w = 360
    h = 640

    def screenshot(self, path: str) -> str:
        """Write a labelled synthetic frame with its observation number.

        Args:
            path: Runtime-allocated artifact destination.
        Raises:
            OSError: Artifact writing fails.
        Returns:
            Unchanged destination path.
        """
        number = sum(call[0] == "screenshot" for call in self.calls) + 1
        frame = Image.new("RGB", (self.w, self.h), (22, 37, 54))
        draw = ImageDraw.Draw(frame)
        draw.text((24, 40), "FAKE / NO REAL DEVICE", fill="white")
        draw.text((24, 80), f"Observation {number}", fill="white")
        draw.rectangle((20, 130, 330, 220), fill=(50, 100, 140))
        draw.text((35, 160), "Synthetic acceptance target", fill="white")
        frame.save(path, format="PNG")
        self.calls.append(("screenshot", path))
        return path


class AcceptanceResolver(ProductionComponentResolverFactory):
    """Keep production metadata/binding behavior and allocate a fresh fake per Run."""

    def __init__(self, control: RunControl) -> None:
        """Keep an explicit runtime test authority without external discovery.

        Args:
            control: Test-only execution control.
        """
        super().__init__()
        self.control = control

    def create(self):
        """Create a normal resolver with only its model dependency replaced.

        Returns:
            Production component resolver using one fresh bounded fake model.
        """
        self.control.executions += 1
        return ProductionComponentResolverFactory(
            dependency_provider={"llm": AcceptanceLLM(self.control)},
            secret_provider=self.control.deny_secret,
        ).create()


@dataclass
class RunExperienceHarness:
    """Owned, isolated real Studio composition and its test boundary counters."""

    authoring: StudioApplicationService
    composition: StudioRunComposition
    agent_id: str
    revision_id: str
    device: AcceptanceDevice
    control: RunControl

    def close(self) -> None:
        """Release held fake calls before waiting for owned worker shutdown."""
        self.control.release.set()
        self.composition.shutdown(wait=True)


def build_run_experience_harness(root: Path, *, control: RunControl | None = None) -> RunExperienceHarness:
    """Compile the shipped template and enable all production launch checks.

    Args:
        root: Fresh isolated directory, never a production workspace.
        control: Optional bounded hold/failure configuration.
    Raises:
        ValueError: Directory is not fresh or template/readiness is ineligible.
        OSError: Isolated storage cannot be created.
    Returns:
        Owned harness; callers must close it, including on failed assertions.
    """
    root.mkdir(parents=True, exist_ok=True)
    if any(root.iterdir()):
        raise ValueError("acceptance requires an empty isolated directory")
    selected = control or RunControl()
    database = root / "studio.sqlite3"
    catalog = build_studio_component_catalog()
    agents = SQLiteAgentDocumentRepository(database)
    replay = build_default_replay_service(database)
    authoring = StudioApplicationService(catalog=catalog, repository=agents, replay_service=replay)
    agent, revision = authoring.create_agent(
        "FAKE / NO REAL DEVICE — Run acceptance",
        initial_document=get_flow_template_document("modular_baseline"),
    )
    eligibility = evaluate_revision_eligibility(revision, catalog=catalog)
    if not eligibility.current_policy_eligible:
        raise ValueError("shipped template is not current-policy eligible")
    device = AcceptanceDevice()
    composition = build_default_studio_run_composition(
        database,
        agents=agents,
        replay_service=replay,
        profiles=AndroidDeviceProfileResolver({
            "acceptance-fake": AndroidDeviceProfile(
                "acceptance-fake", device=device, label="FAKE / NO REAL DEVICE",
            ),
        }),
        components=AcceptanceResolver(selected),
        component_catalog=catalog,
        # Presence metadata is synthetic. The injected model never resolves it.
        runtime_secrets={"api_key": "FAKE-NOT-A-CREDENTIAL", "base_url": "FAKE-NOT-A-URL"},
        enforce_readiness=True,
    )
    exact = composition.readiness.revision_readiness(agent.agent_id, revision.revision_id, "acceptance-fake")
    if not exact.ready:
        composition.shutdown(wait=True)
        raise ValueError(f"fake fixture failed production readiness: {[d.code for d in exact.diagnostics]}")
    return RunExperienceHarness(authoring, composition, agent.agent_id, revision.revision_id, device, selected)
