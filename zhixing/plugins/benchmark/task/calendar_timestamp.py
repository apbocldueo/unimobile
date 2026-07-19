from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict

from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from zhixing.core.benchmark.interface import BaseParamInitializerGenerator
from zhixing.core.factory import PluginRegistry

_WEEKDAY = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}

_DEFAULT_TZ_NAMES = (
    "local",
    "system",
    "device",
    "browser",
    "timezone_local",
)


@PluginRegistry.register(namespace="benchmark.task", name="calendar_timestamp")
class CalendarTimestampGenerator(BaseParamInitializerGenerator):
    """Unix seconds for Simple Calendar Pro ``events.start_ts`` / ``events.end_ts``.

    Date (pick one): **offset_days**, **weekday** (``Monday`` …), or **year** + **month** + **day**.
    Time: **hour** (0–23, or 1–12 with **time** ``am``/``pm``), **duration_mins** (default 60).
    Optional **timezone** may be an IANA name like ``Asia/Shanghai``.
    If omitted, the generator keeps the previous local-time behavior so old JSON configs still work.
    **role**: ``start`` (default) or ``end`` (start + duration).
    """

    @staticmethod
    def _hour_24(hour: int, ampm: Any) -> int:
        if ampm is None or str(ampm).strip() == "":
            return int(hour)
        ap = str(ampm).strip().lower()
        h = int(hour)
        if ap == "am":
            return 0 if h == 12 else h
        if ap == "pm":
            return 12 if h == 12 else h + 12
        raise ValueError(f"Unknown am/pm {ampm!r}; use am or pm.")

    @staticmethod
    def _resolve_timezone(params: Dict[str, Any]):
        tz_name = params.get("timezone", params.get("tz"))
        if tz_name is None or str(tz_name).strip() == "":
            return None
        tz_key = str(tz_name).strip()
        if tz_key.lower() in _DEFAULT_TZ_NAMES:
            return None
        if tz_key.upper() == "UTC":
            return timezone.utc
        try:
            return ZoneInfo(tz_key)
        except ZoneInfoNotFoundError as exc:
            raise ValueError(f"Unknown timezone {tz_name!r}; use an IANA timezone like 'Asia/Shanghai'.") from exc

    def generate(self, params: Dict[str, Any]) -> int:
        hour = self._hour_24(int(params.get("hour", 0)), params.get("time"))
        duration_mins = int(params.get("duration_mins", 60))
        role = str(params.get("role", "start")).strip().lower()
        tzinfo = self._resolve_timezone(params)

        if "offset_days" in params:
            day = date.today() + timedelta(days=int(params["offset_days"]))
        elif "weekday" in params:
            key = str(params["weekday"]).strip().lower()
            if key not in _WEEKDAY:
                raise ValueError(f"Unknown weekday {params['weekday']!r}")
            target = _WEEKDAY[key]
            today = date.today()
            days_ahead = (target - today.weekday()) % 7
            day = today + timedelta(days=days_ahead)
        elif all(k in params for k in ("year", "month", "day")):
            day = date(int(params["year"]), int(params["month"]), int(params["day"]))
        else:
            raise ValueError(
                "calendar_timestamp needs offset_days, weekday, or year+month+day."
            )

        if tzinfo is None:
            start_dt = datetime(day.year, day.month, day.day, hour, 0, 0)
        else:
            start_dt = datetime(day.year, day.month, day.day, hour, 0, 0, tzinfo=tzinfo)

        if role == "end":
            ts = int((start_dt + timedelta(minutes=duration_mins)).timestamp())
        else:
            ts = int(start_dt.timestamp())

        unit = str(params.get("unit", "seconds")).strip().lower()
        if unit in ("ms", "millisecond", "milliseconds"):
            return ts * 1000
        return ts
