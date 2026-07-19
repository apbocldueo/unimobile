import time
import tempfile
import os
from typing import Dict, Any, List, Optional

from zhixing.core.benchmark.interface import BaseEnvironmentInitializerOperation
from zhixing.core.benchmark.protocol import EnvironmentInitializerPluginType
from zhixing.core.factory import PluginRegistry

# Defaults when not specified in plugin or step config (seconds).
DEFAULT_WAIT_AFTER = 2.0
DEFAULT_WAIT_BEFORE = 0.0
DEFAULT_WAIT_BEFORE_BY_ACTION: Dict[str, float] = {
    "judge": 5.0,
    "enter": 3.0,
}

# run_if_judge: always | matched | not_matched
RUN_IF_JUDGE_ALWAYS = "always"
RUN_IF_JUDGE_MATCHED = "matched"
RUN_IF_JUDGE_NOT_MATCHED = "not_matched"
_VALID_RUN_IF_JUDGE = {
    RUN_IF_JUDGE_ALWAYS,
    RUN_IF_JUDGE_MATCHED,
    RUN_IF_JUDGE_NOT_MATCHED,
}

# on_match (judge step only): break | continue
ON_MATCH_BREAK = "break"
ON_MATCH_CONTINUE = "continue"

_FIELD_ALIASES: Dict[str, str] = {
    "resource_id": "resource-id",
    "content_desc": "content-desc",
}


