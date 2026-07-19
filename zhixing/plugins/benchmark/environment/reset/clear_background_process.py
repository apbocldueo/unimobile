"""Force-stop selected apps or all third-party packages on the device."""

from typing import Dict, Any, List

from zhixing.core.benchmark.interface import BaseEnvironmentInitializerOperation
from zhixing.core.benchmark.protocol import EnvironmentInitializerPluginType
from zhixing.core.factory import PluginRegistry

# Legacy: all user-installed packages (`pm list packages -3`).
_SHELL_CLEAR_ALL_THIRD_PARTY = (
    "for p in $(pm list packages -3 | cut -d: -f2); do am force-stop $p; done"
)


@PluginRegistry.register(namespace="benchmark.environment.reset", name="android_reset_clear_background_process")
class ADBClearBackgroundProcessOperator(BaseEnvironmentInitializerOperation):
    """
    Force-stop apps to clear background state (process only — does not clear app data).

    ------------------------------------------------------------
    Params (pick one mode)
    ------------------------------------------------------------

    **Selective (recommended)** — only stop listed apps:

    .. code-block:: json

        {
            "name": "android_reset_clear_background_process",
            "params": {
                "apps": ["maps", "x"]
            }
        }

    Or full package ids::

        "packages": ["com.google.android.apps.maps", "com.twitter.android"]

    Single app shorthand::

        "app": "maps"

    **All third-party (legacy)** — stops every user-installed app:

    .. code-block:: json

        { "params": { "all_third_party": true } }

    Empty ``params`` {{}} still runs all-third-party mode for backward compatibility.
    Prefer explicit ``apps`` so Gmail/X/Maps on the same device are not all killed.
    """

    op_type = EnvironmentInitializerPluginType.ADB_CLEAR_BACKGROUND_PROCESSES

    def _resolve_packages(
        self, device: Any, params: Dict[str, Any]
    ) -> tuple[List[str], str | None]:
        """Return (package_list, error_message)."""
        names = getattr(device, "app_package_names", None) or {}
        resolved: List[str] = []
        seen: set[str] = set()

        single = params.get("app")
        if single:
            apps_param: List[Any] = [single]
        else:
            apps_param = params.get("apps") or []

        if apps_param and not isinstance(apps_param, list):
            return [], "params.apps must be a list of logical app keys"

        for app_name in apps_param:
            key = str(app_name).lower()
            if key not in names:
                return [], (
                    f"unknown app key {app_name!r}; known: {sorted(names.keys())}"
                )
            pkg = names[key]
            if pkg not in seen:
                seen.add(pkg)
                resolved.append(pkg)

        packages_param = params.get("packages") or []
        if packages_param and not isinstance(packages_param, list):
            return [], "params.packages must be a list of package ids"

        for pkg in packages_param:
            pkg = str(pkg).strip()
            if not pkg:
                continue
            if pkg not in seen:
                seen.add(pkg)
                resolved.append(pkg)

        if resolved:
            return resolved, None

        if params.get("all_third_party") or not params:
            return [], None  # sentinel: use shell loop

        return [], (
            "specify params.apps, params.app, params.packages, or all_third_party: true"
        )

    def execute(self, meta: Dict[str, Any], params: Dict[str, Any]) -> bool:
        try:
            device = meta.get("device")
            if not device:
                self.logger.error("meta has no 'device'")
                return False

            packages, err = self._resolve_packages(device, params)
            if err:
                self.logger.error(err)
                return False

            if not packages:
                self.logger.info(
                    "force-stopping all third-party packages (pm list packages -3)"
                )
                self.logger.debug("shell: %s", _SHELL_CLEAR_ALL_THIRD_PARTY)
                result = device.shell(_SHELL_CLEAR_ALL_THIRD_PARTY)
                if result.exit_code != 0:
                    self.logger.error(
                        "clear background failed exit_code=%s stderr=%s",
                        result.exit_code,
                        result.error,
                    )
                    return False
                self.logger.info("clear background (all third-party) finished OK")
                return True

            self.logger.info("force-stop packages: %s", packages)
            for pkg in packages:
                stop_result = device.shell(f"am force-stop {pkg}")
                if stop_result.exit_code != 0:
                    self.logger.error(
                        "force-stop %s failed exit_code=%s stderr=%s",
                        pkg,
                        stop_result.exit_code,
                        stop_result.error,
                    )
                    return False
                self.logger.debug("force-stop OK: %s", pkg)

            self.logger.info(
                "clear background finished OK (%d package(s))", len(packages)
            )
            return True

        except Exception as e:
            self.logger.error("execute failed: %s", e, exc_info=True)
            return False
