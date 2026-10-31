"""Fictional example schedules used by the demo, the API, and the tests."""

from __future__ import annotations

import json
from pathlib import Path

from ..models import ScheduleIn

_DIR = Path(__file__).parent

EXAMPLES: dict[str, tuple[str, str]] = {
    "residential_renovation": (
        "Two-storey renovation; electrical rough-in gates drywall (holiday on the start date)",
        "residential_renovation.json",
    ),
    "textbook_cpm": ("Six-activity CPM example with a hand-computed answer", "textbook_cpm.json"),
    "office_fitout": ("Office fit-out with a long-lead glazing package running in parallel", "office_fitout.json"),
    "circular_dependency": ("Invalid: electrical → drywall → insulation → electrical", "circular_dependency.json"),
    "ops_export_maple_ridge": (
        "Unmodified schedule export from construction-ops-platform's seed data (ScheduleContract v1, as_of set)",
        "ops_export_maple_ridge.json",
    ),
}


def load_example(name: str) -> ScheduleIn:
    if name not in EXAMPLES:
        raise KeyError(name)
    return ScheduleIn.model_validate(json.loads((_DIR / EXAMPLES[name][1]).read_text()))
