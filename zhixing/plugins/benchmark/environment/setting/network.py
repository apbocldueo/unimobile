import time
from typing import Dict, Any

from zhixing.core.benchmark.interface import BaseEnvironmentInitializerOperation
from zhixing.core.benchmark.protocol import EnvironmentInitializerPluginType
from zhixing.core.factory import PluginRegistry


@PluginRegistry.register(namespace="benchmark.environment.setting", name="android_network_check_network")
class ADBCheckNetworkOperator(BaseEnvironmentInitializerOperation):
    """
    Ping an external host (default 8.8.8.8). If unreachable, try enabling Wi‑Fi and mobile data, then re-ping.

    By default the operator **fails** (returns False) when connectivity cannot be verified, which aborts
    benchmark setup via the pipeline. Set ``params.fail_soft`` to true to only log warnings and continue.

    Params:
        host (str): Ping target, default ``8.8.8.8``.
        recovery (bool): Try ``svc wifi enable`` / ``svc data enable`` before re-ping, default true.
        fail_soft (bool): If true, never fail the initializer; default false.
    """
    op_type = EnvironmentInitializerPluginType.ADB_CHECK_NETWORK

    def execute(self, meta: Dict[str, Any], params: Dict[str, Any]) -> bool:
        fail_soft = bool(params.get("fail_soft", False))
        host = (params.get("host") or "8.8.8.8").strip()
        recovery = params.get("recovery", True)

        try:
            device = meta.get("device")
            if not device:
                self.logger.error("network check: no device in meta")
                return fail_soft

            ping_cmd = f"ping -c 1 {host}"
            if self._ping_ok(device, ping_cmd):
                self.logger.info("network check: ping %s OK", host)
                return True

            self.logger.warning(
                "network check: ping %s failed; recovery=%s",
                host,
                recovery,
            )
            if recovery:
                device.shell("svc wifi enable")
                device.shell("svc data enable")
                time.sleep(3)
                if self._ping_ok(device, ping_cmd):
                    self.logger.info(
                        "network check: ping %s OK after enabling radios",
                        host,
                    )
                    return True

            msg = f"network check failed: cannot reach {host} (benchmark aborted)"
            if fail_soft:
                self.logger.warning("%s (fail_soft=true, continuing)", msg)
                return True
            self.logger.error(msg)
            return False

        except Exception as e:
            if fail_soft:
                self.logger.error(
                    "network check raised %s (fail_soft=true, continuing)",
                    e,
                    exc_info=True,
                )
                return True
            self.logger.error("network check failed: %s", e, exc_info=True)
            return False

    @staticmethod
    def _ping_ok(device, ping_cmd: str) -> bool:
        result = device.shell(ping_cmd)
        return result.exit_code == 0
