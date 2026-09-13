"""从 trajectory 中抽取文本，按 ``match`` 模式与 ``expected`` 比较（布尔 / 首个整数 / 字符串）。"""

import re
from typing import Any, Dict, List, Optional, Tuple

from zhixing.core.agent.protocol import Action, ActionType
from zhixing.core.benchmark.interface import BaseEvaluator
from zhixing.core.benchmark.param_handler import ParamHandler
from zhixing.core.benchmark.protocol import EvalResult
from zhixing.core.factory import PluginRegistry

_BOOL_WORD = re.compile(r"\b(true|false)\b", re.IGNORECASE)
_FIRST_INT = re.compile(r"-?\d+")


def _extract_text_from_step(entry: Dict[str, Any], include_raw: bool) -> str:
    action = entry.get("action")
    if not isinstance(action, Action):
        return ""
    parts: List[str] = []
    t = getattr(action, "thought", None)
    if isinstance(t, str) and t.strip():
        parts.append(t.strip())
    if include_raw and isinstance(action.metadata, dict):
        raw = action.metadata.get("raw_response")
        if isinstance(raw, str) and raw.strip():
            parts.append(raw.strip())
    return "\n".join(parts)


def _collect_source_text(trajectory: List[Dict[str, Any]], source: str, include_raw: bool) -> str:
    if not trajectory:
        return ""

    src = (source or "last_step_thought").strip().lower()

    if src == "last_done_thought":
        for entry in reversed(trajectory):
            act = entry.get("action")
            if isinstance(act, Action) and act.type == ActionType.DONE:
                return _extract_text_from_step(entry, include_raw)
        return ""

    if src == "last_step_bundle":
        return _extract_text_from_step(trajectory[-1], include_raw)

    if src != "last_step_thought":
        pass
    for entry in reversed(trajectory):
        act = entry.get("action")
        if not isinstance(act, Action):
            continue
        t = getattr(act, "thought", None)
        if isinstance(t, str) and t.strip():
            return t.strip()
    if include_raw:
        for entry in reversed(trajectory):
            act = entry.get("action")
            if isinstance(act, Action) and isinstance(act.metadata, dict):
                raw = act.metadata.get("raw_response")
                if isinstance(raw, str) and raw.strip():
                    return raw.strip()
    return ""


def _first_boolean_token(text: str) -> Optional[bool]:
    m = _BOOL_WORD.search(text or "")
    if not m:
        return None
    return m.group(1).lower() == "true"


def _normalize_text(s: str, collapse_ws: bool) -> str:
    s = s or ""
    return " ".join(s.split()) if collapse_ws else s


