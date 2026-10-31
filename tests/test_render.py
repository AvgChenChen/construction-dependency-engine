from fastapi.testclient import TestClient

from dependency_engine.api import app
from dependency_engine.cpm import analyze
from dependency_engine.examples import load_example
from dependency_engine.render import render_svg

from .helpers import schedule


def test_renders_every_task_and_the_finish_date():
    s = load_example("residential_renovation")
    svg = render_svg(s, analyze(s))
    assert svg.startswith("<svg") and svg.endswith("</svg>")
    for t in s.tasks:
        assert t.name.replace("&", "&amp;") in svg
    assert "finish Fri Nov 27, 2026" in svg


def test_task_names_are_escaped():
    s = schedule([{"id": "a", "name": '<script>alert("x")</script>', "duration_days": 2}])
    svg = render_svg(s, analyze(s))
    assert "<script>" not in svg and "&lt;script&gt;" in svg


def test_chart_endpoint_returns_svg():
    r = TestClient(app).post("/v1/schedules/chart", json=load_example("textbook_cpm").model_dump(mode="json"))
    assert r.status_code == 200 and r.headers["content-type"].startswith("image/svg+xml")
    assert r.text.startswith("<svg")
