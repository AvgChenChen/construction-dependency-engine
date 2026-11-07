"""Critical Path Method (CPM) on a working-day calendar.

Forward pass:  ES(t) = max EF(p) over predecessors p   (0 if none)
               EF(t) = ES(t) + duration(t)
Backward pass: LF(t) = min LS(s) over successors s     (project end if none)
               LS(t) = LF(t) - duration(t)
Total float  = LS - ES   (how far a task can slip without moving the project end)
Free float   = min ES(successor) - EF   (how far it can slip without moving any successor)
Critical     = total float 0

Offsets are working days from the project start; EF is exclusive (a 1-day task at
offset 0 has EF = 1 and finishes on day 0).
"""

from __future__ import annotations

import math

from .calendar import CalendarRangeError, WorkCalendar
from .graph import find_cycle, predecessors, structural_issues, successors, topological_order
from .models import Issue, ScheduleIn, ScheduleResult, TaskIn, TaskResult, TaskStatus

# About 38 years of Monday-to-Friday work. Longer results are rejected instead of
# walking the calendar for minutes (or past year 9999). Input limits alone don't prevent
# this: 2000 chained tasks of 1000 days would be 2 million working days.
MAX_PROJECT_WORKING_DAYS = 10_000

ASSUMPTIONS = [
    "Durations are whole working days. Default working days are Monday to Friday, minus any listed holidays.",
    "All dependencies are finish-to-start with no lag: a task starts the working day after its last predecessor finishes.",
    "Unlimited resources: tasks with no dependency between them can run at the same time (no resource levelling).",
    "Tasks are scheduled as early as possible. planned_start values in the input are ignored.",
    "In projected mode (as_of set): complete tasks need no more time, in-progress tasks need "
    "ceil(duration x (1 - percent_complete/100)) days from as_of, and no remaining work starts before as_of.",
    "delay_days is added to a task's remaining duration.",
]


class ScheduleError(Exception):
    """The schedule can't be analysed (cycle, unknown dependency, duplicate id...)."""

    def __init__(self, issues: list[Issue]):
        super().__init__("; ".join(i.message for i in issues))
        self.issues = issues


def cycle_issue(cycle: list[str], names: dict[str, str]) -> Issue:
    readable = [names.get(c, c) for c in cycle]
    chain = ", which waits on ".join(f"'{n}'" for n in readable)
    return Issue(
        type="cycle",
        message=f"Circular dependency: {chain}. None of these tasks can ever start. Remove one of these dependencies.",
        task_ids=cycle[:-1],
    )


def lag_issues(schedule: ScheduleIn) -> list[Issue]:
    """Contract 1.1 accepts lags, but the forward and backward passes don't apply them yet.
    Ignoring a lag would report finish dates that are too early, so refuse instead."""
    names = {t.id: t.name for t in schedule.tasks}
    return [
        Issue(
            type="lag_not_supported",
            message=(
                f"'{t.name}' waits {d.lag_days} working day(s) after '{names.get(d.id, d.id)}' finishes. "
                "This engine version accepts lags but can't schedule them yet; send lag_days 0 for now."
            ),
            task_ids=[t.id, d.id],
        )
        for t in schedule.tasks
        for d in t.dependencies
        if d.lag_days > 0
    ]


def validate(schedule: ScheduleIn) -> list[Issue]:
    issues = structural_issues(schedule.tasks)
    if not issues:
        cycle = find_cycle(schedule.tasks)
        if cycle:
            issues.append(cycle_issue(cycle, {t.id: t.name for t in schedule.tasks}))
    return issues + lag_issues(schedule)


def remaining_duration(task: TaskIn, projected: bool) -> int:
    if not projected:
        return task.duration_days + task.delay_days
    if task.status is TaskStatus.complete:
        return 0
    if task.status is TaskStatus.in_progress or task.percent_complete > 0:
        return math.ceil(task.duration_days * (1 - task.percent_complete / 100)) + task.delay_days
    return task.duration_days + task.delay_days


def analyze(schedule: ScheduleIn) -> ScheduleResult:
    """Analyse a schedule, reporting unrepresentable dates as input errors."""
    try:
        return _analyze(schedule)
    except CalendarRangeError as exc:
        raise ScheduleError([Issue(type="calendar_out_of_range", message=str(exc), task_ids=[])]) from exc


