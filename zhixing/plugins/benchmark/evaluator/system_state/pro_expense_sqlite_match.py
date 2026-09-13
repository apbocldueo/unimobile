"""Match a single expense row in Pro Expense (com.arduia.expense) SQLite DB.

Aligns with Android World ``Expense`` / ``expense`` table semantics:
``amount`` is stored in **cents**; ``category`` column holds **category_id**
(see ``category_id_to_name`` in android_world ``sqlite_schema_utils.Expense``).
"""

from __future__ import annotations

from typing import Dict, Any, List, Tuple

from zhixing.core.benchmark.protocol import EvalResult
from zhixing.core.benchmark.base_system import BaseSystemAction
from zhixing.core.factory import PluginRegistry

# android_world.task_evals.utils.sqlite_schema_utils.Expense.category_id_to_name
_CATEGORY_NAME_TO_ID: Dict[str, int] = {
    "others": 1,
    "income": 2,
    "food": 3,
    "housing": 4,
    "social": 5,
    "entertainment": 6,
    "transportation": 7,
    "clothes": 8,
    "health care": 9,
    "education": 10,
    "donation": 11,
}

_DEFAULT_DB = "/data/data/com.arduia.expense/databases/accounting.db"
_DEFAULT_TABLE = "expense"
# Unit separator — unlikely in generated name/note fields.
_SEP = "\x1f"


def _quote_posix_single(s: str) -> str:
    """Wrap ``s`` in POSIX single quotes for device ``sh`` (safe inside ``adb shell \"...\"``)."""
    return "'" + s.replace("'", "'\\''") + "'"


def _norm_name_key(s: str) -> str:
    return (s or "").strip().lower()


def _expected_amount_cents(raw: Any, unit: str) -> int | None:
    """Return expected amount in cents, or None if unparseable."""
    if raw is None:
        return None
    s = str(raw).strip().replace("$", "").replace(",", "")
    if not s:
        return None
    unit_l = (unit or "dollars").strip().lower()
    try:
        if "." in s:
            cents = int(round(float(s) * 100))
            return cents
        n = int(s)
        if unit_l in ("cent", "cents"):
            return n
        # dollars: whole or integer string from JSON
        return n * 100
    except ValueError:
        return None


def _parse_sqlite_rows(raw: str, sep: str) -> List[Tuple[str, int, int, str]]:
    rows: List[Tuple[str, int, int, str]] = []
    for line in (raw or "").splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split(sep)
        if len(parts) != 4:
            continue
        name_s, amount_s, cat_s, note_s = parts
        try:
            amount_i = int(float(amount_s))
            cat_i = int(float(cat_s))
        except ValueError:
            continue
        rows.append((name_s, amount_i, cat_i, note_s or ""))
    return rows


def _sqlite_select_command(database: str, table: str, sep_sql: str) -> str:
    inner = (
        f"SELECT name || {sep_sql} || amount || {sep_sql} || category || {sep_sql} || "
        f"IFNULL(note, '') FROM {table};"
    )
    return f"sqlite3 {_quote_posix_single(database)} {_quote_posix_single(inner)}"


