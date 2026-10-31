"""Graph algorithms over the task list, written by hand (no NetworkX at runtime).

Edges point from a task to the tasks it depends on ("Drywall depends on Electrical").
All functions are O(V + E). Ties are broken by input order so results are deterministic.
"""

from __future__ import annotations

import heapq
from collections import deque
from collections.abc import Sequence

from .models import Issue, TaskIn


class CycleError(Exception):
    def __init__(self, cycle: list[str]):
        super().__init__(" -> ".join(cycle))
        self.cycle = cycle


def predecessors(tasks: Sequence[TaskIn]) -> dict[str, list[str]]:
    # dict.fromkeys de-duplicates while keeping order.
    return {t.id: list(dict.fromkeys(t.depends_on)) for t in tasks}


def successors(tasks: Sequence[TaskIn]) -> dict[str, list[str]]:
    succ: dict[str, list[str]] = {t.id: [] for t in tasks}
    for t in tasks:
        for p in dict.fromkeys(t.depends_on):
            if p in succ:
                succ[p].append(t.id)
    return succ


def structural_issues(tasks: Sequence[TaskIn]) -> list[Issue]:
    """Duplicate ids, self-dependencies, and references to tasks that don't exist."""
    issues: list[Issue] = []
    seen: set[str] = set()
    for t in tasks:
        if t.id in seen:
            issues.append(Issue(type="duplicate_id", message=f"Task id '{t.id}' is used more than once.", task_ids=[t.id]))
        seen.add(t.id)
    for t in tasks:
        for dep in dict.fromkeys(t.depends_on):
            if dep == t.id:
                issues.append(Issue(type="self_dependency", message=f"'{t.name}' depends on itself.", task_ids=[t.id]))
            elif dep not in seen:
                issues.append(
                    Issue(
                        type="unknown_dependency",
                        message=f"'{t.name}' depends on '{dep}', which isn't in this schedule.",
                        task_ids=[t.id, dep],
                    )
                )
    return issues


def find_cycle(tasks: Sequence[TaskIn]) -> list[str] | None:
    """Return one cycle as [a, b, ..., a] (a waits on b waits on ... a), or None.

    Iterative three-colour DFS: WHITE = unvisited, GREY = on the current path,
    BLACK = finished. Meeting a GREY node means we've walked back onto our own path.
    """
    preds = predecessors(tasks)
    white, grey, black = 0, 1, 2
    colour = {t.id: white for t in tasks}
    for root in (t.id for t in tasks):
        if colour[root] != white:
            continue
        path: list[str] = []
        stack: list[tuple[str, int]] = [(root, 0)]  # (node, index of next predecessor to explore)
        while stack:
            node, i = stack[-1]
            if i == 0:
                colour[node] = grey
                path.append(node)
            nexts = [p for p in preds.get(node, []) if p in colour]
            if i < len(nexts):
                stack[-1] = (node, i + 1)
                nxt = nexts[i]
                if colour[nxt] == grey:
                    return path[path.index(nxt) :] + [nxt]
                if colour[nxt] == white:
                    stack.append((nxt, 0))
            else:
                colour[node] = black
                path.pop()
                stack.pop()
    return None


def topological_order(tasks: Sequence[TaskIn]) -> list[str]:
    """Kahn's algorithm: repeatedly take a task whose predecessors are all placed.

    A min-heap keyed on input position makes the order deterministic.
    Raises CycleError if some tasks can never be placed.
    """
    index = {t.id: i for i, t in enumerate(tasks)}
    preds = predecessors(tasks)
    succ = successors(tasks)
    remaining = {tid: sum(1 for p in ps if p in index) for tid, ps in preds.items()}
    ready = [(index[tid], tid) for tid, n in remaining.items() if n == 0]
    heapq.heapify(ready)
    order: list[str] = []
    while ready:
        _, tid = heapq.heappop(ready)
        order.append(tid)
        for s in succ[tid]:
            remaining[s] -= 1
            if remaining[s] == 0:
                heapq.heappush(ready, (index[s], s))
    if len(order) != len(tasks):
        raise CycleError(find_cycle(tasks) or [])
    return order


def descendants(tasks: Sequence[TaskIn], task_id: str) -> list[str]:
    """Every task that directly or indirectly waits on task_id (breadth-first)."""
    succ = successors(tasks)
    seen: set[str] = set()
    queue = deque(succ.get(task_id, []))
    out: list[str] = []
    while queue:
        tid = queue.popleft()
        if tid in seen:
            continue
        seen.add(tid)
        out.append(tid)
        queue.extend(succ[tid])
    return out
