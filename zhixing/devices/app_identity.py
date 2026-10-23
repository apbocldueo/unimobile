"""Explicit Android foreground READ boundaries for frame-bound observations."""

import re

from zhixing.components import DeviceExecutionError, ObservationRequest
from zhixing.core.factory import PluginRegistry
from zhixing.plugins.agent.agent_sama_types import AppIdentity, require_frame


def read_foreground_identity(device) -> AppIdentity:
    """Read the current resumed component through the selected device boundary.

    Args:
        device: Explicit Android-compatible target with shell support.
    Raises:
        DeviceExecutionError: Foreground identity is unavailable or ambiguous.
    Returns:
        AppIdentity: Package and fully qualified activity, never the device serial.
    """
    try:
        result = device.shell("dumpsys activity activities")
        if result.exit_code != 0 or getattr(result, "timed_out", False):
            raise ValueError("foreground read failed")
        components = re.findall(r"(?:topResumedActivity|mResumedActivity)\s*[:=][^\n]*?\s([A-Za-z0-9_.]+)/([A-Za-z0-9_.$]+)", result.output)
        normalized = {(package, package + activity if activity.startswith(".") else activity)
                      for package, activity in components}
        if len(normalized) != 1:
            raise ValueError("no unique foreground activity")
        package, activity = normalized.pop()
        return AppIdentity(package=package, activity=activity)
    except Exception:
        raise DeviceExecutionError("foreground_identity", "Unable to read authoritative foreground identity") from None


@PluginRegistry.register(namespace="device", name="agent_sama_identity_before")
class SamaIdentityBefore:
    """Read authoritative identity immediately before the graph screenshot."""

    def invoke(self, value, runtime):
        """Start a fresh binding attempt, clearing stale evidence first.

        Args:
            value: Frame whose observation is being refreshed.
            runtime: Selected device context.
        Raises:
            DeviceExecutionError: The foreground read fails.
        Returns:
            SamaFrame: Fresh pre-capture identity; no inherited bound flag.
        """
        frame = require_frame(value)
        return frame.model_copy(update={"identity_before": read_foreground_identity(runtime.device),
            "identity_after": None, "observation": None, "observation_bound": False})


@PluginRegistry.register(namespace="device", name="agent_sama_identity_after")
class SamaIdentityAfter:
    """Read identity after the exact DeviceObserve activation has returned."""

    def invoke(self, value, runtime):
        """Attach the screenshot and post-capture identity without certifying it.

        Args:
            value: Declared frame and device_observation input mapping.
            runtime: Selected device context.
        Raises:
            DeviceExecutionError: Foreground identity is unavailable.
        Returns:
            SamaFrame: Evidence ready for pure bracket validation.
        """
        frame = require_frame(value["value"])
        return frame.model_copy(update={"observation": value["observation"],
            "identity_after": read_foreground_identity(runtime.device)})


@PluginRegistry.register(namespace="agent.perception", name="agent_sama_bind_observation")
class SamaBindObservation:
    """Purely compare the two authoritative reads for this screenshot."""

    def invoke(self, value, runtime):
        """Accept only a complete matching package/activity bracket.

        Args:
            value: Pre/post identity and exact screenshot.
            runtime: Unused context.
        Returns:
            SamaFrame: Binding result controlling the bounded observation loop.
        """
        del runtime
        frame = require_frame(value)
        bound = bool(frame.observation is not None and frame.identity_before is not None
                     and frame.identity_before.package and frame.identity_before.activity
                     and frame.identity_before == frame.identity_after)
        return frame.model_copy(update={"observation_bound": bound})


@PluginRegistry.register(namespace="agent.perception", name="agent_sama_observation_request")
class SamaObservationRequest:
    """Request a fresh screenshot through the existing artifact service."""

    def invoke(self, value, runtime):
        """Create a typed observation request without reading the device.

        Args:
            value: Frame after the pre-capture READ.
            runtime: Unused context.
        Returns:
            ObservationRequest: Existing screenshot-only service request.
        """
        del runtime
        require_frame(value)
        return ObservationRequest(include_ui_tree=False)