@PluginRegistry.register(namespace="evaluator.llm_output_judge", name="trajectory_expected_match")
class TrajectoryExpectedMatchEvaluator(BaseEvaluator):
    """Compare agent trajectory text to ``expected`` using ``match`` mode.

    Params (JSON under ``evaluator.params``):

    - **expected** (required unless using map): Interpretation depends on ``match``:

        - ``boolean``: ``True`` or ``False`` (string, supports ``${...}``).
        - ``first_integer``: integer (supports ``${...}`` rendered to int).
        - ``exact`` / ``contains``: string (supports ``${...}``), unless using **expected_from_map** below.

    - **match** (str, optional): ``boolean`` (default), ``first_integer``, ``exact``, ``contains``.

    - **source** (str, optional): ``last_step_thought`` (default), ``last_step_bundle``,
      ``last_done_thought``.

    - **include_raw_response** (bool, optional): For ``last_step_thought``, fall back to
      ``metadata.raw_response`` when thought is empty (default ``true``).

    - **ignore_case** (bool, optional): For ``exact`` default ``false``; for ``contains`` default ``true``.

    - **normalize_whitespace** (bool, optional): Collapse whitespace for ``exact`` / ``contains``
      (default ``true``).

    For ``exact`` / ``contains`` you may instead supply **expected_from_map** (object) and
    **map_lookup_key** (string): the gold string is ``expected_from_map[task_params[map_lookup_key]]``
    (case-insensitive key match). Omit **expected** when using this form.
    """

    def _resolve_string_expected(self, context: Dict[str, Any]) -> Tuple[Optional[str], Optional[EvalResult]]:
        """Return (expected_string, None) or (None, failure EvalResult)."""
        fmap = self.params.get("expected_from_map")
        mkey_raw = self.params.get("map_lookup_key")
        mkey = str(mkey_raw).strip() if mkey_raw is not None else ""

        if fmap is not None and mkey:
            if not isinstance(fmap, dict):
                return None, EvalResult(
                    is_pass=False, reason="expected_from_map must be a JSON object (string keys)."
                )
            task_params = context.get("task_params") or {}
            raw_key = task_params.get(mkey)
            if raw_key is None:
                return None, EvalResult(
                    is_pass=False,
                    reason=f"task_params missing {mkey!r} (needed for expected_from_map lookup).",
                )
            sk = str(raw_key).strip()
            val = fmap.get(sk)
            if val is None:
                for k, v in fmap.items():
                    if str(k).strip().lower() == sk.lower():
                        val = v
                        break
            if val is None:
                return None, EvalResult(
                    is_pass=False,
                    reason=f"expected_from_map has no entry for task_params[{mkey!r}]={sk!r}.",
                )
            return str(val), None

        if "expected" not in self.params:
            return None, EvalResult(
                is_pass=False,
                reason="Provide expected or both expected_from_map and map_lookup_key.",
            )
        return ParamHandler.get_and_render(self.params, "expected", context, str), None

    def evaluate(self, context: Dict[str, Any]) -> EvalResult:
        match_raw = self.get_param("match", context, default="boolean", expected_type=str)
        match_mode = (match_raw or "boolean").strip().lower()
        aliases = {
            "bool": "boolean",
            "integer": "first_integer",
            "first_int": "first_integer",
            "equals": "exact",
            "string_equals": "exact",
            "substring": "contains",
        }
        match_mode = aliases.get(match_mode, match_mode)

        source = self.get_param("source", context, default="last_step_thought", expected_type=str)
        include_raw = self.get_param(
            "include_raw_response", context, default=True, expected_type=bool
        )

        traj = context.get("trajectory") or []
        if not isinstance(traj, list) or len(traj) == 0:
            return EvalResult(is_pass=False, reason="Empty trajectory; no agent output to judge.")

        text = _collect_source_text(traj, source, include_raw)
        if not text.strip():
            return EvalResult(
                is_pass=False,
                reason=f"No extractable text for source={source!r} (thought / raw_response empty).",
            )

        if match_mode == "boolean":
            return self._eval_boolean(context, text)
        if match_mode == "first_integer":
            return self._eval_first_integer(context, text)
        if match_mode == "exact":
            return self._eval_exact(context, text)
        if match_mode == "contains":
            return self._eval_contains(context, text)

        return EvalResult(
            is_pass=False,
            reason=(
                f"Unknown match mode {match_raw!r}; use boolean, first_integer, exact, or contains."
            ),
        )

    def _eval_boolean(self, context: Dict[str, Any], text: str) -> EvalResult:
        expected_raw = self.get_param("expected", context, expected_type=str).strip()
        if expected_raw.lower() not in ("true", "false"):
            return EvalResult(
                is_pass=False,
                reason=f"Invalid expected boolean {expected_raw!r}; must be True or False.",
            )
        expected_bool = expected_raw.lower() == "true"

        parsed = _first_boolean_token(text)
        if parsed is None:
            snippet = text.replace("\n", " ")[:200]
            return EvalResult(
                is_pass=False,
                reason=f"No standalone True/False token found in agent text. Snippet: {snippet!r}",
            )

        if parsed == expected_bool:
            return EvalResult(
                is_pass=True,
                reason=f"Parsed boolean {parsed!r} matches expected {expected_bool!r}.",
            )
        return EvalResult(
            is_pass=False,
            reason=f"Parsed boolean {parsed!r} does not match expected {expected_bool!r}.",
        )

    def _eval_first_integer(self, context: Dict[str, Any], text: str) -> EvalResult:
        expected = self.get_param("expected", context, expected_type=int)
        m = _FIRST_INT.search(text)
        if not m:
            snippet = text.replace("\n", " ")[:200]
            return EvalResult(
                is_pass=False,
                reason=f"No integer token found in agent text. Snippet: {snippet!r}",
            )
        try:
            got = int(m.group(0))
        except ValueError:
            return EvalResult(is_pass=False, reason=f"Could not parse integer from {m.group(0)!r}")

        if got == expected:
            return EvalResult(
                is_pass=True,
                reason=f"First integer {got} matches expected {expected}.",
            )
        return EvalResult(
            is_pass=False,
            reason=f"First integer {got} does not match expected {expected}.",
        )

    def _eval_exact(self, context: Dict[str, Any], text: str) -> EvalResult:
        expected, err = self._resolve_string_expected(context)
        if err is not None:
            return err
        assert expected is not None
        collapse = self.get_param("normalize_whitespace", context, default=True, expected_type=bool)
        ignore_case = self.get_param("ignore_case", context, default=False, expected_type=bool)
        a = _normalize_text(text, collapse)
        b = _normalize_text(expected, collapse)
        if ignore_case:
            a, b = a.lower(), b.lower()
        if a == b:
            return EvalResult(is_pass=True, reason="Trajectory text exactly matches expected string.")
        return EvalResult(
            is_pass=False,
            reason=f"Exact string mismatch: got {a[:200]!r} vs expected {b!r}.",
        )

    def _eval_contains(self, context: Dict[str, Any], text: str) -> EvalResult:
        expected, err = self._resolve_string_expected(context)
        if err is not None:
            return err
        assert expected is not None
        collapse = self.get_param("normalize_whitespace", context, default=True, expected_type=bool)
        ignore_case = self.get_param("ignore_case", context, default=True, expected_type=bool)
        hay = _normalize_text(text, collapse)
        needle = _normalize_text(expected, collapse)
        if ignore_case:
            ok = needle.lower() in hay.lower()
        else:
            ok = needle in hay
        if ok:
            return EvalResult(is_pass=True, reason="Trajectory text contains expected substring.")
        return EvalResult(
            is_pass=False,
            reason=f"Substring not found: expected fragment {needle!r} in text snippet {hay[:200]!r}.",
        )
