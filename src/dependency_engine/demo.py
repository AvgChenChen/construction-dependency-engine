"""Walk through the engine on fictional schedules: python -m dependency_engine.demo"""

from __future__ import annotations

from datetime import date

from .cpm import ScheduleError, analyze
from .examples import load_example
from .impact import delay_impact, fmt, what_if


def section(title: str) -> None:
    print(f"\n{'=' * 78}\n{title}\n{'=' * 78}")


def print_schedule(result) -> None:
    print(f"{'Task':<34}{'Start':>17}{'Finish':>17}{'Float':>7}  Critical")
    for t in result.tasks:
        start = fmt(t.start_date) if t.start_date else "(done)"
        finish = fmt(t.finish_date) if t.finish_date else ""
        flt = "-" if t.start_date is None else str(t.total_float)
        print(f"{t.name[:33]:<34}{start:>17}{finish:>17}{flt:>7}  {'yes' if t.critical else ''}")
    print(f"\nProject: {result.project_duration_days} working days, finishing {fmt(result.projected_finish)}")
    print("Critical path: " + " → ".join(result.critical_path_names))


def main() -> None:
    reno = load_example("residential_renovation")

    section("1. Baseline plan: Maple Ridge renovation (Oct 12 is a holiday, so work starts Tue Oct 13)")
    print_schedule(analyze(reno))

    section("2. Electrical rough-in slips 3 working days")
    print(delay_impact(reno, "electrical", 3).explanation)

    section("3. HVAC rough-in slips 2 working days (it has float)")
    print(delay_impact(reno, "hvac", 2).explanation)

    section("4. What if drywall takes 4 days instead of 6 (bigger crew)?")
    print(what_if(reno, {"drywall": 4}).explanation)

    section("5. Projected from progress as of Mon Nov 2: electrical should be done but is only 60% complete")
    projected = analyze(reno.model_copy(update={"as_of": date(2026, 11, 2)}))
    print_schedule(projected)

    section("6. Office fit-out: when does the long-lead glazing become critical?")
    fitout = load_example("office_fitout")
    base = analyze(fitout)
    glazing = next(t for t in base.tasks if t.id == "glazing")
    print(f"Glazing has {glazing.total_float} working days of float.")
    print(delay_impact(fitout, "glazing", glazing.total_float + 2).explanation)

    section("7. An invalid schedule")
    try:
        analyze(load_example("circular_dependency"))
    except ScheduleError as e:
        for issue in e.issues:
            print(issue.message)


if __name__ == "__main__":
    main()
