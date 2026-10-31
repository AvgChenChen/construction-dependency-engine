from datetime import date

import pytest
from pydantic import ValidationError

from dependency_engine.calendar import WorkCalendar
from dependency_engine.models import CalendarConfig


def test_offsets_skip_weekends():
    cal = WorkCalendar(date(2026, 10, 30))  # Friday
    assert [cal.date_for_offset(i) for i in range(3)] == [date(2026, 10, 30), date(2026, 11, 2), date(2026, 11, 3)]


def test_start_on_a_holiday_moves_to_the_next_working_day():
    cal = WorkCalendar(date(2026, 10, 12), CalendarConfig(holidays=[date(2026, 10, 12)]))
    assert cal.start == date(2026, 10, 13)


def test_holidays_are_skipped_mid_project():
    cal = WorkCalendar(date(2026, 12, 23), CalendarConfig(holidays=[date(2026, 12, 25), date(2026, 12, 28)]))
    # Wed 23, Thu 24, (Fri 25 holiday, weekend, Mon 28 holiday), Tue 29
    assert [cal.date_for_offset(i) for i in range(3)] == [date(2026, 12, 23), date(2026, 12, 24), date(2026, 12, 29)]


def test_six_day_work_week():
    cal = WorkCalendar(date(2026, 11, 6), CalendarConfig(workdays=[0, 1, 2, 3, 4, 5]))
    assert cal.date_for_offset(1) == date(2026, 11, 7)  # Saturday counts


def test_offset_for_date_round_trips():
    cal = WorkCalendar(date(2026, 11, 2))
    for i in range(0, 30):
        assert cal.offset_for_date(cal.date_for_offset(i)) == i
    assert cal.offset_for_date(date(2026, 11, 7)) == 5  # Saturday → next Monday
    assert cal.offset_for_date(date(2026, 10, 1)) == 0  # before start


def test_invalid_workdays_rejected():
    with pytest.raises(ValidationError):
        CalendarConfig(workdays=[])
    with pytest.raises(ValidationError):
        CalendarConfig(workdays=[7])
