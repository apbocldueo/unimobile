from typing import Dict, Any

from zhixing.core.benchmark.interface import BaseEnvironmentInitializerOperation
from zhixing.core.benchmark.protocol import EnvironmentInitializerPluginType
from zhixing.core.factory import PluginRegistry


@PluginRegistry.register(namespace="benchmark.environment.reset", name="android_pm_clear")
class AndroidPmClearPackage(BaseEnvironmentInitializerOperation):
    """``adb shell pm clear <package>`` — clear app/provider data without ``sqlite3`` or ``/data`` access.

    Accepts **only** a full application id in ``params.package`` (no ``app`` alias), so benchmarks
    can target system databases such as ``com.android.providers.contacts`` without mapping
    ``contacts`` → ``com.google.android.contacts``.

    Optional ``force_stop`` (default ``true``): run ``am force-stop`` before ``pm clear``.

    Example::

        {
            "name": "android_pm_clear",
            "params": {
                "package": "com.android.providers.contacts",
                "force_stop": true
            }
        }
    """

    op_type = EnvironmentInitializerPluginType.ADB_PM_CLEAR

    def execute(self, meta: Dict[str, Any], params: Dict[str, Any]) -> bool:
        device = meta.get("device")
        if not device:
            self.logger.error("meta has no 'device'")
            return False

        pkg = (params.get("package") or "").strip()
        if not pkg:
            self.logger.error("params.package is required (full package id, e.g. com.android.providers.contacts)")
            return False

        force_stop = params.get("force_stop", True)
        if force_stop:
            self.logger.info("force-stop %s", pkg)
            stop_result = device.shell(f"am force-stop {pkg}")
            if stop_result.exit_code != 0:
                self.logger.warning(
                    "force-stop exit_code=%s stderr=%s",
                    stop_result.exit_code,
                    stop_result.error,
                )

        self.logger.info("pm clear %s", pkg)
        result = device.shell(f"pm clear {pkg}")
        self.logger.debug(
            "pm clear stdout=%r stderr=%r exit_code=%s",
            result.output,
            result.error,
            result.exit_code,
        )

        if result.exit_code != 0:
            self.logger.error(
                "pm clear failed package=%s exit_code=%s error=%s",
                pkg,
                result.exit_code,
                result.error,
            )
            return False

        out = result.output or ""
        if "Success" not in out:
            self.logger.warning("pm clear unexpected output: %r", out)

        self.logger.info("pm clear succeeded: %s", pkg)
        return True
