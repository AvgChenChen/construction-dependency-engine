import random
from datetime import date

from dependency_engine.models import ScheduleIn


def schedule(tasks, start=date(2026, 11, 2), **kw) -> ScheduleIn:
    """tasks: list of (id, duration, [deps]) or dicts."""
    items = [
        t
        if isinstance(t, dict)
        else {"id": t[0], "name": t[0], "duration_days": t[1], "depends_on": list(t[2]) if len(t) > 2 else []}
        for t in tasks
    ]
    return ScheduleIn(project_id="test", start_date=start, tasks=items, **kw)


def by_id(result):
    return {t.id: t for t in result.tasks}


def random_dag(rng: random.Random, n: int, p: float):
    """A random acyclic schedule: n tasks of 0-10 days, each depending on earlier ones with probability p."""
    # Edges only go from lower to higher index, which guarantees no cycles.
    tasks = []
    for i in range(n):
        deps = [f"t{j}" for j in range(i) if rng.random() < p]
        tasks.append((f"t{i}", rng.randint(0, 10), deps))
    rng.shuffle(tasks)  # input order shouldn't matter
    return tasks
