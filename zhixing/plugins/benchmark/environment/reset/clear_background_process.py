"""Force-stop all third-party packages (user-installed apps) on the device."""

from typing import Dict, Any

from zhixing.core.benchmark.interface import BaseEnvironmentInitializerOperation
from zhixing.core.benchmark.protocol import EnvironmentInitializerPluginType
from zhixing.core.factory import PluginRegistry

# Runs on device shell: third-party packages only (`pm list packages -3`).
_SHELL_CLEAR_THIRD_PARTY = (
    "for p in $(pm list packages -3 | cut -d: -f2); do am force-stop $p; done"
)


@PluginRegistry.register(namespace="benchmark.environment.reset", name="android_reset_clear_background_process")
class ADBClearBackgroundProcessOperator(BaseEnvironmentInitializerOperation):
    """
    Clears Android “background” by force-stopping every third-party package
    (equivalent to listing `pm list packages -3` and running `am force-stop` on each).

    System apps are not included in `-3`; launcher / system UI keep running until
    the next interaction, but user apps are stopped.

    Example ``environment_initializer`` entry::

        {
            "name": "android_reset_clear_background_process",
            "params": {}
        }

    Or rely on unique-name resolution without ``category`` when only one plugin matches.
    """

    op_type = EnvironmentInitializerPluginType.ADB_CLEAR_BACKGROUND_PROCESSES

    def execute(self, meta: Dict[str, Any], params: Dict[str, Any]) -> bool:
        try:
            device = meta.get("device")
            if not device:
                self.logger.error("meta has no 'device'")
                return False

            self.logger.info("force-stopping all third-party packages (pm list packages -3)")
            self.logger.debug("shell: %s", _SHELL_CLEAR_THIRD_PARTY)

            result = device.shell(_SHELL_CLEAR_THIRD_PARTY)
            if result.exit_code != 0:
                self.logger.error(
                    "clear background processes failed exit_code=%s stderr=%s stdout=%s",
                    result.exit_code,
                    result.error,
                    (result.output or "")[:2000],
                )
                return False

            out = (result.output or "").strip()
            if out:
                self.logger.debug("shell stdout (truncated): %s", out[:2000])
            self.logger.info("clear background processes finished OK")
            return True

        except Exception as e:
            self.logger.error("execute failed: %s", e, exc_info=True)
            return False
