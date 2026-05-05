import logging
from typing import Dict, Any

from zhixing.core.benchmark.interface import BaseEnvironmentInitializerOperation
from zhixing.core.benchmark.protocol import EnvironmentInitializerPluginType
from zhixing.core.factory import PluginRegistry

logger = logging.getLogger(__name__)

@PluginRegistry.register(namespace="benchmark.environment.setting", name="android_conditional_adb_operator")
class ADBConditionalAdbOperator(BaseEnvironmentInitializerOperation):
    
    op_type = EnvironmentInitializerPluginType.ADB_CONDITIONAL_ADB_OPERATOR

    def execute(self, meta: Dict[str, Any], params: Dict[str, Any]) -> bool:
        try:
            logger.info("[ConditionalADB] 开始执行条件ADB检测操作")

            # 1. 解析参数
            check_cmd = params.get("check_cmd")
            expected_match = str(params.get("expected_match", ""))
            match_condition = params.get("match_condition", "contains")
            on_true_cmd = params.get("on_true_cmd")
            on_false_cmd = params.get("on_false_cmd")

            if not check_cmd:
                logger.warning("[ConditionalADB] 未提供 check_cmd")
                return 
            
            # 2. 获取 device 实例
            device = meta.get("device")
            if not device:
                logger.warning("[ConditionalADB] 未获取到设备，跳过执行")
                return False

            # 3. 执行检测命令
            logger.info(f"[ConditionalADB] 执行检测命令: {check_cmd}")

            check_result = device.device.shell(check_cmd)

            if check_result.exit_code != 0:
                logger.warning(f"[ConditionalADB] 检测命令返回非零状态码: {check_result.exit_code}。错误输出: {check_result.error}")
            
            output_text = check_result.output

            # 4. 判断逻辑
            is_match = False

            if match_condition == "contains" and expected_match in output_text:
                is_match = True
            elif match_condition == "not_contains" and expected_match not in output_text:
                is_match = True
            elif match_condition == "exact" and expected_match == output_text.strip():
                is_match = True
            
            # 5. 决定要执行的命令
            target_cmd = on_true_cmd if is_match else on_false_cmd
            match_status_str = "True" if is_match else "False"

            # 6. 执行目标命令
            if target_cmd:
                logger.info(f"[ConditionalADB] 正在执行目标命令: {target_cmd}")
                exec_result = device.device.shell(target_cmd)

                if exec_result.exit_code != 0:
                    logger.error(f"[ConditionalADB] 目标命令执行失败！状态码: {exec_result.exit_code} \n错误信息: {exec_result.error}")
                    return False
                else:
                    logger.info("[ConditionalADB] 目标命令执行成功！")
            else:
                logger.info("[ConditionalADB] 未配置对应条件的目标命令，直接跳过执行。")

            return True
        except Exception as e:
            # ⛔ 关键修改：捕获到任何异常，必须返回 False 中断流程！
            logger.error(f"[ConditionalADB] 执行出现致命异常：{str(e)}", exc_info=True)
            return False




            
            