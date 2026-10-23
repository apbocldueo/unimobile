"""Explicit AndroidWorld boundary, preserving original observation/action semantics."""

from __future__ import annotations

import time
from typing import Any, Callable

from zhixing.components import DeviceObservation, RuntimeContext
from zhixing.runtime.artifacts import RunArtifactStore

from .types import portable_ui


class M3AEnvironment:
    """Wrap an already-created official AsyncEnv; construction does not connect it."""

    platform = "android"
    serial = ""

    def __init__(self, env: Any, *, sleep: Callable[[float], None] = time.sleep,
                 termination_fn: Callable[[Any], Any] | None = None) -> None:
        """Bind an official environment and a testable timing boundary.

        Args:
            env: Explicit AndroidWorld AsyncEnv, owned and closed by the caller.
            sleep: Wait implementation; production uses time.sleep.
            termination_fn: Optional original episode environment-termination hook.
        Raises:
            TypeError: Required original environment methods are absent.
        Returns:
            None.
        """
        if not all(callable(getattr(env, key, None)) for key in
                   ("get_state", "execute_action", "reset", "hide_automation_ui")):
            raise TypeError("M3A requires an explicit AndroidWorld AsyncEnv")
        self._env = env
        self._sleep = sleep
        self._sequence = 0
        self._termination_fn = termination_fn

    def should_terminate(self) -> bool:
        """Evaluate the optional original episode hook after a complete decision round.

        Raises:
            Exception: The caller-provided original hook fails.
        Returns:
            bool: Source truthiness of the hook result, otherwise False.
        """
        return bool(self._termination_fn(self._env)) if self._termination_fn is not None else False

    def reset(self, go_home: bool) -> None:
        """Apply the source reset and hide the automation pointer overlay.

        Args:
            go_home: Source episode start_on_home_screen setting.
        Raises:
            Exception: Original reset or overlay operation fails.
        Returns:
            None.
        """
        self._env.reset(go_home=go_home)
        self._env.hide_automation_ui()
        self._sequence = 0

    def observe(self, runtime: RuntimeContext, pause: float | None) -> DeviceObservation:
        """Capture an original state, preserving the source pause/stability policy.

        Args:
            runtime: Run-owned artifact and evidence services.
            pause: None enables original stable-state polling; otherwise sleep first.
        Raises:
            Exception: Original observation, geometry or artifact capture fails.
        Returns:
            DeviceObservation: Lossless screenshot and full portable source UI data.
        """
        from PIL import Image

        if not isinstance(runtime.artifacts, RunArtifactStore):
            raise TypeError("M3A observation requires a run artifact store")
        if pause is not None:
            self._sleep(pause)
        state = self._env.get_state(wait_to_stabilize=pause is None)
        geometry = {
            "logical_screen_size": tuple(self._env.logical_screen_size),
            "orientation": self._env.orientation,
            "physical_frame_boundary": tuple(self._env.physical_frame_boundary),
        }
        ui = portable_ui(state.ui_elements)
        allocated = runtime.artifacts.allocate_observation(runtime.step, include_ui_tree=False)
        image = Image.fromarray(state.pixels.copy())
        image.save(allocated.screenshot_path)
        runtime.artifacts.verify_file(allocated.screenshot_path, minimum_size=8)
        ui_path = allocated.screenshot_path.with_suffix(".ui.json")
        runtime.artifacts.write_json(ui_path, {"elements": ui, **geometry})
        observation = DeviceObservation(
            screenshot_path=str(allocated.screenshot_path), width=image.width, height=image.height,
            platform="android", sequence=self._sequence, interaction_step=runtime.step,
            screenshot_artifact=allocated.screenshot_reference,
            metadata={"m3a": {"ui_elements": ui, **geometry},
                      "source_ui_artifact": runtime.artifacts.reference(ui_path)},
        )
        self._sequence += 1
        runtime.state.last_observation = observation
        runtime.state.observation_history.append(observation)
        return observation

    def execute(self, action: Any) -> None:
        """Delegate JSONAction unchanged, including refresh, text, scroll and answer.

        Args:
            action: Pinned source-compatible JSONAction.
        Raises:
            Exception: Original environment execution fails; graph routing handles it.
        Returns:
            None.
        """
        self._env.execute_action(action)


def environment(runtime: RuntimeContext) -> M3AEnvironment:
    """Require the explicit bridge instead of silently substituting generic XML/ADB.

    Args:
        runtime: Run context with an explicitly supplied device boundary.
    Raises:
        TypeError: A generic Android device or missing environment was supplied.
    Returns:
        M3AEnvironment: The run's bridge, never serialized as component data.
    """
    if not isinstance(runtime.device, M3AEnvironment):
        raise TypeError("Pass device=M3AEnvironment(official_async_env) to run M3A")
    return runtime.device
