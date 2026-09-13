"""Compare ``SELECT COUNT(*) FROM table WHERE ...`` to an expected integer."""

from __future__ import annotations

import os
import sqlite3
import tempfile
from typing import Any, Dict

from zhixing.core.benchmark.protocol import EvalResult
from zhixing.core.benchmark.base_system import BaseSystemAction
from zhixing.core.benchmark.param_handler import ParamHandler
from zhixing.core.factory import PluginRegistry
from zhixing.plugins.benchmark.evaluator.system_state.sqlite_where_match import (
    _build_exists_sql,
    _quote_posix_single,
)
from zhixing.plugins.benchmark.evaluator.system_state.sqlite_row_match import (
    _profile_when_from_raw,
    _when_matches,
)


@PluginRegistry.register(namespace="evaluator.system_state", name="sqlite_row_count_match")
class SqliteRowCountMatchAction(BaseSystemAction):
    """Pass iff ``SELECT COUNT(*) FROM table WHERE ...`` equals ``expected_count``.

    Reuses the same WHERE builder as ``sqlite_where_match`` (identifier-safe columns).

    Optional **when**: ``{ "<task_param>": "<literal or ${...}>" }`` — if set and it does
    not match ``task_params``, this rule is **skipped** (passes vacuously). Use inside
  ``composite`` AND to branch on dynamic task params (e.g. ``ingredient``).
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
        expected_count = self.get_param("expected_count", context, expected_type=int)
        use_pull = self.get_param("use_pull", context, default=False, expected_type=bool)

        where_raw = self.params.get("where")
        if where_raw is None:
            return EvalResult(is_pass=False, reason="Missing required param: where.")
        task_params = context.get("task_params", {})
        where = ParamHandler.render_placeholders(where_raw, task_params)
        if not isinstance(where, dict):
            return EvalResult(
                is_pass=False,
                reason=f"After render, 'where' must be an object, got {type(where).__name__}.",
            )

        sql, err = _build_exists_sql(table, where)
        if err:
            return EvalResult(is_pass=False, reason=err)
        assert sql is not None

        self.logger.info(
            "sqlite_row_count_match: expected_count=%s use_pull=%s sql=%r",
            expected_count,
            use_pull,
            sql,
        )

        if use_pull:
            return self._evaluate_via_pull(database, sql, expected_count)
        return self._evaluate_via_shell(database, sql, expected_count)

    def _evaluate_via_shell(self, database: str, sql: str, expected_count: int) -> EvalResult:
        inner = sql.rstrip(";")
        cmd = f"sqlite3 {_quote_posix_single(database)} {_quote_posix_single(inner)}"
        raw = self._run_device_shell(cmd)
        if raw.startswith("ERROR:"):
            return EvalResult(is_pass=False, reason=f"Shell/sqlite3 failed: {raw}")
        low = (raw or "").strip().lower()
        if "error" in low or "unable to open" in low:
            return EvalResult(is_pass=False, reason=f"sqlite3 error: {raw[:500]!r}")
        try:
            count = int(float((raw or "").strip().split()[0]))
        except (ValueError, IndexError):
            return EvalResult(
                is_pass=False,
                reason=f"Unexpected sqlite3 output (expected integer count): {raw!r}",
            )
        if count == expected_count:
            return EvalResult(
                is_pass=True,
                reason=f"COUNT(*)={count} matches expected_count={expected_count}.",
            )
        return EvalResult(
            is_pass=False,
            reason=f"COUNT(*)={count} does not match expected_count={expected_count}.",
        )

    def _evaluate_via_pull(self, database: str, sql: str, expected_count: int) -> EvalResult:
        device = self.device
        tmp_db = os.path.join(tempfile.gettempdir(), f"unimobile_eval_count_{os.getpid()}.db")
        try:
            device.shell(
                f"sqlite3 {_quote_posix_single(database)} {_quote_posix_single('PRAGMA wal_checkpoint(FULL);')}"
            )
            result = device.pull(database, tmp_db)
            if result.exit_code != 0:
                return EvalResult(
                    is_pass=False,
                    reason=f"pull DB failed: {getattr(result, 'error', '')}",
                )
            if not os.path.exists(tmp_db):
                return EvalResult(is_pass=False, reason="pull succeeded but temp DB missing on host.")

            conn = sqlite3.connect(tmp_db)
            cur = conn.cursor()
            cur.execute(sql.replace(";", ""))
            row = cur.fetchone()
            conn.close()
            val = row[0] if row else 0
            try:
                count = int(float(val))
            except (TypeError, ValueError):
                count = -1
            if count == expected_count:
                return EvalResult(
                    is_pass=True,
                    reason=f"COUNT(*)={count} matches expected_count={expected_count} (pulled DB).",
                )
            return EvalResult(
                is_pass=False,
                reason=f"COUNT(*)={count} does not match expected_count={expected_count} (pulled DB).",
            )
        except Exception as e:
            self.logger.error("sqlite_row_count_match pull path failed: %s", e, exc_info=True)
            return EvalResult(is_pass=False, reason=f"pull/eval error: {e}")
        finally:
            if os.path.exists(tmp_db):
                try:
                    os.remove(tmp_db)
                except OSError:
                    pass
