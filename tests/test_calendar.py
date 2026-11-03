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


def _five_day_task_from_dec_21(holidays, workdays=(0, 1, 2, 3, 4)):
    """Finish date of a 5-day task starting Mon 2026-12-21, through the full CPM path."""
    from dependency_engine.cpm import analyze
    from dependency_engine.models import ScheduleIn

    schedule = ScheduleIn(
        project_id="holidays",
        start_date=date(2026, 12, 21),
        calendar=CalendarConfig(workdays=list(workdays), holidays=holidays),
        tasks=[{"id": "T", "name": "T", "duration_days": 5}],
    )
    return analyze(schedule).projected_finish


def test_a_holiday_on_a_weekend_costs_nothing():
    # Mon 21, Tue 22, Wed 23, Thu 24, (Fri 25 holiday, Sat, Sun), Mon 28.
    # Sat 26 is already a day off, so listing it as a holiday must not push the finish to Tue 29.
    assert _five_day_task_from_dec_21([date(2026, 12, 25)]) == date(2026, 12, 28)
    assert _five_day_task_from_dec_21([date(2026, 12, 25), date(2026, 12, 26)]) == date(2026, 12, 28)


def test_a_duplicated_holiday_counts_once():
    holidays = [date(2026, 12, 25), date(2026, 12, 25), date(2026, 12, 26), date(2026, 12, 26)]
    assert _five_day_task_from_dec_21(holidays) == date(2026, 12, 28)
    cal = WorkCalendar(date(2026, 12, 21), CalendarConfig(holidays=holidays))
    assert [cal.date_for_offset(i) for i in range(5)] == [
        date(2026, 12, 21),
        date(2026, 12, 22),
        date(2026, 12, 23),
        date(2026, 12, 24),
        date(2026, 12, 28),
    ]


def test_a_saturday_holiday_does_cost_a_day_in_a_six_day_week():
    # The control case: when Saturday is a working day, a Saturday holiday really is lost time.
    six_days = (0, 1, 2, 3, 4, 5)
    assert _five_day_task_from_dec_21([date(2026, 12, 25)], six_days) == date(2026, 12, 26)  # Sat 26 works
    assert _five_day_task_from_dec_21([date(2026, 12, 25), date(2026, 12, 26)], six_days) == date(2026, 12, 28)