def _analyze(schedule: ScheduleIn) -> ScheduleResult:
    issues = validate(schedule)
    if issues:
        raise ScheduleError(issues)

    tasks = schedule.tasks
    by_id = {t.id: t for t in tasks}
    index = {t.id: i for i, t in enumerate(tasks)}
    preds, succs = predecessors(tasks), successors(tasks)
    order = topological_order(tasks)
    cal = WorkCalendar(schedule.start_date, schedule.calendar)
    projected = schedule.as_of is not None
    status_offset = cal.offset_for_date(schedule.as_of) if schedule.as_of else 0
    warnings: list[Issue] = []

    dur = {t.id: remaining_duration(t, projected) for t in tasks}
    es: dict[str, int] = {}
    ef: dict[str, int] = {}
    for tid in order:
        start = max((ef[p] for p in preds[tid]), default=0)
        t = by_id[tid]
        if projected:
            if t.status is TaskStatus.complete:
                open_preds = [p for p in preds[tid] if by_id[p].status is not TaskStatus.complete]
                if open_preds:
                    warnings.append(
                        Issue(
                            type="progress_inconsistency",
                            message=f"'{t.name}' is marked complete but depends on unfinished "
                            + ", ".join(f"'{by_id[p].name}'" for p in open_preds)
                            + ".",
                            task_ids=[tid, *open_preds],
                        )
                    )
                start = min(start, status_offset)
            else:
                start = max(start, status_offset)
        es[tid] = start
        ef[tid] = start + dur[tid]

    project_end = max(ef.values())
    if project_end > MAX_PROJECT_WORKING_DAYS:
        raise ScheduleError(
            [
                Issue(
                    type="schedule_too_long",
                    message=f"The schedule runs {project_end} working days, over the {MAX_PROJECT_WORKING_DAYS}-day limit. "
                    "Check the durations for typos.",
                    task_ids=[],
                )
            ]
        )
    lf: dict[str, int] = {}
    ls: dict[str, int] = {}
    for tid in reversed(order):
        lf[tid] = min((ls[s] for s in succs[tid]), default=project_end)
        ls[tid] = lf[tid] - dur[tid]

    def is_critical(tid: str) -> bool:
        if projected and by_id[tid].status is TaskStatus.complete:
            return False
        return ls[tid] - es[tid] == 0

    results = []
    for t in tasks:
        tid = t.id
        done = projected and t.status is TaskStatus.complete
        results.append(
            TaskResult(
                id=tid,
                name=t.name,
                status=t.status,
                remaining_days=dur[tid],
                early_start=es[tid],
                early_finish=ef[tid],
                late_start=ls[tid],
                late_finish=lf[tid],
                total_float=ls[tid] - es[tid],
                free_float=min((es[s] for s in succs[tid]), default=project_end) - ef[tid],
                critical=is_critical(tid),
                start_date=None if done else cal.date_for_offset(es[tid]),
                finish_date=None if done else cal.date_for_offset(max(ef[tid] - 1, es[tid])),
            )
        )

    path = critical_path(order, preds, es, ef, project_end, index, is_critical)
    return ScheduleResult(
        project_id=schedule.project_id,
        mode="projected" if projected else "baseline",
        start_date=cal.start,
        as_of=schedule.as_of,
        project_duration_days=project_end,
        projected_finish=cal.date_for_offset(max(project_end - 1, 0)),
        critical_path=path,
        critical_path_names=[by_id[p].name for p in path],
        tasks=results,
        warnings=warnings,
        assumptions=ASSUMPTIONS,
    )


def critical_path(order, preds, es, ef, project_end, index, is_critical) -> list[str]:
    """Walk back from a critical task that ends the project, through critical predecessors
    whose finish meets the current task's start. If several paths tie, the earliest-listed
    task wins at each step, so the answer is deterministic.

    The walk starts from the *last* such task in topological order, so a zero-duration
    end milestone (which finishes at the same time as its predecessors) is included.
    """
    topo = {t: i for i, t in enumerate(order)}
    ends = sorted((-topo[t], index[t], t) for t in order if ef[t] == project_end and is_critical(t))
    if not ends:
        return []
    current = ends[0][2]
    path = [current]
    while True:
        candidates = sorted((index[p], p) for p in preds[current] if is_critical(p) and ef[p] == es[current])
        if not candidates:
            break
        current = candidates[0][1]
        path.append(current)
    return list(reversed(path))
