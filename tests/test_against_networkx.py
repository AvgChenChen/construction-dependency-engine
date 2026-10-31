"""Cross-check the hand-written algorithms against NetworkX on random graphs.

NetworkX is an independent reference implementation; it is a test-only dependency.
"""

import random

import networkx as nx

from dependency_engine.cpm import analyze
from dependency_engine.graph import find_cycle, topological_order

from .helpers import by_id, schedule


def random_dag(rng: random.Random, n: int, p: float):
    # Edges only go from lower to higher index, which guarantees no cycles.
    tasks = []
    for i in range(n):
        deps = [f"t{j}" for j in range(i) if rng.random() < p]
        tasks.append((f"t{i}", rng.randint(0, 10), deps))
    rng.shuffle(tasks)  # input order shouldn't matter
    return tasks


def longest_path_networkx(tasks) -> int:
    g = nx.DiGraph()
    g.add_node("END")
    for tid, dur, deps in tasks:
        g.add_edge(tid, "END", weight=dur)
        for d in deps:
            g.add_edge(d, tid, weight=next(x[1] for x in tasks if x[0] == d))
    return nx.dag_longest_path_length(g, weight="weight")


def test_project_duration_matches_networkx_longest_path():
    rng = random.Random(20261031)
    for _ in range(300):
        tasks = random_dag(rng, rng.randint(1, 40), rng.uniform(0.02, 0.4))
        r = analyze(schedule(tasks))
        assert r.project_duration_days == longest_path_networkx(tasks)


def test_cpm_invariants_on_random_dags():
    rng = random.Random(7)
    for _ in range(200):
        tasks = random_dag(rng, rng.randint(2, 30), 0.2)
        r = analyze(schedule(tasks))
        t = by_id(r)
        deps = {tid: d for tid, _, d in tasks}
        for tid, res in t.items():
            assert res.total_float >= 0 and 0 <= res.free_float <= res.total_float
            for d in deps[tid]:
                assert t[d].early_finish <= res.early_start  # finish-to-start respected
        # The reported critical path is a real chain whose durations add up to the project length.
        path = r.critical_path
        assert sum(t[p].remaining_days for p in path) == r.project_duration_days
        for a, b in zip(path, path[1:], strict=False):
            assert a in deps[b]


def test_cycle_detection_agrees_with_networkx():
    rng = random.Random(99)
    for _ in range(300):
        n = rng.randint(2, 15)
        tasks = [(f"t{i}", 1, [f"t{j}" for j in range(n) if j != i and rng.random() < 0.12]) for i in range(n)]
        g = nx.DiGraph((d, tid) for tid, _, deps in tasks for d in deps)
        g.add_nodes_from(t[0] for t in tasks)
        s = schedule(tasks)
        cycle = find_cycle(s.tasks)
        assert (cycle is None) == nx.is_directed_acyclic_graph(g)
        if cycle is None:
            order = topological_order(s.tasks)
            pos = {tid: i for i, tid in enumerate(order)}
            assert all(pos[d] < pos[tid] for tid, _, deps in tasks for d in deps)
