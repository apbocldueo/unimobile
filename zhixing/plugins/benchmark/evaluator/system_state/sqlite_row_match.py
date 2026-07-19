"""Flexible SQLite row matcher (read-only, on-device ``sqlite3``).

Fills the gap between ``sqlite_where_match`` (SQL ``col = literal`` only) and
``sqlite_row_count_match`` (count only): SELECT listed columns, compare in Python.

---------------------------------------------------------------------------
Evaluation modes (pick one via JSON shape — do not mix)
---------------------------------------------------------------------------

**Mode A — ``checks``** (single recipe / any matching row)

Pass iff **at least one** row satisfies **every** check in ``checks``.

**Mode B — ``profiles``** (multiple recipes / all must exist)

Pass iff **every active** profile has **at least one** row satisfying that
profile's ``checks``. One SELECT, one pass over rows.

---------------------------------------------------------------------------
Shared params
---------------------------------------------------------------------------

- **database**, **table** (required)
- **columns** (required): non-empty list of column names to SELECT

**Check object** (used in ``checks`` or ``profiles[].checks``):

- **column** (required): must appear in **columns**
- **match**: ``exact`` | ``contains`` | ``substring_either`` | ``flex_text`` |
  ``digits_or_substring`` (default ``exact``)
- **expected**: literal or ``${...}`` (exclusive with **parsed_key**)
- **parsed_key**: key from parsed block (exclusive with **expected**)
- **optional**: skip when expected value is empty after resolve (default false)

- **parse_block_param** (optional): ``task_params`` key with ``Key: value;`` text
  (e.g. AndroidWorld ``Title: …; Time: …``). Required if any check uses
  **parsed_key**.

**Profile object** (mode B only):

- **label** (optional): for failure messages
- **checks** (required): non-empty check list
- **when** (optional): ``{ "<task_param>": "<literal or ${...}>" , ... }``.
  Profile is **active** only when **every** key matches ``task_params[key]``
  (after rendering the expected value) using ``digits_or_substring``.
  Example: ``"when": { "prep_time": "10 mins" }`` for Markor filter tasks.

Deprecated: **for_prep_time** on a profile is treated as
``"when": { "prep_time": "<value>" }``.

Does **not** handle app-specific unit conversion (e.g. Pro Expense cents).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from zhixing.core.benchmark.protocol import EvalResult
from zhixing.core.benchmark.base_system import BaseSystemAction
from zhixing.core.benchmark.param_handler import ParamHandler
from zhixing.core.factory import PluginRegistry
from zhixing.plugins.benchmark.evaluator.system_state.sqlite_where_match import (
    _quote_posix_single,
    _validate_identifier,
)

_SEP = "\x1f"
_FIELD_RE = re.compile(r"^\s*([^:;]+?)\s*:\s*(.+?)\s*$", re.DOTALL)


@dataclass(frozen=True)
class _ProfileSpec:
    label: str
    checks: List[Dict[str, Any]]
    when: Dict[str, str]


def _norm(s: str) -> str:
    return " ".join((s or "").split()).lower()


def _parse_key_value_block(text: str) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for chunk in re.split(r";\s*\n?", text or ""):
        chunk = chunk.strip()
        if not chunk:
            continue
        m = _FIELD_RE.match(chunk)
        if not m:
            continue
        out[m.group(1).strip().lower()] = m.group(2).strip()
    return out


def _match_exact(expected: str, got: str) -> bool:
    if expected == got:
        return True
    return _norm(expected) == _norm(got)


def _match_contains(expected: str, got: str) -> bool:
    a, b = _norm(expected), _norm(got)
    if not a:
        return True
    return a in b


def _match_substring_either(expected: str, got: str) -> bool:
    a, b = _norm(expected), _norm(got)
    if not a:
        return True
    if not b:
        return False
    return a in b or b in a


def _match_flex_text(expected: str, got: str) -> bool:
    a, b = _norm(expected), _norm(got)
    if not a or not b:
        return False
    return a == b or a in b or b in a


def _match_digits_or_substring(expected: str, got: str) -> bool:
    exp = (expected or "").strip()
    if not exp:
        return True
    g = (got or "").strip()
    if not g:
        return False
    if exp in g or g in exp:
        return True
    exp_digits = re.sub(r"\D", "", exp)
    got_digits = re.sub(r"\D", "", g)
    return bool(exp_digits) and exp_digits == got_digits


_MATCHERS = {
    "exact": _match_exact,
    "contains": _match_contains,
    "substring_either": _match_substring_either,
    "flex_text": _match_flex_text,
    "digits_or_substring": _match_digits_or_substring,
}


def _apply_match(mode: str, expected: str, got: str) -> bool:
    fn = _MATCHERS.get((mode or "exact").strip().lower())
    if fn is None:
        raise ValueError(f"Unknown match mode {mode!r}")
    return fn(expected, got)


def _sqlite_select_command(database: str, table: str, columns: List[str], sep_sql: str) -> str:
    parts = [f"IFNULL({c}, '')" for c in columns]
    concat = f" || {sep_sql} || ".join(parts)
    inner = f"SELECT {concat} FROM {table};"
    return f"sqlite3 {_quote_posix_single(database)} {_quote_posix_single(inner)}"


def _parse_fetched_rows(raw: str, ncols: int) -> List[List[str]]:
    rows: List[List[str]] = []
    for line in (raw or "").splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split(_SEP)
        if len(parts) != ncols:
            continue
        rows.append(parts)
    return rows


def _profile_when_from_raw(prof: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, str]:
    when_raw = prof.get("when")
    if when_raw is not None:
        if not isinstance(when_raw, dict) or not when_raw:
            return {}
        out: Dict[str, str] = {}
        for key, val in when_raw.items():
            if not isinstance(key, str):
                continue
            out[key] = ParamHandler.get_and_render({"v": val}, "v", context, str)
        return out
    if "for_prep_time" in prof:
        return {
            "prep_time": ParamHandler.get_and_render(
                {"for_prep_time": prof["for_prep_time"]},
                "for_prep_time",
                context,
                str,
            )
        }
    return {}


def _when_matches(when: Dict[str, str], task_params: Dict[str, Any]) -> bool:
    if not when:
        return True
    for key, expected in when.items():
        actual = task_params.get(key)
        if actual is None:
            return False
        if not _match_digits_or_substring(expected, str(actual)):
            return False
    return True


@PluginRegistry.register(namespace="evaluator.system_state", name="sqlite_row_match")
class SqliteRowMatchAction(BaseSystemAction):
    """See module docstring."""

    def evaluate(self, context: Dict[str, Any]) -> EvalResult:
        database = self.get_param("database", context, expected_type=str).strip()
        table = self.get_param("table", context, expected_type=str).strip()

        columns, err = self._parse_columns(self.params.get("columns"))
        if err:
            return EvalResult(is_pass=False, reason=err)

        err_t = _validate_identifier(table, "table name")
        if err_t:
            return EvalResult(is_pass=False, reason=err_t)

        parsed_block = self._load_parsed_block(context)
        profiles, err = self._parse_profiles(self.params, columns, context)
        if err:
            return EvalResult(is_pass=False, reason=err)

        sep_sql = f"char({ord(_SEP)})"
        cmd = _sqlite_select_command(database, table, columns, sep_sql)
        self.logger.info(
            "sqlite_row_match table=%r columns=%r profiles=%d",
            table,
            columns,
            len(profiles),
        )

        raw = self._run_device_shell(cmd)
        if raw.startswith("ERROR:"):
            return EvalResult(is_pass=False, reason=f"Shell/sqlite3 failed: {raw}")
        low = (raw or "").lower()
        if "unable to open database" in low or "no such table" in low:
            return EvalResult(is_pass=False, reason=f"sqlite3 error: {raw[:500]!r}")

        rows = _parse_fetched_rows(raw, len(columns))
        if not rows:
            return EvalResult(
                is_pass=False,
                reason=f"No rows returned from {table!r} (table empty or SELECT failed).",
            )

        col_index = {c: i for i, c in enumerate(columns)}
        task_params = context.get("task_params") or {}
        active = [p for p in profiles if _when_matches(p.when, task_params)]
        if not active:
            return EvalResult(
                is_pass=False,
                reason="No active profiles (check profile 'when' vs task_params).",
            )

        if len(profiles) == 1 and not profiles[0].when:
            checks = profiles[0].checks
            for row_vals in rows:
                if self._row_passes(checks, row_vals, col_index, parsed_block, context):
                    return EvalResult(
                        is_pass=True,
                        reason=f"At least one row in {table!r} matched all {len(checks)} check(s).",
                    )
            return EvalResult(
                is_pass=False,
                reason=f"No row in {table!r} matched all checks (scanned {len(rows)} row(s)).",
            )

        missing: List[str] = []
        for spec in active:
            if not any(
                self._row_passes(spec.checks, row_vals, col_index, parsed_block, context)
                for row_vals in rows
            ):
                missing.append(spec.label)
        if missing:
            return EvalResult(
                is_pass=False,
                reason=(
                    f"No row matched profile(s) {missing!r} in {table!r} "
                    f"(scanned {len(rows)} row(s))."
                ),
            )
        return EvalResult(
            is_pass=True,
            reason=f"All {len(active)} active profile(s) matched at least one row in {table!r}.",
        )

    def _parse_columns(self, columns_raw: Any) -> Tuple[List[str], str | None]:
        if not isinstance(columns_raw, list) or not columns_raw:
            return [], "Missing required param: columns (non-empty array)."
        columns: List[str] = []
        for c in columns_raw:
            if not isinstance(c, str):
                return [], "Each columns entry must be a string."
            err = _validate_identifier(c, "column name")
            if err:
                return [], err
            columns.append(c)
        return columns, None

    def _load_parsed_block(self, context: Dict[str, Any]) -> Dict[str, str]:
        parse_param = self.params.get("parse_block_param")
        if parse_param is None:
            return {}
        key = str(parse_param).strip()
        if not key:
            return {}
        task_params = context.get("task_params") or {}
        text = task_params.get(key)
        if text is None:
            text = ParamHandler.get_and_render(self.params, "parse_block_param", context, str)
        else:
            text = str(text)
        return _parse_key_value_block(text)

    def _parse_profiles(
        self,
        params: Dict[str, Any],
        columns: List[str],
        context: Dict[str, Any],
    ) -> Tuple[List[_ProfileSpec], str | None]:
        profiles_raw = params.get("profiles")
        checks_raw = params.get("checks")

        if profiles_raw is not None:
            if not isinstance(profiles_raw, list) or not profiles_raw:
                return [], "profiles must be a non-empty array when set."
            if checks_raw:
                return [], "Use either top-level 'checks' or 'profiles', not both."
            specs: List[_ProfileSpec] = []
            for i, prof in enumerate(profiles_raw):
                if not isinstance(prof, dict):
                    return [], f"profiles[{i}] must be an object."
                label = str(prof.get("label") or f"profile_{i}")
                validated, err = self._validate_checks_list(
                    prof.get("checks"), columns, f"profiles[{i}].checks"
                )
                if err:
                    return [], err
                specs.append(
                    _ProfileSpec(
                        label=label,
                        checks=validated,
                        when=_profile_when_from_raw(prof, context),
                    )
                )
            return specs, None

        validated, err = self._validate_checks_list(checks_raw, columns, "checks")
        if err:
            return [], err
        return [_ProfileSpec(label="default", checks=validated, when={})], None

    def _validate_checks_list(
        self,
        checks_raw: Any,
        columns: List[str],
        what: str,
    ) -> Tuple[List[Dict[str, Any]], str | None]:
        if not isinstance(checks_raw, list) or not checks_raw:
            return [], f"Missing required param: {what} (non-empty array)."
        checks: List[Dict[str, Any]] = []
        for i, chk in enumerate(checks_raw):
            if not isinstance(chk, dict):
                return [], f"{what}[{i}] must be an object."
            col = chk.get("column")
            if not col or not isinstance(col, str):
                return [], f"{what}[{i}] missing column."
            if col not in columns:
                return [], f"{what}[{i}] column {col!r} not in columns list."
            checks.append(chk)
        return checks, None

    def _row_passes(
        self,
        checks: List[Dict[str, Any]],
        row_vals: List[str],
        col_index: Dict[str, int],
        parsed_block: Dict[str, str],
        context: Dict[str, Any],
    ) -> bool:
        for chk in checks:
            col = chk["column"]
            got = row_vals[col_index[col]]
            mode = chk.get("match", "exact")
            optional = bool(chk.get("optional", False))

            expected: Optional[str] = None
            if "parsed_key" in chk:
                pk = str(chk["parsed_key"]).strip().lower()
                expected = parsed_block.get(pk)
                if expected is None and not optional:
                    return False
            elif "expected" in chk:
                expected = ParamHandler.get_and_render(
                    {"expected": chk["expected"]},
                    "expected",
                    context,
                    str,
                )
            else:
                return False

            if expected is None or str(expected).strip() == "":
                if optional:
                    continue
                return False

            try:
                if not _apply_match(str(mode), str(expected), got):
                    return False
            except ValueError as e:
                self.logger.error("sqlite_row_match: %s", e)
                return False
        return True
