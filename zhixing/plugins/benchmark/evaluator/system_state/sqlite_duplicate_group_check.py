"""Generic SQLite duplicate-group and row-count checks on device (read-only).

Use for tasks like “remove exact duplicates, keep one per group”: any group of rows
that share the same values on ``group_by_columns`` must have size ``<= max_per_group``
(typically ``1``). Optionally enforce total row count and/or that several logical
rows each exist **exactly once** (AND ``WHERE`` clauses).

Works wherever ``adb shell sqlite3 <path> '...'`` can open the DB (same assumption as
``sqlite_where_match`` / ``android_injection_insert_sqlite_rows``).
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from zhixing.core.benchmark.protocol import EvalResult
from zhixing.core.benchmark.base_system import BaseSystemAction
from zhixing.core.benchmark.param_handler import ParamHandler
from zhixing.core.factory import PluginRegistry

from zhixing.plugins.benchmark.evaluator.system_state.sqlite_where_match import (
    _build_exists_sql,
    _quote_posix_single,
    _sql_literal,
    _validate_identifier,
)
from zhixing.plugins.benchmark.evaluator.system_state.sqlite_row_match import (
    _profile_when_from_raw,
    _when_matches,
)


def _build_duplicate_violation_count_sql(table: str, group_cols: List[str], max_per_group: int) -> Tuple[str | None, str | None]:
    if max_per_group < 1:
        return None, "max_per_group must be >= 1."
    for c in group_cols:
        err = _validate_identifier(c, "column name")
        if err:
            return None, err
    err_t = _validate_identifier(table, "table name")
    if err_t:
        return None, err_t
    if not group_cols:
        return None, "group_by_columns must be a non-empty list."
    inner_cols = ", ".join(group_cols)
    # Number of distinct groups that still have more than max_per_group rows.
    sql = (
        f"SELECT COUNT(*) FROM (SELECT 1 FROM {table} GROUP BY {inner_cols} "
        f"HAVING COUNT(*) > {int(max_per_group)}) AS _dup_violation_groups;"
    )
    return sql, None


def _build_total_count_sql(table: str) -> Tuple[str | None, str | None]:
    err_t = _validate_identifier(table, "table name")
    if err_t:
        return None, err_t
    return f"SELECT COUNT(*) FROM {table};", None


@PluginRegistry.register(namespace="evaluator.system_state", name="sqlite_duplicate_group_check")
class SqliteDuplicateGroupCheckAction(BaseSystemAction):
    """Pass iff no duplicate groups exceed the cap, and optional row-count / row-presence rules hold.

    Parameters (placeholders ``${...}`` resolved from ``context['task_params']``):

    - **database** (required): Absolute path to SQLite on device.
    - **table** (required): Table name.
    - **group_by_columns** (required): List of column names; two rows are in the same
      duplicate group iff all listed columns are equal (``GROUP BY`` semantics).
    - **max_per_group** (optional, default ``1``): Each group must have ``COUNT(*) <= max_per_group``.
      For “delete duplicates, keep one”, use ``1`` (equivalently: no group with ``COUNT(*) > 1``).
    - **exact_row_count** (optional): Total ``SELECT COUNT(*) FROM table`` must equal this integer.
      Use with ``required_row_matches`` to reject extra stray rows.
    - **required_row_matches** (optional): List of objects; each object is an AND ``WHERE`` map
      (same shape as ``sqlite_where_match.where``). For each entry, ``COUNT(*)`` with those
      predicates must be **exactly** ``1`` (one row left matching that signature).

    Example (Pro Expense ``expense`` dedupe; amounts in **cents** as stored)::

        "evaluator": {
            "name": "system_state",
            "params": {
                "method": "sqlite_duplicate_group_check",
                "database": "/data/data/com.arduia.expense/databases/accounting.db",
                "table": "expense",
                "group_by_columns": [
                    "name", "amount", "category", "note", "created_date", "modified_date"
                ],
                "max_per_group": 1,
                "exact_row_count": 2,
                "required_row_matches": [
                    {
                        "name": "Office Supply Purchase",
                        "amount": 15000,
                        "category": 1,
                        "note": "Stationery for team daily use",
                        "created_date": 1715616000000,
                        "modified_date": 1715616000000
                    },
                    {
                        "name": "Client Business Lunch",
                        "amount": 12000,
                        "category": 3,
                        "note": "Customer meeting meal",
                        "created_date": 1715702400000,
                        "modified_date": 1715702400000
                    }
                ]
            }
        }

    Omit ``exact_row_count`` / ``required_row_matches`` if you only need “no duplicate groups”
    without pinning the full gold state (weaker; an agent could delete all rows and vacuously
    pass the group check unless you add ``exact_row_count`` or required matches).
    """

    def evaluate(self, context: Dict[str, Any]) -> EvalResult:
        task_params = context.get("task_params") or {}
        when = _profile_when_from_raw(self.params, context)
        if when and not _when_matches(when, task_params):
            return EvalResult(
                is_pass=True,
                reason=f"Skipped: when {when!r} does not match task_params.",
            )

        database = self.get_param("database", context, expected_type=str).strip()
        table = self.get_param("table", context, expected_type=str).strip()

        raw_groups = self.params.get("group_by_columns")
        if raw_groups is None:
            return EvalResult(is_pass=False, reason="Missing required param: group_by_columns.")
        group_by_columns = ParamHandler.render_placeholders(raw_groups, task_params)
        if not isinstance(group_by_columns, list) or not all(isinstance(c, str) for c in group_by_columns):
            return EvalResult(
                is_pass=False,
                reason="group_by_columns must be a list of column name strings after render.",
            )

        max_per_group = self.get_param("max_per_group", context, default=1, expected_type=int)

        dup_sql, err = _build_duplicate_violation_count_sql(table, group_by_columns, max_per_group)
        if err or dup_sql is None:
            return EvalResult(is_pass=False, reason=err or "internal SQL build error")

        n_viol = self._sqlite3_single_int(database, dup_sql)
        if n_viol is None:
            return EvalResult(is_pass=False, reason="duplicate-check query failed (see logs / shell output).")
        if n_viol > 0:
            return EvalResult(
                is_pass=False,
                reason=(
                    f"Found {n_viol} duplicate group(s): some rows share the same values on "
                    f"{group_by_columns!r} with COUNT(*) > {max_per_group}."
                ),
            )

        if "exact_row_count" in self.params:
            want = self.get_param("exact_row_count", context, expected_type=int)
            total_sql, err2 = _build_total_count_sql(table)
            if err2 or total_sql is None:
                return EvalResult(is_pass=False, reason=err2 or "internal SQL error")
            got = self._sqlite3_single_int(database, total_sql)
            if got is None:
                return EvalResult(is_pass=False, reason="COUNT(*) total query failed.")
            if got != want:
                return EvalResult(
                    is_pass=False,
                    reason=f"Total row count mismatch: expected {want}, got {got}.",
                )

        raw_req = self.params.get("required_row_matches")
        req_match_count = 0
        if raw_req is not None:
            required_list = ParamHandler.render_placeholders(raw_req, task_params)
            if not isinstance(required_list, list):
                return EvalResult(
                    is_pass=False,
                    reason="required_row_matches must be a list after render.",
                )
            req_match_count = len(required_list)
            for i, where in enumerate(required_list):
                if not isinstance(where, dict) or not where:
                    return EvalResult(
                        is_pass=False,
                        reason=f"required_row_matches[{i}] must be a non-empty object.",
                    )
                sql_count, err3 = _build_exists_sql(table, where)
                if err3:
                    return EvalResult(is_pass=False, reason=f"required_row_matches[{i}]: {err3}")
                assert sql_count is not None
                cnt = self._sqlite3_single_int(database, sql_count)
                if cnt is None:
                    return EvalResult(
                        is_pass=False,
                        reason=f"required_row_matches[{i}]: COUNT query failed.",
                    )
                if cnt != 1:
                    return EvalResult(
                        is_pass=False,
                        reason=(
                            f"required_row_matches[{i}]: expected exactly 1 row matching {where!r}, "
                            f"got COUNT={cnt}."
                        ),
                    )

        parts = [f"no groups with COUNT(*) > {max_per_group} on columns {group_by_columns!r}"]
        if "exact_row_count" in self.params:
            parts.append(f"total rows = {self.get_param('exact_row_count', context, expected_type=int)}")
        if req_match_count:
            parts.append(f"{req_match_count} required signature(s) each matched exactly once")
        return EvalResult(is_pass=True, reason="Pass: " + "; ".join(parts) + ".")

    def _sqlite3_single_int(self, database: str, sql: str) -> int | None:
        inner = sql.rstrip(";").strip()
        cmd = f"sqlite3 {_quote_posix_single(database)} {_quote_posix_single(inner)}"
        raw = self._run_device_shell(cmd)
        if raw.startswith("ERROR:"):
            self.logger.error("sqlite3 shell error: %s", raw)
            return None
        low = (raw or "").strip().lower()
        if "error" in low or "unable to open" in low:
            self.logger.error("sqlite3 returned: %s", raw[:500])
            return None
        try:
            return int(float((raw or "").strip().split()[0]))
        except (ValueError, IndexError):
            self.logger.error("unexpected sqlite3 output: %r", raw)
            return None
