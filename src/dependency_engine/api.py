"""REST API. Run with: uvicorn dependency_engine.api:app   (interactive docs at /docs)"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, Response

from . import __version__
from .cpm import ScheduleError, analyze, validate
from .examples import EXAMPLES, load_example
from .impact import UnknownTask, delay_impact, what_if
from .models import DelayImpact, DelayRequest, ScheduleIn, ScheduleResult, ValidationReport, WhatIfRequest, WhatIfResult
from .render import render_svg

app = FastAPI(
    title="Construction Dependency Engine (prototype)",
    version=__version__,
    description="Construction schedule analysis: cycle detection, critical path, delay propagation, what-if. "
    "Stateless: every request carries the full schedule.",
)


@app.exception_handler(ScheduleError)
async def _schedule_error(_: Request, exc: ScheduleError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={"error": "invalid_schedule", "issues": [i.model_dump() for i in exc.issues]},
    )


@app.get("/health", tags=["System"])
def health() -> dict[str, str]:
    return {"status": "ok", "version": __version__}


@app.get("/v1/examples", tags=["Examples"])
def list_examples() -> dict[str, str]:
    return {name: desc for name, (desc, _) in EXAMPLES.items()}


@app.get("/v1/examples/{name}", response_model=ScheduleIn, tags=["Examples"])
def get_example(name: str) -> ScheduleIn:
    try:
        return load_example(name)
    except KeyError:
        raise HTTPException(status_code=404, detail="Unknown example") from None


@app.post("/v1/schedules/validate", response_model=ValidationReport, tags=["Schedules"])
def validate_schedule(schedule: ScheduleIn) -> ValidationReport:
    """Always 200. Lists duplicate ids, unknown or self dependencies, and cycles in plain English."""
    issues = validate(schedule)
    return ValidationReport(valid=not issues, issues=issues)


@app.post("/v1/schedules/analyze", response_model=ScheduleResult, tags=["Schedules"])
def analyze_schedule(schedule: ScheduleIn) -> ScheduleResult:
    """Critical path, float, and dates. Set `as_of` to project remaining work from current progress."""
    return analyze(schedule)


@app.post("/v1/schedules/delay-impact", response_model=DelayImpact, tags=["Schedules"])
def schedule_delay_impact(body: DelayRequest) -> DelayImpact:
    """What happens if one task slips by N working days?"""
    try:
        return delay_impact(body.schedule, body.task_id, body.delay_days)
    except UnknownTask:
        raise HTTPException(status_code=404, detail=f"Task '{body.task_id}' is not in the schedule") from None
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e)) from None


@app.post("/v1/schedules/what-if", response_model=WhatIfResult, tags=["Schedules"])
def schedule_what_if(body: WhatIfRequest) -> WhatIfResult:
    """Recalculate the projected completion with new durations for some tasks."""
    try:
        return what_if(body.schedule, body.duration_changes)
    except UnknownTask as e:
        raise HTTPException(status_code=404, detail=f"Unknown task id(s): {e.args[0]}") from None


@app.post("/v1/schedules/chart", response_class=Response, responses={200: {"content": {"image/svg+xml": {}}}}, tags=["Schedules"])
def schedule_chart(schedule: ScheduleIn) -> Response:
    """The analysed schedule as an SVG bar chart: critical tasks, float, and dates."""
    svg = render_svg(schedule, analyze(schedule))
    return Response(content=svg, media_type="image/svg+xml", headers={"X-Content-Type-Options": "nosniff"})
