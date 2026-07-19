"""Match rows returned by ``adb shell content query`` (ContentProvider), not raw SQLite files.

Typical use: ``content query --uri content://sms/sent --projection address:body``

Output lines look like::

    Row: 0 address=+15551234, body=Hello

Pass iff at least one parsed row satisfies every entry in ``checks`` (same shape as
``sqlite_row_match``).
"""

from __future__ import annotations

import re
import shlex
from typing import Any, Dict, List, Optional

from zhixing.core.benchmark.base_system import BaseSystemAction
from zhixing.core.benchmark.param_handler import ParamHandler
from zhixing.core.benchmark.protocol import EvalResult
from zhixing.core.factory import PluginRegistry
from zhixing.plugins.benchmark.evaluator.system_state.sqlite_row_match import _apply_match

_ROW_PREFIX = re.compile(r"^Row:\s*(\d+)\s+(.*)$", re.DOTALL)


def _parse_projection(projection_raw: Any) -> List[str]:
    if projection_raw is None:
        return []
    if isinstance(projection_raw, str):
        text = projection_raw.strip()
        if not text:
            return []
        if ":" in text and "," not in text:
            return [p.strip() for p in text.split(":") if p.strip()]
        return [p.strip() for p in text.split(",") if p.strip()]
    if isinstance(projection_raw, list):
        cols: List[str] = []
        for item in projection_raw:
            if not isinstance(item, str) or not item.strip():
                raise ValueError("Each projection entry must be a non-empty string.")
            cols.append(item.strip())
        return cols
    raise ValueError("projection must be a string, list of strings, or omitted.")


def _parse_row_payload(payload: str, field_names: List[str]) -> Dict[str, str]:
    """Extract ``field=value`` pairs from the tail of a ``Row:`` line."""
    out: Dict[str, str] = {}
    if not payload or not field_names:
        return out
    for field in field_names:
        marker = f"{field}="
        pos = payload.find(marker)
        if pos < 0:
            continue
        start = pos + len(marker)
        end = len(payload)
        for other in field_names:
            if other == field:
                continue
            nxt = payload.find(f", {other}=", start)
            if nxt >= 0:
                end = min(end, nxt)
        out[field] = payload[start:end].strip()
    return out


def _parse_content_query_output(raw: str, field_names: List[str]) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    for line in (raw or "").splitlines():
        line = line.strip()
        if not line:
            continue
        m = _ROW_PREFIX.match(line)
        if not m:
            continue
        parsed = _parse_row_payload(m.group(2), field_names)
        if parsed:
            rows.append(parsed)
    return rows


def _build_query_command(
    uri: str,
    projection: List[str],
    selection: str,
    selection_args: str,
    sort: str,
    limit: str,
) -> str:
    parts: List[str] = ["content", "query", "--uri", uri]
    if projection:
        parts.extend(["--projection", ":".join(projection)])
    if selection:
        parts.extend(["--where", selection])
    if selection_args:
        parts.extend(["--bind", selection_args])
    if sort:
        parts.extend(["--sort", sort])
    if limit:
        parts.extend(["--limit", limit])
    return " ".join(shlex.quote(p) for p in parts)


@PluginRegistry.register(namespace="evaluator.system_state", name="content_query_row_match")
class ContentQueryRowMatchAction(BaseSystemAction):
    """Generic ``content query`` row matcher (any ContentProvider URI).

    Params:

    - **uri** (required unless **query_command** is set): e.g. ``content://sms/sent``
    - **query_command** (optional): Full shell command override (placeholders allowed).
    - **projection** (optional): Column list or ``"col1:col2"`` string for ``--projection``.
      Also used to parse ``Row:`` lines when set; otherwise inferred from ``checks`` columns.
    - **selection**, **selection_args**, **sort**, **limit** (optional): Passed to ``content query``.
    - **checks** (required): Same objects as ``sqlite_row_match`` (``column``, ``expected``, ``match``).
    """

    def evaluate(self, context: Dict[str, Any]) -> EvalResult:
        checks_raw = self.params.get("checks")
        if not isinstance(checks_raw, list) or not checks_raw:
            return EvalResult(is_pass=False, reason="Missing required param: checks (non-empty array).")

        checks: List[Dict[str, Any]] = []
        columns: List[str] = []
        for i, chk in enumerate(checks_raw):
            if not isinstance(chk, dict):
                return EvalResult(is_pass=False, reason=f"checks[{i}] must be an object.")
            col = chk.get("column")
            if not col or not isinstance(col, str):
                return EvalResult(is_pass=False, reason=f"checks[{i}] missing column.")
            checks.append(chk)
            if col not in columns:
                columns.append(col)

        try:
            projection = _parse_projection(self.params.get("projection"))
        except ValueError as e:
            return EvalResult(is_pass=False, reason=str(e))

        parse_fields = projection if projection else columns

        query_command = self.params.get("query_command")
        if query_command is not None:
            cmd = ParamHandler.get_and_render(
                {"query_command": query_command},
                "query_command",
                context,
                str,
            ).strip()
        else:
            uri = ParamHandler.get_and_render(self.params, "uri", context, str).strip()
            if not uri:
                return EvalResult(is_pass=False, reason="Missing required param: uri (or set query_command).")
            selection = ""
            if "selection" in self.params:
                selection = ParamHandler.get_and_render(
                    self.params, "selection", context, str
                ).strip()
            selection_args = ""
            if "selection_args" in self.params:
                selection_args = ParamHandler.get_and_render(
                    self.params, "selection_args", context, str
                ).strip()
            sort = ""
            if "sort" in self.params:
                sort = ParamHandler.get_and_render(self.params, "sort", context, str).strip()
            limit = ""
            if "limit" in self.params:
                limit = ParamHandler.get_and_render(self.params, "limit", context, str).strip()
            cmd = _build_query_command(uri, projection, selection, selection_args, sort, limit)

        self.logger.info("content_query_row_match: cmd=%r", cmd)
        raw = self._run_device_shell(cmd)
        if raw.startswith("ERROR:"):
            return EvalResult(is_pass=False, reason=f"Shell/content query failed: {raw}")

        low = (raw or "").lower()
        if "error while accessing provider" in low or "illegalargumentexception" in low:
            return EvalResult(
                is_pass=False,
                reason=f"Content provider error: {raw[:500]!r}",
            )

        rows = _parse_content_query_output(raw, parse_fields)
        if not rows:
            preview = (raw or "")[:400]
            return EvalResult(
                is_pass=False,
                reason=f"No rows parsed from content query (truncated): {preview!r}",
            )

        for row in rows:
            if self._row_passes(checks, row, context):
                return EvalResult(
                    is_pass=True,
                    reason=f"At least one content row matched all {len(checks)} check(s).",
                )

        return EvalResult(
            is_pass=False,
            reason=f"No content row matched all checks (parsed {len(rows)} row(s)).",
        )

    def _row_passes(
        self,
        checks: List[Dict[str, Any]],
        row: Dict[str, str],
        context: Dict[str, Any],
    ) -> bool:
        for chk in checks:
            col = chk["column"]
            got = row.get(col, "")
            mode = chk.get("match", "exact")
            optional = bool(chk.get("optional", False))

            if "expected" not in chk:
                return False
            expected = ParamHandler.get_and_render(
                {"expected": chk["expected"]},
                "expected",
                context,
                str,
            )
            if expected is None or str(expected).strip() == "":
                if optional:
                    continue
                return False

            try:
                if not _apply_match(str(mode), str(expected), got):
                    return False
            except ValueError as e:
                self.logger.error("content_query_row_match: %s", e)
                return False
        return True
