"""Generic SQLite row existence check on device (read-only).

Pairs with ``android_injection_insert_sqlite_rows``: same ``database`` / ``table``
ideas, but only checks ``SELECT COUNT(*) ... WHERE`` built from a ``where`` dict (ANDed).

**Feasibility / limits**

- Works wherever ``adb shell sqlite3 <path> '...'`` can open the DB (same
  assumption as ``android_reset_clear_sqlite_rows`` / Android World images).
- ``table`` and every key in ``where`` must match ``^[A-Za-z_][A-Za-z0-9_]*$`` to
  avoid SQL injection from config.
- Values are compared as SQL literals (strings escaped; numbers passed as numeric
  literals booleans coerced to 0/1). There is **no** per-app unit conversion
  (e.g. dollars→cents): encode the expected stored value in YAML or task_params.
- Match a **NULL** column with JSON ``null`` in ``where`` (renders to Python
  ``None`` → SQL ``col IS NULL``).
"""

from __future__ import annotations

import re
import sqlite3
import os
import tempfile
from typing import Any, Dict, Tuple

from zhixing.core.benchmark.protocol import EvalResult
from zhixing.core.benchmark.base_system import BaseSystemAction
from zhixing.core.benchmark.param_handler import ParamHandler
from zhixing.core.factory import PluginRegistry

_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _quote_posix_single(s: str) -> str:
    """Wrap ``s`` in single quotes for ``/system/bin/sh`` on device.

    ``AndroidDevice.shell`` already wraps the whole command in double quotes; inner
    ``"`` characters break parsing. Use only POSIX single-quoted segments instead.
    """
    return "'" + s.replace("'", "'\\''") + "'"


def _sql_literal(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if value.is_integer():
            return str(int(value))
        return repr(value)
    s = str(value).replace("'", "''")
    return f"'{s}'"


def _validate_identifier(name: str, what: str) -> str | None:
    if not name or not _IDENTIFIER.match(name):
        return f"Invalid {what} {name!r}; use only letters, digits, underscore, not starting with a digit."
    return None


def _build_exists_sql(table: str, where: Dict[str, Any]) -> Tuple[str | None, str | None]:
    if not where:
        return None, "Parameter 'where' must be a non-empty object."
    parts = []
    for col, val in where.items():
        err = _validate_identifier(col, "column name")
        if err:
            return None, err
        if val is None:
            parts.append(f"{col} IS NULL")
        else:
            parts.append(f"{col} = {_sql_literal(val)}")
    err_t = _validate_identifier(table, "table name")
    if err_t:
        return None, err_t
    # COUNT(*) avoids nested parens; semantics same as EXISTS for match / no-match.
    sql = f"SELECT COUNT(*) FROM {table} WHERE {' AND '.join(parts)};"
    return sql, None


@PluginRegistry.register(namespace="evaluator.system_state", name="sqlite_where_match")
class SqliteWhereMatchAction(BaseSystemAction):
    """Return pass iff ``SELECT COUNT(*) FROM table WHERE ... AND ...`` is greater than zero.

    Parameters (placeholders resolved from ``context['task_params']`` like other evaluators):

    - **database** (required): Absolute path to the SQLite file on device.
    - **table** (required): Table name.
    - **where** (required): Object mapping column names to expected scalar values (AND).
    - **expect_absent** (optional, default ``false``): If ``true``, pass iff ``COUNT(*)`` is **zero**
      (no row matches — use to verify a row was deleted). If ``false`` (default), pass iff
      ``COUNT(*) > 0`` (at least one matching row exists).
    - **use_pull** (optional, default ``false``): If ``true``, ``pull`` DB to host and run the
      query with Python ``sqlite3`` (parameterized, WAL checkpoint first). Safer for quoting
      and some WAL edge cases; slower. If ``false``, runs a single ``sqlite3`` shell line on device.

    Example::

        "evaluator": {
            "name": "system_state",
            "params": {
                "method": "sqlite_where_match",
                "database": "/data/data/com.arduia.expense/databases/accounting.db",
                "table": "expense",
                "where": {
                    "name": "${name}",
                    "amount": "${amount_cents}",
                    "category": "${category_id}",
                    "note": "${note}"
                }
            }
        }

    Here ``amount_cents`` / ``category_id`` would be produced by ``task_initializer`` (or static)
    so stored types match the DB without app-specific logic in this plugin.
    """

    def evaluate(self, context: Dict[str, Any]) -> EvalResult:
        database = self.get_param("database", context, expected_type=str).strip()
        table = self.get_param("table", context, expected_type=str).strip()
        use_pull = self.get_param("use_pull", context, default=False, expected_type=bool)
        expect_absent = self.get_param("expect_absent", context, default=False, expected_type=bool)

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
            "sqlite_where_match: use_pull=%s expect_absent=%s sql=%r",
            use_pull,
            expect_absent,
            sql,
        )

        if use_pull:
            return self._evaluate_via_pull(database, sql, expect_absent)
        return self._evaluate_via_shell(database, sql, expect_absent)

    def _evaluate_via_shell(self, database: str, sql: str, expect_absent: bool) -> EvalResult:
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
        if expect_absent:
            if count == 0:
                return EvalResult(
                    is_pass=True,
                    reason="expect_absent: COUNT(*) is 0 (no matching row).",
                )
            return EvalResult(
                is_pass=False,
                reason=(
                    f"expect_absent: expected no matching row but COUNT(*)={count}. "
                    "Row(s) still present for the given WHERE clause."
                ),
            )
        if count > 0:
            return EvalResult(is_pass=True, reason=f"COUNT(*) query returned {count} matching row(s).")
        return EvalResult(
            is_pass=False,
            reason=(
                "No row matched the given WHERE clause (COUNT was 0). "
                "For Pro Expense / Android World, ``amount`` is stored in **cents** (100 USD → 10000) "
                "and ``category`` is an **integer id** (Food → 3), not the UI string \"Food\"."
            ),
        )

    def _evaluate_via_pull(self, database: str, sql: str, expect_absent: bool) -> EvalResult:
        device = self.device
        tmp_db = os.path.join(tempfile.gettempdir(), f"unimobile_eval_pull_{os.getpid()}.db")
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
                cnt = int(float(val))
            except (TypeError, ValueError):
                cnt = -1
            if expect_absent:
                if cnt == 0:
                    return EvalResult(is_pass=True, reason="expect_absent: COUNT(*) is 0 (pulled DB).")
                return EvalResult(
                    is_pass=False,
                    reason=f"expect_absent: COUNT(*)={cnt} after pull (expected 0).",
                )
            ok = cnt > 0
            if ok:
                return EvalResult(is_pass=True, reason="COUNT(*) > 0 (pulled DB).")
            return EvalResult(
                is_pass=False,
                reason="No row matched the given WHERE clause (COUNT 0, pulled DB).",
            )
        except Exception as e:
            self.logger.error("sqlite_where_match pull path failed: %s", e, exc_info=True)
            return EvalResult(is_pass=False, reason=f"pull/eval error: {e}")
        finally:
            if os.path.exists(tmp_db):
                try:
                    os.remove(tmp_db)
                except OSError:
                    pass
