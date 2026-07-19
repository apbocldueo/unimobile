import re
from typing import Dict, Any, Optional

from zhixing.core.benchmark.protocol import EvalResult
from zhixing.core.benchmark.base_system import BaseSystemAction
from zhixing.core.factory import PluginRegistry

# Same as ``adb shell "dumpsys window | grep mCurrentFocus"``: pipe runs on the device.
_DUMPSYS_FOCUS_CMD = "dumpsys window | grep mCurrentFocus"


def _parse_focus_package(raw: str) -> Optional[str]:
    """Parse the foreground package name from ``mCurrentFocus=Window{... u0 pkg/activity}`` style output."""
    if not raw or "mCurrentFocus" not in raw:
        return None
    # First segment of com.foo.bar/com.foo.BarActivity (package must contain a dot).
    for m in re.finditer(r"([\w][\w.]*\.[\w.]+)/([\w.]+)", raw):
        pkg = m.group(1)
        if "." in pkg and not pkg.startswith("Window"):
            return pkg
    return None


@PluginRegistry.register(namespace="evaluator.system_state", name="foreground_app_validator")
class ForegroundAppValidatorAction(BaseSystemAction):
    """Pass if the focused window belongs to the expected app (compare ``mCurrentFocus`` package via ``dumpsys window``).

    The logical ``app`` key is resolved through ``device.app_package_names`` (same as Agent / reset plugins).
    Alternatively, pass ``package`` with the full application id to skip the alias map.

    Task JSON example::

        {
            "name": "system_state",
            "params": {
                "method": "foreground_app_validator",
                "app": "audio recorder"
            }
        }

    Or with an explicit package id::

        "params": {
            "method": "foreground_app_validator",
            "package": "com.dimowner.audiorecorder"
        }
    """

    def evaluate(self, context: Dict[str, Any]) -> EvalResult:
        # get_param raises when the key is missing and default is None; use "" for optional fields.
        package_param = self.get_param("package", context, default="", expected_type=str).strip()
        app_key = self.get_param("app", context, default="", expected_type=str).strip()

        expected: Optional[str] = None
        if package_param:
            expected = package_param
        elif app_key:
            names = getattr(self.device, "app_package_names", None)
            if not names:
                return EvalResult(
                    is_pass=False,
                    reason="Device has no app_package_names mapping; use params.package instead.",
                )
            key = app_key.lower().strip()
            if key not in names:
                return EvalResult(
                    is_pass=False,
                    reason=f"Unknown app key {app_key!r}; known: {sorted(names.keys())}",
                )
            expected = names[key]
        else:
            return EvalResult(
                is_pass=False,
                reason="Missing required param: provide 'app' (logical name) or 'package' (full package id).",
            )

        self.logger.info("foreground_app_validator expect_package=%r (app=%r)", expected, app_key)

        raw = self._run_device_shell(_DUMPSYS_FOCUS_CMD)
        if raw.startswith("ERROR:"):
            return EvalResult(is_pass=False, reason=f"Shell failed: {raw}")

        current = _parse_focus_package(raw)
        if not current:
            preview = (raw or "")[:400]
            return EvalResult(
                is_pass=False,
                reason=f"Could not parse foreground package from mCurrentFocus. Raw (truncated): {preview!r}",
            )

        self.logger.info("foreground_app_validator current_package=%r", current)

        if current == expected:
            return EvalResult(
                is_pass=True,
                reason=f"Foreground matches expected package {expected!r}.",
            )

        return EvalResult(
            is_pass=False,
            reason=(
                f"Foreground package is {current!r}, expected {expected!r} "
                f"(raw mCurrentFocus line truncated: {(raw or '')[:300]!r})"
            ),
        )
