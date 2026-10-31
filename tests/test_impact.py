from datetime import date

import pytest

from dependency_engine.examples import load_example
from dependency_engine.impact import UnknownTask, delay_impact, what_if

RENO = load_example("residential_renovation")


def test_critical_delay_moves_completion_by_the_full_amount():
    r = delay_impact(RENO, "electrical", 3)
    assert r.finish_before == date(2026, 11, 27) and r.finish_after == date(2026, 12, 2)
    assert r.finish_shift_days == 3 and r.absorbed_by_float == 0
    assert r.downstream_tasks == 8 and len(r.affected) == 8
    assert all(a.start_shift_days == 3 for a in r.affected)
    assert "critical path" in r.explanation and "Wed Dec 2, 2026" in r.explanation


def test_delay_within_float_moves_nothing():
    r = delay_impact(RENO, "hvac", 2)  # HVAC has 2 days of float
    assert r.finish_shift_days == 0 and r.absorbed_by_float == 2
    assert r.affected == [] and len(r.unaffected_downstream) == 8
    assert "now also critical" in r.explanation


def test_delay_beyond_float_moves_completion_by_the_excess():
    r = delay_impact(RENO, "hvac", 3)
    assert r.finish_shift_days == 1 and r.absorbed_by_float == 2


def test_off_critical_branch_with_large_float():
    r = delay_impact(RENO, "windows", 10)  # 26 days of float
    assert r.finish_shift_days == 0
    assert r.affected == []  # walkthrough doesn't move


def test_errors():
    with pytest.raises(UnknownTask):
        delay_impact(RENO, "nope", 1)
    projected = RENO.model_copy(update={"as_of": date(2026, 11, 2)})
    with pytest.raises(ValueError, match="already complete"):
        delay_impact(projected, "demo", 2)


def test_what_if_shorter_critical_task():
    r = what_if(RENO, {"drywall": 4})
    assert r.finish_shift_days == -2 and r.finish_after == date(2026, 11, 25)


def test_what_if_non_critical_change_within_float():
    assert what_if(RENO, {"cabinets": 9}).finish_shift_days == 0  # 5 days float, +4


def test_what_if_non_critical_task_becomes_critical():
    r = what_if(RENO, {"cabinets": 11})  # +6 with 5 days float → +1
    assert r.finish_shift_days == 1
    assert "Kitchen cabinets & counters" in r.critical_path_after


def test_what_if_unknown_task():
    with pytest.raises(UnknownTask):
        what_if(RENO, {"nope": 3})
