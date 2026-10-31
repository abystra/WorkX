"""Automation schedules: standard 5-field cron, evaluated in the automation's IANA time zone.

The scheduler that turns due automations into tasks is R2 (P-10); this module computes ``next_run_at``.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from workx.core.errors import validation

_RANGES = ((0, 59), (0, 23), (1, 31), (1, 12), (0, 6))


def _field(spec: str, low: int, high: int) -> set[int]:
    values: set[int] = set()
    for part in spec.split(","):
        step = 1
        if "/" in part:
            part, step_text = part.split("/", 1)
            step = int(step_text)
        if part in ("*", ""):
            start, end = low, high
        elif "-" in part:
            a, b = part.split("-", 1)
            start, end = int(a), int(b)
        else:
            start = end = int(part)
        if start < low or end > high or start > end or step < 1:
            raise ValueError(spec)
        values.update(range(start, end + 1, step))
    return values


def parse(expression: str) -> tuple[set[int], ...]:
    parts = expression.split()
    if len(parts) != 5:
        raise validation("Use a 5-field cron schedule, for example `0 9 * * 1-5`.", data={"field": "schedule"})
    try:
        fields = tuple(_field(p, lo, hi) for p, (lo, hi) in zip(parts, _RANGES, strict=True))
    except ValueError as exc:
        raise validation("The schedule is not a valid cron expression.", data={"field": "schedule"}) from exc
    # Cron allows 7 for Sunday.
    return fields


def next_run(expression: str, timezone: str, after: datetime | None = None) -> datetime:
    minutes, hours, days, months, weekdays = parse(expression)
    try:
        zone = ZoneInfo(timezone)
    except ZoneInfoNotFoundError as exc:
        raise validation("Unknown time zone.", data={"field": "timezone"}) from exc
    moment = (after or datetime.now(zone)).astimezone(zone).replace(second=0, microsecond=0) + timedelta(minutes=1)
    for _ in range(366 * 24 * 60):
        cron_weekday = (moment.weekday() + 1) % 7
        if (
            moment.minute in minutes
            and moment.hour in hours
            and moment.day in days
            and moment.month in months
            and cron_weekday in weekdays
        ):
            return moment
        moment += timedelta(minutes=1)
    raise validation("The schedule never runs.", data={"field": "schedule"})