@PluginRegistry.register(namespace="evaluator.system_state", name="pro_expense_sqlite_match")
class ProExpenseSqliteMatchAction(BaseSystemAction):
    """Check that ``expense`` contains a row matching **name** and **amount** (always).

    **name** and **amount** are required: ``amount`` is interpreted like Android World
    (default **dollars** in UI → **cents** in DB, e.g. ``"100"`` → 10000).

    **category** / **category_id** and **note** are optional: include the key in params
    only when you want that column checked. If **category** is a non-empty string, it is
    mapped to ``category_id`` (Food → 3, …). If a key is absent, or **category** / **note**
    is present but renders to empty after placeholders, that field is **not** used in the match.

    Runs ``sqlite3`` on the device (same assumption as ``android_reset_clear_sqlite_rows``).

    - **database** (optional): DB path; default Pro Expense ``accounting.db``.
    - **table** (optional): Default ``expense``.
    - **amount_unit** (optional): ``dollars`` (default) or ``cents``.
    - **sqlite_command** (optional): Full shell command; if set, overrides built-in SELECT.

    Example (name + amount only)::

        "params": {
            "method": "pro_expense_sqlite_match",
            "name": "${name}",
            "amount": "${amount}"
        }

    Example (full)::

        "params": {
            "method": "pro_expense_sqlite_match",
            "name": "${name}",
            "amount": "${amount}",
            "category": "${category}",
            "note": "${note}"
        }
    """

    def evaluate(self, context: Dict[str, Any]) -> EvalResult:
        name = self.get_param("name", context, expected_type=str).strip()
        if not name:
            return EvalResult(is_pass=False, reason="Missing required param: name.")

        amount_unit = self.get_param("amount_unit", context, default="dollars", expected_type=str)
        amount_raw = self.get_param("amount", context, default=None)
        expected_cents = _expected_amount_cents(amount_raw, amount_unit)
        if expected_cents is None:
            return EvalResult(
                is_pass=False,
                reason=f"Could not parse amount from {amount_raw!r} (amount_unit={amount_unit!r}).",
            )

        expected_cat_id: int | None = None
        if "category_id" in self.params:
            expected_cat_id = self.get_param("category_id", context, expected_type=int)
        elif "category" in self.params:
            category_name = self.get_param("category", context, default="", expected_type=str).strip()
            if category_name:
                key = _norm_name_key(category_name)
                if key not in _CATEGORY_NAME_TO_ID:
                    known = sorted(_CATEGORY_NAME_TO_ID.keys())
                    return EvalResult(
                        is_pass=False,
                        reason=f"Unknown category {category_name!r}; known names (case-insensitive): {known}.",
                    )
                expected_cat_id = _CATEGORY_NAME_TO_ID[key]

        expected_note: str | None = None
        if "note" in self.params:
            note_val = self.get_param("note", context, expected_type=str).strip()
            if note_val:
                expected_note = note_val

        database = self.get_param("database", context, default=_DEFAULT_DB, expected_type=str)
        table = self.get_param("table", context, default=_DEFAULT_TABLE, expected_type=str)

        cmd = self.get_param("sqlite_command", context, default="", expected_type=str).strip()
        if not cmd:
            sep_sql = f"char({ord(_SEP)})"
            cmd = _sqlite_select_command(database, table, sep_sql)

        self.logger.info("pro_expense_sqlite_match: cmd=%r", cmd)
        raw = self._run_device_shell(cmd)
        if raw.startswith("ERROR:"):
            return EvalResult(is_pass=False, reason=f"Shell/sqlite3 failed: {raw}")

        if "unable to open database" in raw.lower() or "no such table" in raw.lower():
            return EvalResult(is_pass=False, reason=f"sqlite3 error: {raw[:500]!r}")

        rows = _parse_sqlite_rows(raw, _SEP)
        if not rows:
            preview = (raw or "")[:400]
            return EvalResult(
                is_pass=False,
                reason=f"No expense rows parsed (expected 4 fields per line, sep U+001F). Output (truncated): {preview!r}",
            )

        for r_name, r_amount, r_cat, r_note in rows:
            if r_name.strip() != name:
                continue
            if r_amount != expected_cents:
                continue
            if expected_cat_id is not None and r_cat != expected_cat_id:
                continue
            if expected_note is not None and r_note.strip() != expected_note:
                continue
            parts = [f"name={name!r}", f"amount_cents={expected_cents}"]
            if expected_cat_id is not None:
                parts.append(f"category_id={expected_cat_id}")
            if expected_note is not None:
                parts.append(f"note={expected_note!r}")
            return EvalResult(is_pass=True, reason="Matched expense row: " + ", ".join(parts))

        parts = [f"name={name!r}", f"amount_cents={expected_cents}"]
        if expected_cat_id is not None:
            parts.append(f"category_id={expected_cat_id}")
        if expected_note is not None:
            parts.append(f"note={expected_note!r}")
        return EvalResult(
            is_pass=False,
            reason="No row matched (" + ", ".join(parts) + f"); parsed {len(rows)} row(s).",
        )
