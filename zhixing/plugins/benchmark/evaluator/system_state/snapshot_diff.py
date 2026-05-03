import re
from typing import Dict, Any

from zhixing.core.benchmark.protocol import EvalResult
from zhixing.core.benchmark.base_system import BaseSystemAction
from zhixing.core.factory import PluginRegistry

@PluginRegistry.register(namespace="evaluator.system_state", name="snapshot_diff")
class SnapshotDiffAction(BaseSystemAction):
    """System state snapshot difference validator.
    
    Captures a baseline output of a shell command before the task starts, 
    and compares it with the output after the task. It validates if the 
    newly added lines match a specific regular expression pattern.
    """

    def pre_evaluate(self, context: Dict[str, Any]) -> None:
        """Captures the baseline snapshot before the agent executes its task.

        Args:
            context (Dict[str, Any]): The execution context containing dynamic variables.
        """
        # 统一使用 get_param 提取
        command = self.get_param("command", context, expected_type=str)
        
        self.logger.info(f"Capturing baseline snapshot using command: {command}")
        
        # 将 baseline 存入实例属性
        self._baseline_snapshot = self._run_device_shell(command)
        
        # 日志统一翻译，考虑到内容可能很长，建议用 debug 级别打印具体快照
        self.logger.debug(f"Baseline snapshot result: {self._baseline_snapshot}")
    
    def evaluate(self, context: Dict[str, Any]) -> EvalResult:
        """Evaluates the difference between the baseline and current snapshots.

        Args:
            context (Dict[str, Any]): The execution context containing dynamic variables.

        Returns:
            EvalResult: The evaluation result, including pass/fail status and the reason.
        """
        command = self.get_param("command", context, expected_type=str)
        pattern = self.get_param("pattern", context, expected_type=str)

        # 架构师防坑：使用 getattr 防止预处理钩子因意外未运行而导致的崩溃
        baseline_snapshot = getattr(self, "_baseline_snapshot", None)
        if baseline_snapshot is None:
            return EvalResult(is_pass=False, reason="Fatal error: Baseline snapshot missing! Ensure 'pre_evaluate' was successfully called.")

        # 抓取执行后的最新快照
        current_snapshot = self._run_device_shell(command)

        # 集合差异计算
        baseline_lines = set(baseline_snapshot.splitlines())
        current_lines = set(current_snapshot.splitlines())

        self.logger.debug(f"Baseline content lines: {len(baseline_lines)}")
        self.logger.debug(f"Current content lines: {len(current_lines)}")

        # 找出新增的行
        new_lines = current_lines - baseline_lines
        self.logger.info(f"Detected new content lines: {new_lines}")

        if not new_lines:
            return EvalResult(is_pass=False, reason="Snapshot comparison finished: No new states/lines detected.")
        
        new_files_str = "\n".join(new_lines)

        # 只要新增的内容里出现 pattern 中指定的字符串，就算匹配成功
        if re.search(pattern, new_files_str):
            return EvalResult(is_pass=True, reason=f"Successfully discovered new states matching the expected pattern.")
        
        return EvalResult(is_pass=False, reason=f"State changed, but did not match expectations. Actual new content:\n{new_files_str}")