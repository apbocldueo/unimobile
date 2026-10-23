"""Explicit AndroidWorld and scoped ADB boundaries for AndroidGen's source protocol."""

from __future__ import annotations

import io
import shlex
import subprocess
from typing import Any, Callable

from zhixing.components import DeviceObservation, RuntimeContext
from zhixing.plugins.agent.m3a.types import portable_ui

from .source import Env


class AndroidGenAdb:
    """Run the original shell commands against an explicitly selected ADB target."""

    def __init__(self, adb_path: str = "adb", serial: str = "") -> None:
        """Remember the target without connecting to it.

        Args:
            adb_path: Executable used for source ADB commands.
            serial: Optional explicit ADB serial.
        Returns:
            None.
        """
        self.prefix = shlex.quote(adb_path) + (" -s " + shlex.quote(serial) if serial else "")

    def _command(self, command: str) -> str:
        """Rebind only the leading ADB executable, retaining original shell syntax.

        Args:
            command: Source command beginning with adb.
        Raises:
            ValueError: The source command is not an ADB command.
        Returns:
            str: Target-scoped shell command.
        """
        if not command.startswith("adb "):
            raise ValueError("AndroidGen ADB boundary requires an adb command")
        return self.prefix + command[3:]

    def system(self, command: str) -> int:
        """Execute the original side effect without replacing its return policy.

        Args:
            command: Original ADB shell command.
        Raises:
            OSError: The shell cannot be started.
        Returns:
            int: Shell status; original source ignores this value.
        """
        return subprocess.run(self._command(command), shell=True, check=False,
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode

    def popen(self, command: str) -> io.StringIO:
        """Read the original current-focus pipeline through the scoped target.

        Args:
            command: Original ADB/pipeline source string.
        Raises:
            OSError: The shell cannot be started.
        Returns:
            StringIO: Original-shaped read interface.
        """
        result = subprocess.run(self._command(command), shell=True, check=False,
                                capture_output=True, text=True)
        return io.StringIO(result.stdout)

    @property
    def patterns(self):
        """Load the official App aliases only at the device boundary.

        Raises:
            ImportError: AndroidWorld is unavailable.
        Returns:
            Mapping: Official activity alias patterns.
        """
        from android_world.env.adb_utils import _PATTERN_TO_ACTIVITY

        return _PATTERN_TO_ACTIVITY

    def get_adb_activity(self, app_name: str):
        """Resolve an App name using the official helper.

        Args:
            app_name: Original unmodified name.
        Raises:
            ImportError: AndroidWorld is unavailable.
        Returns:
            Any: Original activity or None.
        """
        from android_world.env.adb_utils import get_adb_activity

        return get_adb_activity(app_name)


class _TrackedEnv:
    """Count external calls while keeping the original source exception guards."""

    def __init__(self, owner) -> None:
        """Bind the explicit bridge. Args: owner: Environment bridge. Returns: None."""
        self.owner = owner

    def execute_action(self, action) -> None:
        """Delegate the unchanged JSONAction and record successful/attempted effects.

        Args:
            action: Original-compatible JSONAction.
        Raises:
            Exception: Original device execution fails.
        Returns:
            None.
        """
        self.owner.attempts.append(action.as_dict())
        self.owner.raw.execute_action(action)
        self.owner.completed.append(action.as_dict())

    def close(self) -> None:
        """Honor an explicit source close call. Raises: Exception: Close fails. Returns: None."""
        self.owner.close()


class _TrackedAdb:
    """Per-instance ADB forwarding; never patch the process-global os module."""

    def __init__(self, owner) -> None:
        """Bind the bridge. Args: owner: Environment bridge. Returns: None."""
        self.owner = owner

    def system(self, command):
        """Record and forward a source effect. Args: command: Source string. Raises: Exception: I/O fails. Returns: int: Status."""
        self.owner.shell_attempts += 1
        result = self.owner.adb.system(command)
        self.owner.shell_completed += 1
        return result

    def popen(self, command):
        """Forward a source read. Args: command: Source pipeline. Raises: Exception: I/O fails. Returns: Any: Reader."""
        return self.owner.adb.popen(command)

    @property
    def patterns(self):
        """Return source aliases. Raises: Exception: Loading fails. Returns: Mapping: Aliases."""
        return self.owner.adb.patterns

    def get_adb_activity(self, app_name):
        """Forward alias resolution. Args: app_name: Source name. Raises: Exception: Resolution fails. Returns: Any: Activity."""
        return self.owner.adb.get_adb_activity(app_name)


class AndroidGenEnvironment:
    """Bind a caller-owned AsyncEnv; construction performs no device operations."""

    platform = "android"
    serial = ""

    def __init__(self, env: Any, *, adb: Any = None,
                 geometry: Callable[[Any], dict[str, Any]] | None = None,
                 reset_on_setup: bool = False) -> None:
        """Bind original I/O services, without storing them in graph State.

        Args:
            env: Caller-owned AndroidWorld AsyncEnv, closed explicitly by the caller.
            adb: Scoped source ADB protocol; default uses AndroidGenAdb.
            geometry: Optional geometry provider; default uses original adb_utils.
            reset_on_setup: Reset Home as in source's internally-created Env path.
        Raises:
            TypeError: Original get_state/execute_action/close methods are absent.
        Returns:
            None.
        """
        if not all(callable(getattr(env, name, None)) for name in ("get_state", "execute_action", "close")):
            raise TypeError("AndroidGen requires an explicit AndroidWorld AsyncEnv")
        self.raw, self.adb, self.geometry = env, adb if adb is not None else AndroidGenAdb(), geometry
        self.reset_on_setup = reset_on_setup
        self._runtime = None
        self._sequence = 0
        self.attempts, self.completed = [], []
        self.shell_attempts = self.shell_completed = 0
        self.source = Env(_TrackedEnv(self), _TrackedAdb(self), self._source_observe)

    def setup(self) -> str:
        """Apply original setup once, including the injected-env keyboard/TTS policy.

        Raises:
            Exception: Reset, ADB or App reading fails.
        Returns:
            str: Original init_state App name.
        """
        if self.reset_on_setup:
            self.raw.reset(go_home=True)
        self.adb.system("adb shell pm disable-user com.google.android.inputmethod.latin")
        self.adb.system("adb shell pm disable-user com.google.android.tts")
        self.source.init_state = self.source.get_current_app()
        self._sequence = 0
        return self.source.init_state

    def observe(self, runtime: RuntimeContext) -> DeviceObservation:
        """Capture original UI, raw PNG, geometry and App in source order.

        Args:
            runtime: Run-local artifact and observation services.
        Raises:
            Exception: Capture, geometry or artifact persistence fails.
        Returns:
            DeviceObservation: Portable full-index UI data and lossless pixels.
        """
        from PIL import Image

        state = self.raw.get_state(wait_to_stabilize=True)
        logical = tuple(self.raw.logical_screen_size)
        if self.geometry is None:
            from android_world.env import adb_utils

            geometry = {"orientation": adb_utils.get_orientation(self.raw.base_env),
                        "physical_frame_boundary": tuple(adb_utils.get_physical_frame_boundary(self.raw.base_env))}
        else:
            geometry = dict(self.geometry(self.raw))
        allocated = runtime.artifacts.allocate_observation(runtime.step, include_ui_tree=False)
        image = Image.fromarray(state.pixels.copy())
        image.save(allocated.screenshot_path)
        observation = DeviceObservation(screenshot_path=str(allocated.screenshot_path),
            width=image.width, height=image.height, platform="android", sequence=self._sequence,
            interaction_step=runtime.step, screenshot_artifact=allocated.screenshot_reference,
            metadata={"androidgen": {"ui_elements": portable_ui(state.ui_elements),
                "logical_screen_size": logical, **geometry, "app": self.source.get_current_app()}})
        self._sequence += 1
        runtime.state.last_observation = observation
        runtime.state.observation_history.append(observation)
        return observation

    def _source_observe(self):
        """Support source code's observation helper inside the execution boundary.

        Raises:
            RuntimeError: No active source execution owns the callback.
            Exception: Capture or pure encoding fails.
        Returns:
            tuple: Original state and record dictionaries.
        """
        from .perception import encode_view

        if self._runtime is None:
            raise RuntimeError("source observation requires an active execution boundary")
        view = encode_view(self.observe(self._runtime))
        return dict(view.state), dict(view.record)

    def interact(self, code: str, runtime: RuntimeContext):
        """Execute the original Python protocol, retaining original error recovery.

        Args:
            code: Unmodified model code block; this is trusted Python, not a sandbox.
            runtime: Explicit observation callback scope.
        Raises:
            Exception: A source exception escapes the original Exception guard.
        Returns:
            Mapping | None: Original execution result, including source None behavior.
        """
        self.attempts, self.completed = [], []
        self.shell_attempts = self.shell_completed = 0
        self._runtime = runtime
        try:
            return self.source.interact(code)
        finally:
            self._runtime = None

    def close(self) -> None:
        """Close the caller's environment explicitly. Raises: Exception: Close fails. Returns: None."""
        self.raw.close()


def environment(runtime: RuntimeContext) -> AndroidGenEnvironment:
    """Require AndroidGen's explicit original-device bridge.

    Args:
        runtime: Run context with caller-supplied device.
    Raises:
        TypeError: Device is a generic or incompatible bridge.
    Returns:
        AndroidGenEnvironment: Run-owned external services.
    """
    if not isinstance(runtime.device, AndroidGenEnvironment):
        raise TypeError("Pass device=AndroidGenEnvironment(official_async_env)")
    return runtime.device
