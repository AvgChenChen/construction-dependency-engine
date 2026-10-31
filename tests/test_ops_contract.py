"""Contract test: a real export from construction-ops-platform must analyse unchanged.

The fixture was produced by the Ops app's own exportSchedule() from its fictional seed
data (as_of = 2026-10-31). If either side changes ScheduleContract v1, this fails.
"""

from datetime import date

from dependency_engine.cpm import analyze
from dependency_engine.examples import load_example
from dependency_engine.impact import delay_impact


def test_ops_export_is_accepted_and_projected_from_progress():
    s = load_example("ops_export_maple_ridge")
    assert s.contract_version == "1.0" and len(s.tasks) == 12
    r = analyze(s)
    assert r.mode == "projected"
    # As of Sat Oct 31 → first working day Mon Nov 2. Electrical (60% of 5) needs 2 more days.
    assert r.projected_finish == date(2026, 12, 1)
    assert r.critical_path_names[0] == "Electrical rough-in"
    assert not any(t.critical for t in r.tasks if t.status == "complete")


def test_ops_export_planned_baseline_and_delay():
    s = load_example("ops_export_maple_ridge")
    assert analyze(s.model_copy(update={"as_of": None})).projected_finish == date(2026, 11, 26)
    electrical = next(t.id for t in s.tasks if t.name == "Electrical rough-in")
    assert delay_impact(s, electrical, 2).finish_after == date(2026, 12, 3)