@PluginRegistry.register(namespace="benchmark.environment.ui", name="ui_judge_ui")
class UIJudgeUIGenerator(BaseEnvironmentInitializerOperation):
    """Scripted UI environment setup with optional judge-based branching on later steps."""

    op_type = EnvironmentInitializerPluginType.UI_JUDEG_UI

    def execute(self, meta: Dict[str, Any], params: Dict[str, Any]) -> bool:
        """Run scripted UI steps for environment initialization.

        Timing (seconds, all optional):
          - Plugin ``wait_after`` / ``wait_before``: defaults for every step.
          - Per-step ``wait_after`` / ``wait_before``: override plugin defaults.

        Judge branching:
          - Judge step ``on_match``:
              - ``continue`` (default): keep running later steps; use ``run_if_judge`` on each.
              - ``break``: legacy — if judge matches, stop the entire script immediately.
          - Steps **after** a judge step may set ``run_if_judge``:
              - ``always`` (default): always run.
              - ``matched``: run only when the last judge matched.
              - ``not_matched``: run only when the last judge did not match.

        Example (X profile pre-setup: unfollow if already Following; exit if still Follow)::

            {"action": "judge", "on_match": "break", "wait_before": 5,
             "params": [{"fields": ["resource_id", "text"],
                         "content": ["com.twitter.android:id/follow_button", "follow"]}]},
            {"action": "judge", "on_match": "continue",
             "params": [{"fields": ["resource_id", "text"],
                         "content": ["com.twitter.android:id/follow_button", "following"]}]},
            {"action": "tap", "run_if_judge": "matched", "params": {"x": 982, "y": 619}},
            {"action": "home", "run_if_judge": "always", "params": {}}

        Judge rule optional ``match_modes`` per field: ``equals`` (default) or ``contains``.
        """
        device = meta.get("device")
        if not device:
            self.logger.error("meta has no 'device'")
            return False

        steps = params.get("steps")
        if not steps or not isinstance(steps, list):
            self.logger.error("params.steps must be a non-empty list")
            return False

        plugin_wait_after = float(params.get("wait_after", DEFAULT_WAIT_AFTER))
        plugin_wait_before = float(params.get("wait_before", DEFAULT_WAIT_BEFORE))

        judge_matched: Optional[bool] = None

        for step in steps:
            action = (step.get("action") or "").lower()
            step_params = step.get("params")

            if action != "judge" and not self._should_run_step(step, judge_matched):
                run_if = (step.get("run_if_judge") or RUN_IF_JUDGE_ALWAYS).lower()
                self.logger.info(
                    "ui_judge_ui skip step action=%s run_if_judge=%s judge_matched=%s",
                    action,
                    run_if,
                    judge_matched,
                )
                continue

            wait_before = self._resolve_wait_before(step, action, plugin_wait_before)
            wait_after = self._resolve_wait_after(step, plugin_wait_after)

            if wait_before > 0:
                self.logger.debug("ui_judge_ui wait_before=%.2fs action=%s", wait_before, action)
                time.sleep(wait_before)

            if action == "judge":
                if not isinstance(step_params, list):
                    self.logger.error("judge step params must be a list")
                    return False
                params_logic = (step.get("params_logic") or "all").lower()
                judge_matched = self._evaluate_judge(device, step_params, params_logic)
                on_match = (step.get("on_match") or ON_MATCH_CONTINUE).lower()
                self.logger.info(
                    "ui_judge_ui judge result=%s on_match=%s",
                    judge_matched,
                    on_match,
                )
                if on_match == ON_MATCH_BREAK and judge_matched:
                    self.logger.info("ui_judge_ui on_match=break — stopping remaining steps")
                    break
            elif action == "start_app":
                page = (step_params or {}).get("page", "")
                device.start_app(f"{(step_params or {}).get('app_name')}", page)
            elif action == "tap":
                device.tap(f"{(step_params or {}).get('x')}", f"{(step_params or {}).get('y')}")
            elif action == "type":
                device.input_text(f"{(step_params or {}).get('text')}")
            elif action == "swipe":
                device.swipe(
                    f"{(step_params or {}).get('direction')}",
                    f"{(step_params or {}).get('scale')}",
                )
            elif action == "enter":
                device.enter()
            elif action == "back":
                device.go_back()
            elif action == "home":
                device.go_home()
            elif action == "clear":
                device.clear_text(f"{(step_params or {}).get('num', 15)}")
            else:
                self.logger.error("unknown step action=%r", step.get("action"))
                return False

            if wait_after > 0:
                self.logger.debug("ui_judge_ui wait_after=%.2fs action=%s", wait_after, action)
                time.sleep(wait_after)

        return True

    def _evaluate_judge(
        self,
        device,
        judge_params: List[dict],
        params_logic: str = "all",
    ) -> bool:
        ui_elements = device.extract_android_ui_elements()
        screenshot = os.path.join(tempfile.gettempdir(), "ui_judge_ui_judge.png")
        device.screenshot(screenshot)

        rule_results: List[bool] = []
        for param in judge_params:
            if all(k in param for k in ["content", "fields"]):
                rule_results.append(self._judge_content_in_elements_xml(param, ui_elements))
            elif all(k in param for k in ["model", "prompt"]):
                prompt = param.get("prompt")
                rule_results.append(self._judge_content_in_elements_llm(device, prompt))
            else:
                rule_results.append(False)

        if not rule_results:
            matched = False
        elif params_logic == "any":
            matched = any(rule_results)
        else:
            matched = all(rule_results)

        self.logger.debug(
            "judge step aggregate result=%s params_logic=%s rules=%s",
            matched,
            params_logic,
            rule_results,
        )
        return matched

    def _should_run_step(self, step: Dict[str, Any], judge_matched: Optional[bool]) -> bool:
        run_if = (step.get("run_if_judge") or RUN_IF_JUDGE_ALWAYS).lower()
        if run_if not in _VALID_RUN_IF_JUDGE:
            self.logger.warning(
                "unknown run_if_judge=%r (use always|matched|not_matched), treating as always",
                run_if,
            )
            return True
        if run_if == RUN_IF_JUDGE_ALWAYS:
            return True
        if judge_matched is None:
            return True
        if run_if == RUN_IF_JUDGE_MATCHED:
            return judge_matched is True
        if run_if == RUN_IF_JUDGE_NOT_MATCHED:
            return judge_matched is False
        return True

    @staticmethod
    def _resolve_wait_after(step: Dict[str, Any], plugin_default: float) -> float:
        if "wait_after" in step:
            return max(0.0, float(step["wait_after"]))
        return max(0.0, plugin_default)

    @classmethod
    def _resolve_wait_before(
        cls,
        step: Dict[str, Any],
        action: str,
        plugin_default: float,
    ) -> float:
        if "wait_before" in step:
            return max(0.0, float(step["wait_before"]))
        action_default = DEFAULT_WAIT_BEFORE_BY_ACTION.get(action)
        if action_default is not None:
            return max(0.0, action_default)
        return max(0.0, plugin_default)

    def _judge_content_in_elements_xml(self, variable: dict, elements: List[dict]) -> bool:
        for element in elements:
            if self._check_match(variable, element):
                return True
        return False

    def _judge_content_in_elements_llm(self, device, prompt: str) -> bool:
        pass

    @classmethod
    def _element_field(cls, element: dict, field: str) -> str:
        """Resolve field name with Android XML alias support (resource_id -> resource-id)."""
        if field == "text":
            # X often puts visible label in content-desc while text is empty on the same node.
            return str(element.get("text") or element.get("content_desc") or "")
        if field == "content_desc":
            return str(element.get("content_desc") or "")

        if field in element:
            val = str(element.get(field) or "")
            if val:
                return val
        alias = _FIELD_ALIASES.get(field)
        if alias and alias in element:
            val = str(element.get(alias) or "")
            if val:
                return val
        return ""

    @classmethod
    def _check_match(cls, d: dict, element: dict) -> bool:
        """All fields[i] must match content[i] (case-insensitive, stripped)."""
        fields = d["fields"]
        contents = d["content"]
        modes = d.get("match_modes") or ["equals"] * len(fields)
        if len(modes) < len(fields):
            modes = list(modes) + ["equals"] * (len(fields) - len(modes))

        for field, expected, mode in zip(fields, contents, modes):
            actual = cls._element_field(element, field).lower().strip()
            expected_norm = expected.lower().strip()
            mode_norm = (mode or "equals").lower()
            if mode_norm == "contains":
                if expected_norm not in actual:
                    return False
            elif actual != expected_norm:
                return False
        return True
