import json
from pathlib import Path

from fastapi.testclient import TestClient

from dependency_engine.api import app

client = TestClient(app)
EXAMPLES = Path(__file__).resolve().parents[1] / "src" / "dependency_engine" / "examples"


def example(name):
    return client.get(f"/v1/examples/{name}").json()


def test_health_and_examples():
    assert client.get("/health").json()["status"] == "ok"
    assert set(client.get("/v1/examples").json()) == {
        "residential_renovation",
        "textbook_cpm",
        "office_fitout",
        "circular_dependency",
        "ops_export_maple_ridge",
    }
    assert client.get("/v1/examples/nope").status_code == 404


def test_analyze_returns_dates_and_critical_path():
    r = client.post("/v1/schedules/analyze", json=example("residential_renovation"))
    assert r.status_code == 200
    body = r.json()
    assert body["projected_finish"] == "2026-11-27" and body["project_duration_days"] == 34
    assert body["assumptions"]


def test_cycles_are_422_on_analyze_and_reported_on_validate():
    cyclic = example("circular_dependency")
    r = client.post("/v1/schedules/analyze", json=cyclic)
    assert r.status_code == 422 and r.json()["issues"][0]["type"] == "cycle"
    v = client.post("/v1/schedules/validate", json=cyclic).json()
    assert v["valid"] is False and "Circular dependency" in v["issues"][0]["message"]
    assert client.post("/v1/schedules/validate", json=example("textbook_cpm")).json() == {
        "valid": True,
        "issues": [],
        "warnings": [],
    }


def test_delay_impact_endpoint():
    body = {"schedule": example("residential_renovation"), "task_id": "electrical", "delay_days": 3}
    r = client.post("/v1/schedules/delay-impact", json=body).json()
    assert r["finish_after"] == "2026-12-02" and r["finish_shift_days"] == 3
    assert client.post("/v1/schedules/delay-impact", json={**body, "task_id": "nope"}).status_code == 404
    assert client.post("/v1/schedules/delay-impact", json={**body, "delay_days": 0}).status_code == 422


def test_what_if_endpoint():
    body = {"schedule": example("residential_renovation"), "duration_changes": {"drywall": 4}}
    assert client.post("/v1/schedules/what-if", json=body).json()["finish_shift_days"] == -2
    assert client.post("/v1/schedules/what-if", json={**body, "duration_changes": {"x": 1}}).status_code == 404
    assert client.post("/v1/schedules/what-if", json={**body, "duration_changes": {"drywall": -1}}).status_code == 422


def test_input_limits_and_unknown_fields():
    s = example("textbook_cpm")
    s["tasks"][0]["duration_days"] = -1
    assert client.post("/v1/schedules/analyze", json=s).status_code == 422
    big = {
        "project_id": "x",
        "start_date": "2026-11-02",
        "tasks": [{"id": str(i), "name": "t", "duration_days": 1} for i in range(2001)],
    }
    assert client.post("/v1/schedules/analyze", json=big).status_code == 422
    s = example("textbook_cpm")
    s["unexpected_field_from_a_newer_client"] = True  # ignored for forward compatibility
    s["tasks"][0]["planned_start"] = "2026-11-02"
    assert client.post("/v1/schedules/analyze", json=s).status_code == 200


def test_examples_on_disk_are_valid_json():
    for f in EXAMPLES.glob("*.json"):
        json.loads(f.read_text())


def lagged(lag):
    s = example("textbook_cpm")
    task = next(t for t in s["tasks"] if t["depends_on"])
    task["depends_on"] = [{"id": d, "lag_days": lag} for d in task["depends_on"]]
    return s, task["id"]


def test_zero_lag_objects_give_the_same_schedule_as_plain_ids():
    plain = client.post("/v1/schedules/analyze", json=example("textbook_cpm"))
    objects = client.post("/v1/schedules/analyze", json=lagged(0)[0])
    assert plain.status_code == objects.status_code == 200
    assert plain.json() == objects.json()


def test_a_nonzero_lag_is_refused_until_the_engine_applies_it():
    """Contract 1.1 accepts lags, but the CPM passes don't apply them yet. A silently ignored lag
    would give finish dates that are too early, so the engine says so instead."""
    schedule, task_id = lagged(2)
    r = client.post("/v1/schedules/analyze", json=schedule)
    assert r.status_code == 422
    issue = r.json()["issues"][0]
    assert issue["type"] == "lag_not_supported" and issue["task_ids"][0] == task_id
    v = client.post("/v1/schedules/validate", json=schedule).json()
    assert v["valid"] is False and v["issues"][0]["type"] == "lag_not_supported"


def test_out_of_range_lag_is_a_request_validation_error():
    schedule, _ = lagged(366)
    assert client.post("/v1/schedules/analyze", json=schedule).status_code == 422
    assert client.post("/v1/schedules/validate", json=schedule).status_code == 422
