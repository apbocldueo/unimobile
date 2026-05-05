from typing import Dict, Any

from zhixing.core.benchmark.interface import BaseEnvironmentInitializerOperation
from zhixing.core.benchmark.protocol import EnvironmentInitializerPluginType
from zhixing.core.factory import PluginRegistry


@PluginRegistry.register(namespace="benchmark.environment.setting", name="android_conditional_adb_operator")
class ADBConditionalAdbOperator(BaseEnvironmentInitializerOperation):

    op_type = EnvironmentInitializerPluginType.ADB_CONDITIONAL_ADB_OPERATOR

    def execute(self, meta: Dict[str, Any], params: Dict[str, Any]) -> bool:
        try:
            check_cmd = params.get("check_cmd")
            expected_match = str(params.get("expected_match", ""))
            match_condition = params.get("match_condition", "contains")
            on_true_cmd = params.get("on_true_cmd")
            on_false_cmd = params.get("on_false_cmd")

            if not check_cmd:
                self.logger.error("execute: missing required param 'check_cmd'")
                return False

            device = meta.get("device")
            if not device:
                self.logger.error("execute: meta has no 'device'")
                return False

            self.logger.debug("check_cmd=%r match_condition=%r expected_match=%r", check_cmd, match_condition, expected_match)
            check_result = device.device.shell(check_cmd)

            if check_result.exit_code != 0:
                self.logger.warning(
                    "check command non-zero exit_code=%s stderr=%s (output may still be usable)",
                    check_result.exit_code,
                    check_result.error,
                )

            output_text = check_result.output or ""
            is_match = False
            if match_condition == "contains" and expected_match in output_text:
                is_match = True
            elif match_condition == "not_contains" and expected_match not in output_text:
                is_match = True
            elif match_condition == "exact" and expected_match == output_text.strip():
                is_match = True

            target_cmd = on_true_cmd if is_match else on_false_cmd
            self.logger.info(
                "condition result=%s branch=%s",
                is_match,
                "on_true" if is_match else "on_false",
            )

            if target_cmd:
                self.logger.debug("running branch command: %s", target_cmd)
                exec_result = device.device.shell(target_cmd)
                if exec_result.exit_code != 0:
                    self.logger.error(
                        "branch command failed exit_code=%s stderr=%s cmd=%r",
                        exec_result.exit_code,
                        exec_result.error,
                        target_cmd,
                    )
                    return False
                self.logger.info("branch command finished OK")
            else:
                self.logger.info("no command configured for this branch; nothing to run")

            return True
        except Exception as e:
            self.logger.error("execute failed: %s", e, exc_info=True)
            return False
