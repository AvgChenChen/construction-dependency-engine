"""Input and output models. The input is "ScheduleContract v1" (docs/INTEGRATION.md).

Unknown fields are ignored so construction-ops-platform can add fields without breaking us.
"""

from __future__ import annotations

from datetime import date
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator

MAX_TASKS = 2000


class TaskStatus(StrEnum):
    not_started = "not_started"
    in_progress = "in_progress"
    blocked = "blocked"
    delayed = "delayed"
    complete = "complete"


class CalendarConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    workdays: list[int] = Field(default=[0, 1, 2, 3, 4], description="0 = Monday … 6 = Sunday")
    holidays: list[date] = Field(default_factory=list)

    @field_validator("workdays")
    @classmethod
    def _valid_workdays(cls, v: list[int]) -> list[int]:
        if not v or any(d < 0 or d > 6 for d in v):
            raise ValueError("workdays must be a non-empty list of integers 0..6")
        return sorted(set(v))


class TaskIn(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=200)
    trade: str | None = None
    duration_days: int = Field(ge=0, le=1000, description="Working days. 0 means a milestone.")
    status: TaskStatus = TaskStatus.not_started
    percent_complete: int = Field(default=0, ge=0, le=100)
    delay_days: int = Field(default=0, ge=0, le=1000, description="Known slip added to the remaining work.")
    depends_on: list[str] = Field(default_factory=list, description="Finish-to-start predecessors")


class ScheduleIn(BaseModel):
    model_config = ConfigDict(extra="ignore")

    contract_version: str = "1.0"
    project_id: str = Field(min_length=1, max_length=100)
    project_name: str | None = None
    start_date: date
    as_of: date | None = Field(default=None, description="If set, project remaining work from this date using progress.")
    calendar: CalendarConfig = Field(default_factory=CalendarConfig)
    tasks: list[TaskIn] = Field(min_length=1, max_length=MAX_TASKS)


class Issue(BaseModel):
    type: str  # duplicate_id | unknown_dependency | self_dependency | cycle | progress_inconsistency
    message: str
    task_ids: list[str]


class ValidationReport(BaseModel):
    valid: bool
    issues: list[Issue]
    warnings: list[Issue] = Field(default_factory=list)


class TaskResult(BaseModel):
    id: str
    name: str
    status: TaskStatus
    remaining_days: int
    early_start: int
    early_finish: int
    late_start: int
    late_finish: int
    total_float: int
    free_float: int
    critical: bool
    # None for tasks already complete in projected mode (their actual dates aren't in the input).
    start_date: date | None
    finish_date: date | None


class ScheduleResult(BaseModel):
    project_id: str
    mode: str  # "baseline" or "projected"
    start_date: date
    as_of: date | None
    project_duration_days: int
    projected_finish: date
    critical_path: list[str]
    critical_path_names: list[str]
    tasks: list[TaskResult]
    warnings: list[Issue] = Field(default_factory=list)
    assumptions: list[str]


class DelayRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schedule: ScheduleIn
    task_id: str
    delay_days: int = Field(ge=1, le=1000)


class AffectedTask(BaseModel):
    id: str
    name: str
    start_shift_days: int
    finish_shift_days: int
    old_start: date
    new_start: date
    float_before: int
    float_after: int


class DelayImpact(BaseModel):
    task_id: str
    task_name: str
    delay_days: int
    task_float_before: int
    absorbed_by_float: int
    downstream_tasks: int
    affected: list[AffectedTask]
    unaffected_downstream: list[str]
    finish_before: date
    finish_after: date
    finish_shift_days: int
    critical_path_before: list[str]
    critical_path_after: list[str]
    explanation: str


class WhatIfRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schedule: ScheduleIn
    duration_changes: dict[str, int] = Field(min_length=1, description="task_id → new duration in working days")

    @field_validator("duration_changes")
    @classmethod
    def _non_negative(cls, v: dict[str, int]) -> dict[str, int]:
        if any(d < 0 or d > 1000 for d in v.values()):
            raise ValueError("durations must be between 0 and 1000 working days")
        return v


class WhatIfResult(BaseModel):
    finish_before: date
    finish_after: date
    finish_shift_days: int
    changed_tasks: list[AffectedTask]
    critical_path_before: list[str]
    critical_path_after: list[str]
    explanation: str
