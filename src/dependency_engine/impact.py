"""Delay propagation and what-if analysis, with plain-English explanations.

Both work the same way: analyse the schedule, change it, analyse again, and diff.
Re-running CPM is O(V + E), so recomputing from scratch is simpler and safer than
patching dates incrementally, and fast enough for thousands of tasks.
"""

from __future__ import annotations

from datetime import date

from .cpm import analyze
from .graph import descendants
from .models import AffectedTask, DelayImpact, ScheduleIn, ScheduleResult, TaskStatus, WhatIfResult


class UnknownTask(KeyError):
    pass


def fmt(d: date | None) -> str:
    return d.strftime("%a %b %-d, %Y") if d else "n/a"


def _days(n: int) -> str:
    return f"{n} working day{'s' if abs(n) != 1 else ''}"


def _diff(before: ScheduleResult, after: ScheduleResult, ids: list[str]) -> list[AffectedTask]:
    b = {t.id: t for t in before.tasks}
    a = {t.id: t for t in after.tasks}
    out = []
    for tid in ids:
        tb, ta = b[tid], a[tid]
        if ta.early_start != tb.early_start or ta.early_finish != tb.early_finish:
            out.append(
                AffectedTask(
                    id=tid,
                    name=ta.name,
                    start_shift_days=ta.early_start - tb.early_start,
                    finish_shift_days=ta.early_finish - tb.early_finish,
                    old_start=tb.start_date or before.start_date,
                    new_start=ta.start_date or after.start_date,
                    float_before=tb.total_float,
                    float_after=ta.total_float,
                )
            )
    return out


def delay_impact(schedule: ScheduleIn, task_id: str, delay_days: int) -> DelayImpact:
    task = next((t for t in schedule.tasks if t.id == task_id), None)
    if task is None:
        raise UnknownTask(task_id)
    if schedule.as_of is not None and task.status is TaskStatus.complete:
        raise ValueError(f"'{task.name}' is already complete, so it can't be delayed.")

    before = analyze(schedule)
    modified = schedule.model_copy(deep=True)
    for t in modified.tasks:
        if t.id == task_id:
            t.delay_days += delay_days
    after = analyze(modified)

    downstream = descendants(schedule.tasks, task_id)
    affected = _diff(before, after, downstream)
    affected_ids = {a.id for a in affected}
    task_float = next(t.total_float for t in before.tasks if t.id == task_id)
    finish_shift = after.project_duration_days - before.project_duration_days

    return DelayImpact(
        task_id=task_id,
        task_name=task.name,
        delay_days=delay_days,
        task_float_before=task_float,
        absorbed_by_float=delay_days - finish_shift,
        downstream_tasks=len(downstream),
        affected=affected,
        unaffected_downstream=[t for t in downstream if t not in affected_ids],
        finish_before=before.projected_finish,
        finish_after=after.projected_finish,
        finish_shift_days=finish_shift,
        critical_path_before=before.critical_path_names,
        critical_path_after=after.critical_path_names,
        explanation=explain_delay(task.name, delay_days, task_float, affected, len(downstream), before, after),
    )


def explain_delay(name, delay, task_float, affected, n_downstream, before: ScheduleResult, after: ScheduleResult) -> str:
    shift = after.project_duration_days - before.project_duration_days
    parts = [f"'{name}' slips {_days(delay)}."]
    if task_float == 0:
        parts.append("It is on the critical path (0 days of float), so every working day of delay passes straight through.")
    else:
        parts.append(f"It had {_days(task_float)} of float before this change.")

    if n_downstream == 0:
        parts.append("No other task depends on it.")
    elif not affected:
        parts.append(f"None of the {n_downstream} downstream tasks move, because the float absorbs the whole delay.")
    else:
        moved = ", ".join(f"'{a.name}' (+{a.start_shift_days})" for a in affected[:6])
        more = f" and {len(affected) - 6} more" if len(affected) > 6 else ""
        parts.append(f"{len(affected)} of {n_downstream} downstream tasks start later: {moved}{more}.")

    if shift == 0:
        parts.append(f"Projected completion is unchanged at {fmt(before.projected_finish)}.")
    else:
        absorbed = delay - shift
        parts.append(
            f"Projected completion moves from {fmt(before.projected_finish)} to {fmt(after.projected_finish)} "
            f"(+{_days(shift)})" + (f"; float absorbed {_days(absorbed)} of the delay." if absorbed > 0 else ".")
        )
    crit_before = {t.id for t in before.tasks if t.critical}
    crit_after = {t.id for t in after.tasks if t.critical}
    newly = [t.name for t in after.tasks if t.id in crit_after - crit_before]
    if newly and crit_before <= crit_after:
        parts.append(
            "With its float used up, "
            + ", ".join(f"'{n}'" for n in newly)
            + (" is" if len(newly) == 1 else " are")
            + " now also critical: any further slip moves completion."
        )
    elif before.critical_path != after.critical_path:
        parts.append("The critical path changed: it now runs " + " → ".join(after.critical_path_names) + ".")
    return " ".join(parts)


def what_if(schedule: ScheduleIn, duration_changes: dict[str, int]) -> WhatIfResult:
    ids = {t.id for t in schedule.tasks}
    unknown = [k for k in duration_changes if k not in ids]
    if unknown:
        raise UnknownTask(", ".join(unknown))
    before = analyze(schedule)
    modified = schedule.model_copy(deep=True)
    for t in modified.tasks:
        if t.id in duration_changes:
            t.duration_days = duration_changes[t.id]
    after = analyze(modified)
    changed = _diff(before, after, [t.id for t in schedule.tasks])
    shift = after.project_duration_days - before.project_duration_days
    names = {t.id: t.name for t in schedule.tasks}
    edits = ", ".join(
        f"'{names[k]}' {next(t.duration_days for t in schedule.tasks if t.id == k)}→{v} days" for k, v in duration_changes.items()
    )
    if shift == 0:
        outcome = f"projected completion stays {fmt(before.projected_finish)}"
    else:
        direction = "later" if shift > 0 else "earlier"
        outcome = (
            f"projected completion moves {_days(abs(shift))} {direction}, "
            f"from {fmt(before.projected_finish)} to {fmt(after.projected_finish)}"
        )
    explanation = f"With {edits}, {outcome}. {len(changed)} task(s) change dates."
    if shift < 0 < len(duration_changes) and before.critical_path != after.critical_path:
        explanation += " The critical path changed, so further cuts on the old path would save less."
    return WhatIfResult(
        finish_before=before.projected_finish,
        finish_after=after.projected_finish,
        finish_shift_days=shift,
        changed_tasks=changed,
        critical_path_before=before.critical_path_names,
        critical_path_after=after.critical_path_names,
        explanation=explanation,
    )
