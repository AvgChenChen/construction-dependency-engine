"""Schedules at the date boundary must fail as input errors, not server errors."""

from datetime import date

import pytest
from fastapi.testclient import TestClient

from dependency_engine.api import app
from dependency_engine.cpm import ScheduleError, analyze
from dependency_engine.models import ScheduleIn


def boundary_schedule(**overrides):
    return {
        "project_id": "date-boundary",
        "start_date": "9999-12-31",
        "tasks": [{"id": "a", "name": "Final task", "duration_days": 2}],
        **overrides,
    }


@pytest.mark.parametrize(
    "overrides",
    [
        {},
        {"calendar": {"holidays": ["9999-12-31"]}},
        {"start_date": "9999-12-30", "as_of": "9999-12-31", "calendar": {"workdays": [3]}},
    ],
)
def test_unrepresentable_calendar_dates_are_schedule_errors(overrides):
    with pytest.raises(ScheduleError) as error:
        analyze(ScheduleIn.model_validate(boundary_schedule(**overrides)))
    assert error.value.issues[0].type == "calendar_out_of_range"


@pytest.mark.parametrize("endpoint", ["analyze", "chart", "delay-impact", "what-if"])
def test_calendar_overflow_returns_structured_422(endpoint):
    schedule = boundary_schedule()
    body = schedule
    if endpoint == "delay-impact":
        body = {"schedule": schedule, "task_id": "a", "delay_days": 1}
    elif endpoint == "what-if":
        body = {"schedule": schedule, "duration_changes": {"a": 3}}
    response = TestClient(app).post(f"/v1/schedules/{endpoint}", json=body)
    assert response.status_code == 422
    assert response.json()["error"] == "invalid_schedule"
    assert response.json()["issues"][0]["type"] == "calendar_out_of_range"


def test_last_representable_workday_is_still_valid():
    schedule = boundary_schedule(tasks=[{"id": "a", "name": "Final task", "duration_days": 1}])
    assert analyze(ScheduleIn.model_validate(schedule)).projected_finish == date.max


@pytest.mark.parametrize("endpoint", ["delay-impact", "what-if"])
def test_a_valid_baseline_can_overflow_after_a_change(endpoint):
    schedule = boundary_schedule(tasks=[{"id": "a", "name": "Final task", "duration_days": 1}])
    if endpoint == "delay-impact":
        body = {"schedule": schedule, "task_id": "a", "delay_days": 1}
    else:
        body = {"schedule": schedule, "duration_changes": {"a": 2}}
    response = TestClient(app).post(f"/v1/schedules/{endpoint}", json=body)
    assert response.status_code == 422
    assert response.json()["issues"][0]["type"] == "calendar_out_of_range"
