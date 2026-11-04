"""Contract 1.1: a dependency is either a task id or {"id": ..., "lag_days": ...}."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from dependency_engine.examples import EXAMPLES, load_example
from dependency_engine.models import Dependency, TaskIn


def task(*deps):
    return TaskIn.model_validate({"id": "paint", "name": "Paint", "duration_days": 3, "depends_on": list(deps)})


def test_plain_ids_still_validate_and_mean_zero_lag():
    t = task("drywall", "electrical")
    assert t.depends_on == ["drywall", "electrical"]
    assert t.dependencies == [Dependency(id="drywall"), Dependency(id="electrical")]
    assert all(d.lag_days == 0 for d in t.dependencies)


def test_object_form_carries_a_lag():
    t = task({"id": "drywall", "lag_days": 2})
    assert t.depends_on == ["drywall"]
    assert t.dependencies == [Dependency(id="drywall", lag_days=2)]


def test_both_forms_can_be_mixed_and_lag_defaults_to_zero():
    t = task("electrical", {"id": "drywall", "lag_days": 2}, {"id": "plumbing"})
    assert t.depends_on == ["electrical", "drywall", "plumbing"]
    assert [d.lag_days for d in t.dependencies] == [0, 2, 0]


@pytest.mark.parametrize("lag", [0, 365])
def test_lag_bounds_are_inclusive(lag):
    assert task({"id": "drywall", "lag_days": lag}).dependencies[0].lag_days == lag


@pytest.mark.parametrize(
    "dep",
    [
        {"id": "drywall", "lag_days": -1},
        {"id": "drywall", "lag_days": 366},
        {"id": "drywall", "lag_days": 1.5},
        {"id": "drywall", "lag_days": "two"},
        {"lag_days": 2},
        {"id": "", "lag_days": 2},
        {"id": "drywall", "lag_days": 2, "type": "start_to_start"},  # an unsupported relationship is not ignored
        "",
        7,
    ],
)
def test_bad_dependencies_are_rejected(dep):
    with pytest.raises(ValidationError) as e:
        task(dep)
    assert all(err["loc"][0] == "depends_on" for err in e.value.errors())


def test_repeated_predecessor_keeps_the_longest_lag():
    """Each entry is a constraint "start >= finish + lag"; together, only the largest lag binds."""
    t = task("drywall", {"id": "drywall", "lag_days": 2}, {"id": "drywall", "lag_days": 1})
    assert t.dependencies == [Dependency(id="drywall", lag_days=2)]
    assert t.depends_on == ["drywall"]


def test_serialises_back_to_the_form_it_came_in():
    """Zero-lag dependencies dump as plain ids, so contract 1.0 output is byte-for-byte unchanged."""
    t = task("electrical", {"id": "drywall", "lag_days": 2}, {"id": "plumbing", "lag_days": 0})
    assert t.model_dump(mode="json")["depends_on"] == ["electrical", {"id": "drywall", "lag_days": 2}, "plumbing"]
    assert "dependencies" not in t.model_dump(mode="json", by_alias=True)
    assert TaskIn.model_validate(t.model_dump(mode="json")) == t


@pytest.mark.parametrize("name", EXAMPLES)
def test_bundled_examples_serialise_exactly_as_on_disk(name):
    on_disk = json.loads((Path(__file__).resolve().parents[1] / "src/dependency_engine/examples" / EXAMPLES[name][1]).read_text())
    dumped = load_example(name).model_dump(mode="json", by_alias=True)
    assert [t["depends_on"] for t in dumped["tasks"]] == [t.get("depends_on", []) for t in on_disk["tasks"]]
