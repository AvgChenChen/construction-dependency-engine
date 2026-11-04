"""Every expected value here was worked out by hand (see comments) before the code ran."""

import random
from datetime import date

import pytest

from dependency_engine.cpm import ScheduleError, analyze
from dependency_engine.examples import load_example

from .helpers import by_id, random_dag, schedule


def test_textbook_example_forward_backward_and_float():
    # A3 → B4 → D5 → F2 and A → C2 → E1 → F.
    # Forward: A 0-3, B 3-7, C 3-5, D 7-12, E 5-6, F 12-14. Project = 14.
    # Backward: F 12-14, D 7-12, E 11-12, B 3-7, C 9-11, A 0-3.
    r = analyze(load_example("textbook_cpm"))
    t = by_id(r)
    expected = {  # id: (ES, EF, LS, LF, total float, free float)
        "A": (0, 3, 0, 3, 0, 0),
        "B": (3, 7, 3, 7, 0, 0),
        "C": (3, 5, 9, 11, 6, 0),
        "D": (7, 12, 7, 12, 0, 0),
        "E": (5, 6, 11, 12, 6, 6),
        "F": (12, 14, 12, 14, 0, 0),
    }
    for tid, (es, ef, ls, lf, tf, ff) in expected.items():
        assert (
            t[tid].early_start,
            t[tid].early_finish,
            t[tid].late_start,
            t[tid].late_finish,
            t[tid].total_float,
            t[tid].free_float,
        ) == (es, ef, ls, lf, tf, ff), tid
    assert r.project_duration_days == 14
    assert r.critical_path == ["A", "B", "D", "F"]
    # Start Mon Nov 2; working day 13 (0-based) is Thu Nov 19.
    assert r.projected_finish == date(2026, 11, 19)
    assert t["F"].start_date == date(2026, 11, 18) and t["F"].finish_date == date(2026, 11, 19)


def test_residential_renovation_baseline():
    # Oct 12 is a holiday, so day 0 is Tue Oct 13. Critical chain:
    # demo 4 + framing 5 + electrical 5 + inspection 1 + insulation 2 + drywall 6 + paint 4 + flooring 3 + trim 3 + walkthrough 1 = 34.
    r = analyze(load_example("residential_renovation"))
    t = by_id(r)
    assert r.start_date == date(2026, 10, 13)
    assert r.project_duration_days == 34
    assert r.projected_finish == date(2026, 11, 27)
    assert (t["plumbing"].total_float, t["hvac"].total_float, t["windows"].total_float, t["cabinets"].total_float) == (
        1,
        2,
        26,
        5,
    )
    assert r.critical_path == [
        "demo",
        "framing",
        "electrical",
        "inspection",
        "insulation",
        "drywall",
        "painting",
        "flooring",
        "trim",
        "walkthrough",
    ]


def test_projected_mode_uses_progress_and_status_date():
    # As of Mon Nov 2 (offset 14): done tasks need 0 days; electrical is 60% of 5 → ceil(2) = 2 days, Nov 2-3.
    # Then inspection 1, insulation 2, drywall 6, paint 4, flooring 3, trim 3, walkthrough 1 → 14 + 2 + 20 = 36 → Tue Dec 1.
    s = load_example("residential_renovation").model_copy(update={"as_of": date(2026, 11, 2)})
    r = analyze(s)
    t = by_id(r)
    assert r.mode == "projected"
    assert t["electrical"].remaining_days == 2
    assert t["electrical"].start_date == date(2026, 11, 2) and t["electrical"].finish_date == date(2026, 11, 3)
    assert r.project_duration_days == 36 and r.projected_finish == date(2026, 12, 1)
    assert t["demo"].start_date is None and not t["demo"].critical  # complete: no dates, never critical
    assert r.critical_path[0] == "electrical"


def test_no_remaining_work_starts_before_the_status_date():
    s = schedule([("a", 3), ("b", 2, ["a"])], as_of=date(2026, 11, 9))  # a not started, a week late
    t = by_id(analyze(s))
    assert t["a"].start_date == date(2026, 11, 9)
    assert t["b"].start_date == date(2026, 11, 12)


def test_progress_inconsistency_is_warned_not_hidden():
    s = schedule(
        [
            {"id": "a", "name": "A", "duration_days": 3, "status": "in_progress", "percent_complete": 50},
            {"id": "b", "name": "B", "duration_days": 2, "status": "complete", "depends_on": ["a"]},
        ],
        as_of=date(2026, 11, 4),
    )
    r = analyze(s)
    assert [w.type for w in r.warnings] == ["progress_inconsistency"]


def test_milestones_and_parallel_ties():
    # Two equal parallel paths: both critical; the path picks the earlier-listed one.
    r = analyze(schedule([("start", 0), ("x", 3, ["start"]), ("y", 3, ["start"]), ("end", 0, ["x", "y"])]))
    t = by_id(r)
    assert r.project_duration_days == 3
    assert t["x"].critical and t["y"].critical
    assert r.critical_path == ["start", "x", "end"]


def test_delay_days_extend_duration():
    r = analyze(schedule([{"id": "a", "name": "A", "duration_days": 2, "delay_days": 3}]))
    assert r.project_duration_days == 5


def test_invalid_schedules_raise_with_readable_issues():
    with pytest.raises(ScheduleError) as e:
        analyze(load_example("circular_dependency"))
    assert e.value.issues[0].type == "cycle"
    assert "which waits on" in e.value.issues[0].message
    with pytest.raises(ScheduleError):
        analyze(schedule([("a", 1, ["missing"])]))


def test_absurdly_long_schedules_are_rejected_cleanly():
    tasks = [{"id": str(i), "name": "t", "duration_days": 1000, "depends_on": [str(i - 1)] if i else []} for i in range(20)]
    with pytest.raises(ScheduleError) as e:
        analyze(schedule(tasks))
    assert e.value.issues[0].type == "schedule_too_long"


def test_float_invariants_hold_on_300_random_schedules():
    """Properties every CPM result must have, checked on seeded random graphs (ENG-003).

    1. A task is critical exactly when its total float is 0, and every task on the
       reported critical path is critical.
    2. 0 <= free float <= total float.
    3. Total float is the same measured at either end: LS - ES == LF - EF == TF.
    """
    rng = random.Random(20261104)
    checked = 0
    for _ in range(300):
        tasks = random_dag(rng, rng.randint(1, 40), rng.uniform(0.02, 0.4))
        r = analyze(schedule(tasks))
        t = by_id(r)
        for tid in r.critical_path:
            assert t[tid].total_float == 0, tid
        for res in r.tasks:
            assert res.critical == (res.total_float == 0), res.id
            assert 0 <= res.free_float <= res.total_float, res.id
            assert res.late_start - res.early_start == res.total_float, res.id
            assert res.late_finish - res.early_finish == res.total_float, res.id
            checked += 1
    assert checked > 3000  # enough tasks to mean something
