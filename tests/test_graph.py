import pytest

from dependency_engine.graph import CycleError, descendants, find_cycle, structural_issues, topological_order

from .helpers import schedule


def test_structural_issues():
    s = schedule([("a", 1), ("b", 1, ["a", "ghost"]), ("c", 1, ["c"])])
    s.tasks.append(s.tasks[0].model_copy())
    types = sorted(i.type for i in structural_issues(s.tasks))
    assert types == ["duplicate_id", "self_dependency", "unknown_dependency"]


def test_find_cycle_returns_the_loop_in_order():
    s = schedule(
        [
            ("electrical", 5, ["drywall"]),
            ("drywall", 6, ["insulation"]),
            ("insulation", 2, ["electrical"]),
            ("paint", 4, ["drywall"]),
        ]
    )
    cycle = find_cycle(s.tasks)
    assert cycle[0] == cycle[-1]
    assert set(cycle) == {"electrical", "drywall", "insulation"}
    deps = {t.id: t.depends_on for t in s.tasks}
    for a, b in zip(cycle, cycle[1:], strict=False):
        assert b in deps[a]  # each step is a real "waits on" edge


def test_two_task_cycle_and_acyclic_graph():
    assert find_cycle(schedule([("a", 1, ["b"]), ("b", 1, ["a"])]).tasks) in (["a", "b", "a"], ["b", "a", "b"])
    assert find_cycle(schedule([("a", 1), ("b", 1, ["a"]), ("c", 1, ["a", "b"])]).tasks) is None


def test_topological_order_is_valid_and_deterministic():
    s = schedule([("d", 1, ["b", "c"]), ("b", 1, ["a"]), ("c", 1, ["a"]), ("a", 1)])
    order = topological_order(s.tasks)
    assert order == ["a", "b", "c", "d"]  # ties broken by input order (b before c)
    with pytest.raises(CycleError):
        topological_order(schedule([("a", 1, ["b"]), ("b", 1, ["a"])]).tasks)


def test_descendants_breadth_first():
    s = schedule([("a", 1), ("b", 1, ["a"]), ("c", 1, ["b"]), ("d", 1, ["a"]), ("e", 1)])
    assert descendants(s.tasks, "a") == ["b", "d", "c"]
    assert descendants(s.tasks, "e") == []
