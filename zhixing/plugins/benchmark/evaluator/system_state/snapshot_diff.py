import re
from typing import Dict, Any, List

from zhixing.core.benchmark.protocol import EvalResult
from zhixing.core.benchmark.base_system import BaseSystemAction
from zhixing.core.factory import PluginRegistry


@PluginRegistry.register(namespace="evaluator.system_state", name="snapshot_diff")
class SnapshotDiffAction(BaseSystemAction):
    """System state snapshot difference validator.

    Captures a baseline output of a shell command before the task starts,
    and compares it with the output after the task. It validates if the
    newly added lines match a specific regular expression pattern.

    Optional ``new_lines`` (int): when omitted or 0, only checks that there is
    at least one new line and that ``pattern`` matches the concatenated new
    text (legacy behavior). When set to N > 0, requires **exactly** N new lines
    that each match ``pattern`` on their own (excludes e.g. ``ls``'s
    ``total …`` line if ``pattern`` is ``\\.jpg``).
    """

    def pre_evaluate(self, context: Dict[str, Any]) -> None:
        """Captures the baseline snapshot before the agent executes its task.

        Args:
            context (Dict[str, Any]): The execution context containing dynamic variables.
        """
        command = self.get_param("command", context, expected_type=str)

        self.logger.info(f"Capturing baseline snapshot using command: {command}")

        self._baseline_snapshot = self._run_device_shell(command)

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
        expected_new = self.get_param("new_lines", context, default=0, expected_type=int)

        baseline_snapshot = getattr(self, "_baseline_snapshot", None)
        if baseline_snapshot is None:
            return EvalResult(
                is_pass=False,
                reason="Fatal error: Baseline snapshot missing! Ensure 'pre_evaluate' was successfully called.",
            )

        current_snapshot = self._run_device_shell(command)

        baseline_lines = set(baseline_snapshot.splitlines())
        current_lines = set(current_snapshot.splitlines())

        self.logger.debug(f"Baseline content lines: {len(baseline_lines)}")
        self.logger.debug(f"Current content lines: {len(current_lines)}")

        new_lines = current_lines - baseline_lines
        self.logger.info(f"Detected new content lines: {new_lines}")

        if not new_lines:
            return EvalResult(
                is_pass=False,
                reason="Snapshot comparison finished: No new states/lines detected.",
            )

        new_files_str = "\n".join(new_lines)
        matching: List[str] = [ln for ln in new_lines if re.search(pattern, ln)]
        n_match = len(matching)

        if expected_new > 0:
            self.logger.debug(
                "snapshot_diff new_lines=%s pattern-matching count=%s",
                expected_new,
                n_match,
            )
            if n_match != expected_new:
                return EvalResult(
                    is_pass=False,
                    reason=(
                        f"Expected exactly {expected_new} new line(s) matching `pattern`, "
                        f"got {n_match}. Matching lines: {matching!r}. "
                        f"All new lines:\n{new_files_str}"
                    ),
                )
            return EvalResult(
                is_pass=True,
                reason=(
                    f"Successfully matched expectation: {n_match} new line(s) match `pattern`."
                ),
            )

        if re.search(pattern, new_files_str):
            return EvalResult(
                is_pass=True,
                reason="Successfully discovered new states matching the expected pattern.",
            )

        return EvalResult(
            is_pass=False,
            reason=f"State changed, but did not match expectations. Actual new content:\n{new_files_str}",
        )
