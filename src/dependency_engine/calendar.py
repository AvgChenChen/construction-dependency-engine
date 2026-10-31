"""Working-day calendar.

Schedules are computed in integer *working-day offsets* from the project start
(offset 0 = the first working day on or after start_date). Dates are only produced
at the end, so the graph algorithms never deal with weekends or holidays.
"""

from __future__ import annotations

from datetime import date, timedelta

from .models import CalendarConfig

_MAX_SCAN = 20_000  # ~55 years of calendar days; guards against a calendar with no working days


class WorkCalendar:
    def __init__(self, start: date, config: CalendarConfig | None = None):
        config = config or CalendarConfig()
        self.workdays = set(config.workdays)
        self.holidays = set(config.holidays)
        self.start = self.next_workday_on_or_after(start)
        self._days: list[date] = [self.start]  # offset -> date, grown on demand

    def is_workday(self, d: date) -> bool:
        return d.weekday() in self.workdays and d not in self.holidays

    def next_workday_on_or_after(self, d: date) -> date:
        for _ in range(_MAX_SCAN):
            if self.is_workday(d):
                return d
            d += timedelta(days=1)
        raise ValueError("calendar has no working days")

    def date_for_offset(self, offset: int) -> date:
        """The date of working day number `offset` (0-based) counted from the start."""
        if offset < 0:
            raise ValueError("offset must be >= 0")
        while len(self._days) <= offset:
            self._days.append(self.next_workday_on_or_after(self._days[-1] + timedelta(days=1)))
        return self._days[offset]

    def offset_for_date(self, d: date) -> int:
        """Working-day offset of `d` (or of the next working day if `d` isn't one). Dates before start → 0."""
        d = self.next_workday_on_or_after(d)
        if d <= self.start:
            return 0
        offset = 0
        while self.date_for_offset(offset) < d:
            offset += 1
        return offset
