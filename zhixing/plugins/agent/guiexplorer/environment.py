"""Caller-owned original Device boundary with source ordering and explicit effects."""

from dataclasses import asdict
import time
from types import FunctionType, SimpleNamespace
from typing import Any, Callable

from zhixing.components import DeviceObservation, RuntimeContext

from . import source


class _TrackedDevice:
    """Forward source device methods, retaining only confirmed effect names."""

    def __init__(self, device, effects):
        """Bind a caller-owned device and a per-action effect list.

        Args:
            device: Original-compatible Device.
            effects: Mutable private operation-name list.
        Returns:
            None.
        """
        self.device, self.effects = device, effects

    def __getattr__(self, name):
        """Forward one original operation and record success after it returns.

        Args:
            name: Original device method name.
        Returns:
            Callable: Forwarder with no live values in its effect record.
        """
        method = getattr(self.device, name)

        def call(*args, **kwargs):
            """Perform the explicit device effect and remember its name.

            Args:
                args, kwargs: Unmodified source device arguments.
            Raises:
                Exception: The underlying device operation fails.
            Returns:
                Any: Unmodified original result.
            """
            value = method(*args, **kwargs)
            self.effects.append(name)
            return value

        return call


class GUIExplorerEnvironment:
    """Wrap an explicit source-compatible Device; construction performs no I/O."""

    platform = "android"
    serial = ""

    def __init__(self, device: Any, *, sleep: Callable[[float], None] = time.sleep) -> None:
        """Bind the device and a private timing namespace for original dispatch.

        Args:
            device: Already-created official or original-compatible Device, caller-owned.
            sleep: Injectable source timing boundary.
        Raises:
            TypeError: Required source observation operations are absent.
        Returns:
            None.
        """
        required = ("wait_to_stabilize", "_get_ui_elements", "get_orientation", "get_screen_size",
                    "get_physical_frame_boundary", "get_screenshot", "get_top_package_name")
        if not all(callable(getattr(device, name, None)) for name in required):
            raise TypeError("GUI-explorer requires an explicit original-compatible Device")
        self.device, self.effects, self._sequence = device, [], 0
        # Clone only function globals, not algorithms, to inject a per-run clock.
        # This avoids mutating module globals when two runs use different devices.
        namespace = {**vars(source), "time": SimpleNamespace(sleep=sleep)}
        for name in ("execute_adb_action", "launch_app", "send_android_intent", "display_message", "change_orientation"):
            original = getattr(source, name)
            namespace[name] = FunctionType(original.__code__, namespace, name, original.__defaults__, original.__closure__)
        self._dispatch = namespace["execute_adb_action"]

    def observe(self, runtime: RuntimeContext, *, after: bool = False) -> DeviceObservation:
        """Capture exact source before/after UI, geometry and screenshot order.

        Args:
            runtime: Run-owned artifact/observation services.
            after: Use the source post-action stable wait followed by fresh UI reading.
        Raises:
            Exception: Device observation or evidence persistence fails.
        Returns:
            DeviceObservation: Portable UI data and lossless source pixels.
        """
        elements = self.device.wait_to_stabilize()
        orientation = self.device.get_orientation()
        logical = tuple(self.device.get_screen_size())
        physical = tuple(self.device.get_physical_frame_boundary())
        if after:
            elements = self.device._get_ui_elements()
        data = {"ui_elements": tuple(asdict(element) for element in elements),
                "logical_screen_size": logical, "physical_frame_boundary": physical, "orientation": orientation}
        image = self.device.get_screenshot()
        if not after:
            image = image.convert("RGB")
            data["top_app_package_name"] = self.device.get_top_package_name()
        allocated = runtime.artifacts.allocate_observation(runtime.step, include_ui_tree=False)
        image.save(allocated.screenshot_path)
        runtime.artifacts.verify_file(allocated.screenshot_path, minimum_size=8)
        ui_path = allocated.screenshot_path.with_suffix(".ui.json")
        runtime.artifacts.write_json(ui_path, data)
        observation = DeviceObservation(screenshot_path=str(allocated.screenshot_path),
            width=image.width, height=image.height, platform="android", sequence=self._sequence,
            interaction_step=runtime.step, screenshot_artifact=allocated.screenshot_reference,
            metadata={"guiexplorer": data, "source_ui_artifact": runtime.artifacts.reference(ui_path)})
        self._sequence += 1
        runtime.state.last_observation = observation
        runtime.state.observation_history.append(observation)
        return observation

    def execute(self, action, elements, screen_size):
        """Delegate unchanged source actions and retain confirmed device-effect names.

        Args:
            action: Official JSONAction.
            elements: Full original before-action element list.
            screen_size: Original logical dimensions.
        Raises:
            Exception: Original validation, timing or device execution fails.
        Returns:
            tuple | None: Original actual action coordinates.
        """
        self.effects.clear()
        result = self._dispatch(action, _TrackedDevice(self.device, self.effects), elements, screen_size)
        if action.action_type == "wait":
            self.effects.append("wait")
        return result

    def wait_round(self) -> None:
        """Perform the official run-loop extra wait after every nonterminal step.

        Raises:
            Exception: The source stable-state read fails.
        Returns:
            None.
        """
        self.device.wait_to_stabilize()


def environment(runtime: RuntimeContext) -> GUIExplorerEnvironment:
    """Require the explicit source bridge instead of silently switching device semantics.

    Args:
        runtime: Run context with the caller-owned environment.
    Raises:
        TypeError: No source-compatible explicit environment was provided.
    Returns:
        GUIExplorerEnvironment: Live boundary, never stored in graph data.
    """
    if not isinstance(runtime.device, GUIExplorerEnvironment):
        raise TypeError("Pass device=GUIExplorerEnvironment(original_device)")
    return runtime.device
