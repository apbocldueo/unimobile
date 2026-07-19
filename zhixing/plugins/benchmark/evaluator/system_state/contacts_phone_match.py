from typing import Dict, Any, List, Tuple

from zhixing.core.benchmark.protocol import EvalResult
from zhixing.core.benchmark.base_system import BaseSystemAction
from zhixing.core.factory import PluginRegistry

# ContactsContract.CommonDataKinds.Phone.CONTENT_URI — must be ``.../data/phones`` (not ``phonees``).
_PHONES_CONTENT_URI = "content://com.android.contacts/data/phones"
_DEFAULT_QUERY = (
    f"content query --uri {_PHONES_CONTENT_URI} "
    "--projection display_name:data1"
)


def _digits(s: str) -> str:
    return "".join(c for c in (s or "") if c.isdigit())


def _phone_matches(actual_data1: str, expected: str) -> bool:
    """Compare phone strings loosely (ignore +, spaces, dashes)."""
    da = _digits(actual_data1)
    de = _digits(expected)
    if not de:
        return False
    return de in da or da == de or da.endswith(de)


def _norm_display(s: str) -> str:
    """Lowercase and collapse internal whitespace for comparing full display_name strings."""
    return " ".join((s or "").lower().split())


def _name_matches_display(display_name: str, first: str, last: str, single: str) -> bool:
    """Name rules (mutually exclusive by priority):

    1. **name** — Compare the whole ``display_name`` string to ``name`` (normalized equality).
    2. **first_name + last_name** — Concatenate ``first + ' ' + last`` and ``last + ' ' + first``;
       ``display_name`` must equal one of them after the same normalization.
    3. **only first_name** or **only last_name** — Normalized ``display_name`` must **equal** that
       single field (same normalization). ``Mary`` does **not** match ``mary zhen``.
    """
    d = _norm_display(display_name)
    if not d:
        return False

    sn = (single or "").strip()
    if sn:
        return d == _norm_display(sn)

    fn = (first or "").strip()
    ln = (last or "").strip()
    if fn and ln:
        a = _norm_display(f"{fn} {ln}")
        b = _norm_display(f"{ln} {fn}")
        return d == a or d == b
    if fn and not ln:
        return d == _norm_display(fn)
    if ln and not fn:
        return d == _norm_display(ln)
    return False


def _parse_rows(raw: str) -> List[Tuple[str, str]]:
    """Parse ``content query`` output lines such as
    ``Row: 0 display_name=Mary Zhen, data1=+112513513512``.

    Naive comma-splitting fails: the first segment is ``Row: 0 display_name=...``,
    which does not start with ``display_name=``, so ``display_name`` would never
    be captured.
    """
    rows: List[Tuple[str, str]] = []
    dn_marker = "display_name="
    for line in (raw or "").splitlines():
        line = line.strip()
        if not line.startswith("Row:"):
            continue
        sep = ", data1="
        idx = line.rfind(sep)
        if idx < 0:
            sep = ",data1="
            idx = line.rfind(sep)
        if idx < 0:
            continue
        left, data1 = line[:idx], line[idx + len(sep) :].strip()
        p = left.rfind(dn_marker)
        if p < 0:
            continue
        display_name = left[p + len(dn_marker) :].strip()
        if display_name and data1:
            rows.append((display_name, data1))
    return rows


@PluginRegistry.register(namespace="evaluator.system_state", name="contacts_phone_match")
class ContactsPhoneMatchAction(BaseSystemAction):
    """Query phone rows from ContactsProvider and check name + number without regex in JSON.

    Uses ``content query`` on ``data/phones`` with ``display_name:data1`` (see ContactsContract).

    Parameters (placeholders use ``task_params`` as usual):

    - **number** (required): Expected phone, e.g. ``"${number}"`` (alias **phone**).
    - **name** (optional): Full name string. After normalizing case and whitespace, must
      **equal** the entire ``display_name`` from the provider (e.g. ``Mary Zhen`` matches
      ``display_name=mary zhen``).
    - **first_name** / **last_name** (optional): If **both** are set, they are concatenated as
      ``first last`` and ``last first``; the normalized ``display_name`` must **equal** one of
      those concatenations.
    - If only **first_name** or only **last_name**: normalized ``display_name`` must **equal** that
      one field (same normalization). So ``Mary`` does not match ``mary zhen`` — use **name** or
      **first_name + last_name** for full names.

    - **query_command** (optional): Override the default ``content query ...`` string.

    Examples::

        # Full display string
        "params": {"method": "contacts_phone_match", "name": "${full_name}", "number": "${number}"}

        # First + last vs display_name
        "params": {
            "method": "contacts_phone_match",
            "first_name": "${first_name}",
            "last_name": "${last_name}",
            "number": "${number}",
        }

        # Display is exactly one token (e.g. contact saved as "Bob" only)
        "params": {"method": "contacts_phone_match", "first_name": "${name}", "number": "${number}"}
    """

    def evaluate(self, context: Dict[str, Any]) -> EvalResult:
        first = self.get_param("first_name", context, default="", expected_type=str).strip()
        last = self.get_param("last_name", context, default="", expected_type=str).strip()
        single = self.get_param("name", context, default="", expected_type=str).strip()

        number = self.get_param("number", context, default="", expected_type=str).strip()
        if not number:
            number = self.get_param("phone", context, default="", expected_type=str).strip()
        if not number:
            return EvalResult(is_pass=False, reason="Missing required param: number (or phone).")

        if not (first or last or single):
            return EvalResult(
                is_pass=False,
                reason="Provide at least one of: first_name, last_name, or name (for display_name matching).",
            )

        cmd = self.get_param("query_command", context, default=_DEFAULT_QUERY, expected_type=str)
        self.logger.info("contacts_phone_match: query=%r", cmd)
        raw = self._run_device_shell(cmd)
        if raw.startswith("ERROR:"):
            return EvalResult(is_pass=False, reason=f"Shell/query failed: {raw}")

        if "Error while accessing provider" in raw or "IllegalArgumentException" in raw:
            return EvalResult(
                is_pass=False,
                reason=f"Content provider error (check URI/projection on this device): {raw[:500]}",
            )

        rows = _parse_rows(raw)
        if not rows:
            preview = (raw or "")[:400]
            return EvalResult(
                is_pass=False,
                reason=f"No phone rows parsed from query output (truncated): {preview!r}",
            )

        for display_name, data1 in rows:
            if not _phone_matches(data1, number):
                continue
            if _name_matches_display(display_name, first, last, single):
                return EvalResult(
                    is_pass=True,
                    reason=f"Matched row display_name={display_name!r} data1={data1!r}",
                )

        return EvalResult(
            is_pass=False,
            reason=(
                f"No row matched number={number!r} with name rules "
                f"(first_name={first!r} last_name={last!r} name={single!r}); "
                f"parsed {len(rows)} row(s)."
            ),
        )
