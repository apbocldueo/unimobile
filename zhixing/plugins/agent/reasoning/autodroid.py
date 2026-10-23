"""AutoDroid online policy using only the existing Reasoning -> Action contract."""

from __future__ import annotations

import json
from dataclasses import replace

from zhixing.components import Action, ActionType, BaseReasoning, ReasoningInput, RuntimeContext
from zhixing.core.agent.protocol import FragmentType
from zhixing.core.factory import PluginRegistry
from zhixing.plugins.agent.autodroid_types import (
    Candidate, Guide, PolicyState, ScanState, ScrollRegion, Target, UIState,
    normalize_description, stable_id,
)
from zhixing.plugins.agent.parsers.autodroid_action_parser import AutoDroidActionParser
from zhixing.plugins.agent.parsers.json_action_parser import ActionParseError
from zhixing.plugins.agent.perception.autodroid import candidate_html
from zhixing.resources import read_prompt


def _failure(code: str) -> Action:
    """Create a bounded policy failure without exposing backend exception text.

    Args:
        code: Stable algorithm failure category.
    Returns:
        Action: Explicit FAIL, never a fabricated successful completion.
    """
    return Action(ActionType.FAIL, thought=code, metadata={"autodroid.error": code})


def _matches(target: Target, candidate: Candidate, state_id: str) -> bool:
    """Compare semantic identities, optionally requiring a particular UI state.

    Args:
        target: Memory or selected navigation target.
        candidate: Candidate from the current observation.
        state_id: Current UI signature.
    Returns:
        bool: Whether the target describes this candidate.
    """
    if target.state_id and target.state_id != state_id:
        return False
    if target.key:
        return target.key == candidate.key
    return normalize_description(target.description) == normalize_description(candidate.description)


