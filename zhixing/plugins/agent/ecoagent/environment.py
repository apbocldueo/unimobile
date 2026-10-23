"""Explicit serial-bound device and run-owned I/O lifetime, outside portable State."""

import time

from PIL import Image

from zhixing.components import DeviceObservation
from .io_jobs import InferenceJobs


class EcoEnvironment:
    """Caller-owned adapter; context entry is required for every Agent run."""

    platform = 'android'

    def __init__(self, device, *, sleep=time.sleep):
        """Retain explicit services without connecting or creating threads.

        Args:
            device: Already-selected AndroidDevice or compatible caller device.
            sleep: Injectable original two-second wait.
        Returns:
            None.
        """
        self.device, self.sleep = device, sleep
        self.serial = getattr(device, 'serial', '')
        self.jobs = None

    def __enter__(self):
        """Begin a fresh isolated run scope.

        Raises:
            RuntimeError: The boundary is already entered.
        Returns:
            EcoEnvironment: Same explicit device boundary.
        """
        if self.jobs is not None:
            raise RuntimeError('EcoEnvironment is already active')
        self.jobs = InferenceJobs()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        """Drain submitted I/O even after binding/runtime failure or cancellation.

        Args:
            exc_type,exc_value,traceback: Caller exception context, never suppressed.
        Returns:
            None.
        """
        try:
            self.jobs.close()
        finally:
            self.jobs = None

    def capture(self, runtime):
        """Capture pixels into immutable run artifacts without XML or shared paths.

        Args:
            runtime: Current observation/artifact context.
        Raises:
            Exception: Explicit device capture or artifact verification fails.
        Returns:
            DeviceObservation: Source screenshot and its evidence reference.
        """
        allocated = runtime.artifacts.allocate_observation(runtime.step, include_ui_tree=False)
        self.device.screenshot(str(allocated.screenshot_path))
        runtime.artifacts.verify_file(allocated.screenshot_path, minimum_size=8)
        with Image.open(allocated.screenshot_path) as image:
            width, height = image.size
        observation = DeviceObservation(screenshot_path=str(allocated.screenshot_path),
            width=width, height=height, platform='android', interaction_step=runtime.step,
            sequence=len(runtime.state.observation_history), screenshot_artifact=allocated.screenshot_reference)
        runtime.state.last_observation = observation
        runtime.state.observation_history.append(observation)
        return observation

    def execute_command(self, command, *, check=False):
        """Execute only a decoder-produced command through the selected device boundary.

        Args:
            command: Source decoder command starting with adb shell, possibly joined Enter.
            check: Preserve checked direct calls versus unchecked model-decoded calls.
        Raises:
            ValueError: Command is not a source-supported shell command.
            Exception: Device transport raises or checked execution fails.
        Returns:
            bool: Whether every command reported a zero exit code.
        """
        prefix = 'adb shell '
        if not command.startswith(prefix):
            raise ValueError('Unsupported EcoAgent decoder command')
        # The only compound source command is text followed by an Enter key.
        suffix = ' && adb shell input keyevent KEYCODE_ENTER'
        if command.endswith(suffix):
            first = command[:-len(suffix)]
            ok = self.execute_command(first, check=check)
            return ok and self.execute_command('adb shell input keyevent KEYCODE_ENTER', check=check)
        result = self.device.shell(command[len(prefix):], error_raise=check)
        return getattr(result, 'exit_code', 0) == 0


def environment(runtime):
    """Require an entered run-owned boundary instead of silently selecting any device.

    Args:
        runtime: Current explicit runtime context.
    Raises:
        TypeError: Caller did not enter an EcoEnvironment.
    Returns:
        EcoEnvironment: Claimed exclusively by this run.
    """
    boundary = runtime.device
    if not isinstance(boundary, EcoEnvironment) or boundary.jobs is None:
        raise TypeError('Run EcoAgent inside with EcoEnvironment(device) as boundary')
    boundary.jobs.claim(runtime.run_id)
    return boundary
