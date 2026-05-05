import time
from typing import Dict, Any

from zhixing.core.benchmark.interface import BaseEnvironmentInitializerOperation
from zhixing.core.benchmark.protocol import EnvironmentInitializerPluginType
from zhixing.core.factory import PluginRegistry


@PluginRegistry.register(namespace="benchmark.environment.setting", name="android_network_check_network")
class ADBCheckNetworkOperator(BaseEnvironmentInitializerOperation):
    """
    Ping 8.8.8.8; if unreachable, try enabling Wi‑Fi and mobile data.
    Failures are logged as warnings; the operator still returns True so benchmarks can proceed.
    """
    op_type = EnvironmentInitializerPluginType.ADB_CHECK_NETWORK

    def execute(self, meta: Dict[str, Any], params: Dict[str, Any]) -> bool:
        try:
            device = meta.get("device")
            if not device:
                self.logger.warning("no device in meta; skip network check (treat as OK)")
                return True

            ping_cmd = "ping -c 1 8.8.8.8"
            ping_result = device.shell(ping_cmd)

            if ping_result.exit_code == 0:
                self.logger.info("network check: ping OK")
                return True

            self.logger.warning(
                "network check: ping failed exit_code=%s; attempting svc wifi/data enable",
                ping_result.exit_code,
            )
            device.shell("svc wifi enable")
            device.shell("svc data enable")
            time.sleep(3)

            recheck = device.shell(ping_cmd)
            if recheck.exit_code == 0:
                self.logger.info("network check: recovery succeeded after enabling radios")
            else:
                self.logger.warning(
                    "network check: still no ping after recovery; continue anyway exit_code=%s",
                    recheck.exit_code,
                )
            return True
        except Exception as e:
            self.logger.error("network check raised %s (non-fatal, returning True)", e, exc_info=True)
            return True