@PluginRegistry.register(namespace="agent.reasoning", name="autodroid_reasoning")
class AutoDroidReasoning(BaseReasoning):
    """Advance scan/shortcut/model phases without ever receiving a device handle."""

    def __init__(self, llm_client, scan_enabled: bool = True, max_scrolls: int = 7,
                 shortcut_threshold: float = 0.95, shortcut_enabled: bool = True,
                 parse_max_retries: int = 0, prompt_file: str = "reasoning_autodroid.md") -> None:
        """Store inference and bounded policy configuration without runtime effects.

        Args:
            llm_client: Existing generate(prompt, images) model dependency.
            scan_enabled: Collect off-screen elements before querying the model.
            max_scrolls: Per-direction/per-region scroll limit.
            shortcut_threshold: Minimum cosine similarity for memory execution.
            shortcut_enabled: Enable the declared shortcut policy.
            parse_max_retries: Additional model attempts after invalid formatting.
            prompt_file: Package-owned or explicit caller prompt resource.
        Raises:
            ValueError: A bound or threshold is invalid.
        Returns:
            None.
        """
        if (isinstance(max_scrolls, bool) or not isinstance(max_scrolls, int)
                or not 1 <= max_scrolls <= 100 or not -1 <= shortcut_threshold <= 1):
            raise ValueError("invalid AutoDroid scroll limit or shortcut threshold")
        if (isinstance(parse_max_retries, bool) or not isinstance(parse_max_retries, int)
                or not 0 <= parse_max_retries <= 3):
            raise ValueError("parse_max_retries must be in 0..3")
        self.llm = llm_client
        self.scan_enabled, self.max_scrolls = scan_enabled, max_scrolls
        self.shortcut_threshold, self.shortcut_enabled = shortcut_threshold, shortcut_enabled
        self.parse_max_retries, self.prompt_file = parse_max_retries, prompt_file
        self.parser = AutoDroidActionParser()

    def _scroll(self, target: Target, ui: UIState, phase: str) -> Action:
        """Translate a logical content scroll to an explicit current-frame swipe.

        Args:
            target: Scroll container key and logical direction.
            ui: Current observed region bounds.
            phase: Auditable policy phase.
        Returns:
            Action: One precise SWIPE or a missing/ambiguous-region FAIL.
        """
        regions = [region for region in ui.regions if region.key == target.key]
        if len(regions) != 1:
            return _failure("scroll_region_missing_or_ambiguous")
        x1, y1, x2, y2 = regions[0].bounds
        if x2 - x1 < 8 or y2 - y1 < 8:
            return _failure("scroll_region_too_small")
        x, y = (x1 + x2) // 2, (y1 + y2) // 2
        lo_x, hi_x = x1 + (x2 - x1) // 4, x2 - (x2 - x1) // 4
        lo_y, hi_y = y1 + (y2 - y1) // 4, y2 - (y2 - y1) // 4
        # Content DOWN requires a finger swipe UP; never rely on backend naming.
        points = {"down": (x, hi_y, x, lo_y), "up": (x, lo_y, x, hi_y),
                  "right": (hi_x, y, lo_x, y), "left": (lo_x, y, hi_x, y)}
        start_x, start_y, end_x, end_y = points[target.direction]
        return Action(ActionType.SWIPE,
                      {"start_x": start_x, "start_y": start_y, "end_x": end_x, "end_y": end_y,
                       "duration_ms": 500},
                      metadata={"autodroid.phase": phase, "autodroid.direction": target.direction})

    def _target_action(self, target: Target, ui: UIState, phase: str) -> Action:
        """Resolve exactly one canonical action on the current observation.

        Args:
            target: Semantic operation, never coordinates captured on another page.
            ui: Current candidates and regions.
            phase: Auditable origin of the action.
        Returns:
            Action: One resolved operation or a deterministic FAIL.
        """
        if target.operation == "scroll":
            return self._scroll(target, ui, phase)
        if target.operation == "back" or target.key == "__back__":
            return Action(ActionType.KEY, {"code": "back"}, metadata={"autodroid.phase": phase})
        matches = [candidate for candidate in ui.candidates if _matches(target, candidate, ui.state_id)]
        if len(matches) != 1 or not matches[0].interactive:
            return _failure("target_missing_or_ambiguous")
        candidate = matches[0]
        if candidate.key == "__back__":
            return Action(ActionType.KEY, {"code": "back"}, metadata={"autodroid.phase": phase})
        x1, y1, x2, y2 = candidate.bounds
        params = {"x": (x1 + x2) // 2, "y": (y1 + y2) // 2}
        if target.operation == "input":
            if candidate.tag != "input":
                return _failure("input_requires_editable_element")
            params["text"] = target.text
        return Action(ActionType.TEXT if target.operation == "input" else ActionType.TAP, params,
                      metadata={"autodroid.phase": phase, "autodroid.target": candidate.description})

    def _next_pending(self, state: PolicyState, ui: UIState) -> Action | None:
        """Take one path step or abandon an inapplicable memory shortcut.

        Args:
            state: Task-owned navigation cursor.
            ui: Current observation.
        Returns:
            Action | None: Next action, failure, or no pending path.
        """
        if not state.pending:
            return None
        action = self._target_action(state.pending[0], ui, state.pending_kind)
        if action.type is ActionType.FAIL and state.pending_kind == "shortcut":
            state.pending.clear()
            state.pending_kind = ""
            return None
        state.pending.pop(0)
        if not state.pending:
            state.pending_kind = ""
            state.scanned = None
        return action

    @staticmethod
    def _signature(ui: UIState, region: ScrollRegion) -> str:
        """Compare scroll contents without coordinates or unrelated UI regions.

        Args:
            ui: Current UI.
            region: Container being explored.
        Returns:
            str: Stable signature of its observed content.
        """
        return stable_id([(item.key, item.text, item.checked) for item in ui.candidates if item.region_key == region.key])

    @staticmethod
    def _collect(scan: ScanState, ui: UIState, region: ScrollRegion) -> None:
        """Collect unique choices and their replayable logical scroll prefixes.

        Args:
            scan: Mutable task-local scan data.
            ui: Current frame.
            region: Active region; unrelated scroll containers are collected later.
        Returns:
            None.
        """
        known = {item.key for item in scan.candidates}
        for candidate in ui.candidates:
            if candidate.key in known or candidate.region_key not in {"", region.key}:
                continue
            prefix = tuple(Target(key=region.key, operation="scroll", direction="down") for _ in range(scan.offset))
            scan.candidates.append(candidate.model_copy(update={"prefix": prefix if candidate.region_key else ()}))
            known.add(candidate.key)

    def _scan(self, state: PolicyState, ui: UIState) -> Action | None:
        """Advance one bounded scan action, restoring each container before selection.

        Args:
            state: Run-owned policy data.
            ui: New observation after the last confirmed device action.
        Returns:
            Action | None: One scroll, explicit failure, or completed merged choices.
        """
        scan = state.scan
        if scan is None:
            scan = ScanState(regions=ui.regions)
            state.scan = scan
        # Pure transitions may complete phases; device commands never occur here.
        for _ in range(len(scan.regions) * 4 + 4):
            if scan.index >= len(scan.regions):
                state.scanned = tuple(item.model_copy(update={"choice_id": index}) for index, item in enumerate(scan.candidates))
                state.scan = None
                return None
            region = scan.regions[scan.index]
            if not any(item.key == region.key for item in ui.regions):
                return _failure("scan_region_disappeared")
            signature = self._signature(ui, region)
            if scan.phase == "top":
                if scan.waiting:
                    scan.attempts += 1
                    if signature == scan.previous_signature:
                        scan.phase, scan.waiting = "down", ""
                        scan.top_signature, scan.offset, scan.attempts = signature, 0, 0
                        self._collect(scan, ui, region)
                        continue
                    if scan.attempts >= self.max_scrolls:
                        return _failure("scan_top_budget_exhausted")
                scan.previous_signature, scan.waiting = signature, "top"
                return self._scroll(Target(key=region.key, operation="scroll", direction="up"), ui, "scan")
            if scan.phase == "down":
                if scan.waiting:
                    scan.waiting = ""
                    if signature == scan.previous_signature:
                        scan.phase = "restore"
                        continue
                    scan.offset += 1
                    previous_count = len(scan.candidates)
                    self._collect(scan, ui, region)
                    if len(scan.candidates) == previous_count or scan.offset >= self.max_scrolls:
                        scan.phase = "restore"
                        continue
                scan.previous_signature, scan.waiting = signature, "down"
                return self._scroll(Target(key=region.key, operation="scroll", direction="down"), ui, "scan")
            if scan.waiting:
                scan.offset -= 1
                scan.waiting = ""
            if scan.offset > 0:
                scan.waiting = "restore"
                return self._scroll(Target(key=region.key, operation="scroll", direction="up"), ui, "scan")
            if signature != scan.top_signature:
                return _failure("scan_restore_mismatch")
            scan.index += 1
            scan.phase, scan.previous_signature, scan.attempts = "top", None, 0
        return _failure("scan_transition_budget_exhausted")

    @staticmethod
    def _prompt_ui(candidates: tuple[Candidate, ...], guide: Guide, ui: UIState) -> tuple[str, tuple[Candidate, ...]]:
        """Apply declared UTG equivalences and only matching functionality hints.

        Args:
            candidates: Collected current and off-screen UI choices.
            guide: Retrieved paths and declared equivalence groups.
            ui: Current restored UI identity.
        Returns:
            tuple[str, tuple[Candidate, ...]]: Prompt statements and exact choice map.
        """
        choices = list(candidates)
        for group in guide.equivalent_groups.get(ui.state_id, ()):
            selected = [item for item in choices if item.key in group]
            if len(selected) < 2 or any((item.prefix, item.tag, item.interactive) !=
                                        (selected[0].prefix, selected[0].tag, selected[0].interactive)
                                        for item in selected):
                continue
            first = selected[0].model_copy(update={"text": "<br>".join(item.text for item in selected)})
            choices = [first if item.key == first.key else item for item in choices if item not in selected[1:]]
        choices = [item.model_copy(update={"choice_id": index}) for index, item in enumerate(choices)]
        statements: list[str] = []
        for candidate in choices:
            hints = list(dict.fromkeys(hit.entry.function or hit.entry.task for hit in guide.hits
                                      if any(_matches(target, candidate, ui.state_id) for target in hit.entry.path)))
            statements.append(candidate_html(candidate, "; ".join(hints)[:4000]))
        return "\n".join(statements), tuple(choices)

    def invoke(self, input: ReasoningInput, runtime: RuntimeContext) -> Action:
        """Return one physical/terminal action using the current policy phase.

        Args:
            input: Existing task/perception/memory DTO without a live device.
            runtime: Run-local policy state and last confirmed execution result.
        Raises:
            ValueError: Perception or App Memory does not follow its declared contract.
            Exception: The selected model provider fails.
        Returns:
            Action: One SWIPE/TAP/TEXT/KEY/START_APP, DONE or explicit FAIL.
        """
        previous = runtime.state.last_action_result
        if previous is not None and not previous.succeeded:
            return _failure("previous_action_failed")
        ui = UIState.model_validate(input.perception.data.get("autodroid"))
        guides = [fragment for fragment in input.memory_context if fragment.metadata.get("source") == "autodroid.app_memory"]
        if len(guides) != 1:
            return _failure("missing_or_ambiguous_app_memory")
        guide = Guide.model_validate(guides[0].content)
        state = runtime.state.strategy_state.setdefault("autodroid.reasoning", PolicyState())
        if ui.app_id and ui.app_id != guide.app_id:
            state.pending.clear()
            state.scan, state.scanned = None, None
            return Action(ActionType.START_APP, {"app": guide.app_id}, metadata={"autodroid.phase": "recovery"})
        if not state.shortcut_attempted:
            state.shortcut_attempted = True
            if self.shortcut_enabled and guide.hits and guide.hits[0].score >= self.shortcut_threshold:
                state.pending = list(guide.hits[0].entry.path)
                state.pending_kind = "shortcut"
        pending = self._next_pending(state, ui)
        if pending is not None:
            return pending
        if self.scan_enabled and ui.regions and state.scanned is None:
            scan_action = self._scan(state, ui)
            if scan_action is not None:
                return scan_action
        candidates = state.scanned if state.scanned is not None else ui.candidates
        ui_text, candidates = self._prompt_ui(candidates, guide, ui)
        history: list[str] = []
        for fragment in input.memory_context:
            if fragment.type is FragmentType.ACTION and isinstance(fragment.content, Action):
                action = fragment.content
                if action.metadata.get("autodroid.phase") == "scan":
                    continue
                history.append(action.metadata.get("autodroid.target") or action.type.value + " " + json.dumps(action.params, ensure_ascii=False))
            elif fragment.type is FragmentType.ERROR:
                history.append("Execution error: " + str(fragment.content))
        prompt = read_prompt(self.prompt_file).replace("{task}", input.task.instruction).replace("{history}", "\n".join(history)).replace("{ui}", ui_text)
        for attempt in range(self.parse_max_retries + 1):
            response = self.llm.generate(prompt, images=None)
            try:
                choice = self.parser.parse(response)
                break
            except ActionParseError:
                if attempt == self.parse_max_retries:
                    return _failure("model_output_invalid")
        if choice.choice_id == -1:
            return Action(ActionType.DONE, thought=choice.thought, metadata={"autodroid.phase": "decision"})
        selected = [item for item in candidates if item.choice_id == choice.choice_id]
        if len(selected) != 1 or not selected[0].interactive:
            return _failure("selected_id_invalid")
        target = Target(key=selected[0].key, operation=choice.operation, text=choice.text)
        state.pending = [*selected[0].prefix, target]
        state.pending_kind = "decision"
        action = self._next_pending(state, ui)
        return replace(action, thought=choice.thought)
