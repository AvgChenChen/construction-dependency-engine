"""Render a schedule as an SVG bar chart (no dependencies, deterministic output).

    python -m dependency_engine.render residential_renovation docs/schedule.svg
    python -m dependency_engine.render residential_renovation docs/delay.svg --delay electrical:3

The x-axis is working days, so weekends and holidays take no space. Ticks show the
calendar date of every fifth working day. Colours follow docs/DESIGN.md.
Task names come from user input, so every piece of text is XML-escaped.
"""

from __future__ import annotations

import argparse
from html import escape
from pathlib import Path

from .calendar import WorkCalendar
from .cpm import analyze
from .examples import load_example
from .models import ScheduleIn, ScheduleResult

INK, MUTED, SUBTLE = "#1C2928", "#4A5856", "#5E6B69"
CANVAS, SURFACE, LINE = "#F7F6F2", "#E3E9E5", "#D6DDD8"
PRIMARY, ACCENT, DANGER, DONE = "#176B5B", "#D9A452", "#B42318", "#9DBFAF"

ROW, BAR, LABEL_W, PAD, HEAD = 30, 14, 250, 24, 64
FONT = "Inter, ui-sans-serif, system-ui, -apple-system, Segoe UI, sans-serif"


def _text(x: float, y: float, s: str, size: int = 12, fill: str = INK, weight: int = 400, anchor: str = "start") -> str:
    return (
        f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size}" font-weight="{weight}" fill="{fill}" '
        f'text-anchor="{anchor}">{escape(s)}</text>'
    )


def render_svg(
    schedule: ScheduleIn, result: ScheduleResult, before: ScheduleResult | None = None, title: str | None = None
) -> str:
    """Draw `result`. If `before` is given, its bars are drawn as outlines to show what moved."""
    cal = WorkCalendar(schedule.start_date, schedule.calendar)
    span = max(result.project_duration_days, before.project_duration_days if before else 0, 1)
    day_w = max(8.0, min(24.0, 640 / span))
    width = LABEL_W + span * day_w + PAD * 2
    height = HEAD + len(result.tasks) * ROW + 56
    old = {t.id: t for t in before.tasks} if before else {}
    x0 = LABEL_W + PAD

    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width:.0f}" height="{height}" viewBox="0 0 {width:.0f} {height}" '
        f'font-family="{FONT}" role="img" aria-label="{escape(title or "Schedule chart")}">',
        f'<rect width="100%" height="100%" fill="{CANVAS}"/>',
        _text(PAD, 28, title or (schedule.project_name or schedule.project_id), 15, INK, 600),
        _text(
            PAD, 46, f"{result.project_duration_days} working days · finish {result.projected_finish:%a %b %-d, %Y}", 12, MUTED
        ),
    ]
    for off in range(0, span + 1, 5):
        x = x0 + off * day_w
        out.append(f'<line x1="{x:.1f}" y1="{HEAD - 6}" x2="{x:.1f}" y2="{height - 44}" stroke="{LINE}" stroke-width="1"/>')
        out.append(_text(x + 3, HEAD - 10, f"{cal.date_for_offset(off):%b %-d}", 10, SUBTLE))

    for i, t in enumerate(result.tasks):
        y = HEAD + i * ROW
        if i % 2 == 0:
            out.append(f'<rect x="0" y="{y}" width="{width:.0f}" height="{ROW}" fill="#FFFFFF" fill-opacity="0.55"/>')
        out.append(_text(PAD, y + ROW / 2 + 4, t.name[:34], 12, INK if t.critical else MUTED, 500 if t.critical else 400))
        by = y + (ROW - BAR) / 2
        if t.id in old:
            o = old[t.id]
            if (o.early_start, o.early_finish) != (t.early_start, t.early_finish):
                ow = max((o.early_finish - o.early_start) * day_w, 3)
                out.append(
                    f'<rect x="{x0 + o.early_start * day_w:.1f}" y="{by:.1f}" width="{ow:.1f}" height="{BAR}" rx="3" '
                    f'fill="none" stroke="{SUBTLE}" stroke-dasharray="3 2"/>'
                )
        w = max((t.early_finish - t.early_start) * day_w, 3)
        moved = bool(old) and t.id in old and old[t.id].early_start != t.early_start
        if t.start_date is None:
            fill = DONE
        elif moved:
            fill = DANGER
        elif t.critical:
            fill = PRIMARY
        else:
            fill = "#8FA79F"
        out.append(
            f'<rect x="{x0 + t.early_start * day_w:.1f}" y="{by:.1f}" width="{w:.1f}" height="{BAR}" rx="3" fill="{fill}"/>'
        )
        if t.total_float > 0 and t.start_date is not None:
            fx1 = x0 + t.early_finish * day_w
            fx2 = x0 + t.late_finish * day_w
            out.append(
                f'<line x1="{fx1:.1f}" y1="{by + BAR / 2:.1f}" x2="{fx2:.1f}" y2="{by + BAR / 2:.1f}" stroke="{ACCENT}" stroke-width="2"/>'
            )
            out.append(
                f'<line x1="{fx2:.1f}" y1="{by + 2:.1f}" x2="{fx2:.1f}" y2="{by + BAR - 2:.1f}" stroke="{ACCENT}" stroke-width="2"/>'
            )

    ly = height - 22
    legend = [(PRIMARY, "Critical"), ("#8FA79F", "Has float"), (ACCENT, "Float (slack)"), (DONE, "Complete")]
    if before:
        legend.insert(0, (DANGER, "Moved"))
    lx = PAD
    for color, label in legend:
        out.append(f'<rect x="{lx}" y="{ly - 9}" width="14" height="10" rx="2" fill="{color}"/>')
        out.append(_text(lx + 20, ly, label, 11, MUTED))
        lx += 30 + len(label) * 6.5
    if before:
        out.append(
            f'<rect x="{lx}" y="{ly - 9}" width="14" height="10" rx="2" fill="none" stroke="{SUBTLE}" stroke-dasharray="3 2"/>'
        )
        out.append(_text(lx + 20, ly, "Before the change", 11, MUTED))
    out.append("</svg>")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render an example schedule as SVG.")
    parser.add_argument("example")
    parser.add_argument("out")
    parser.add_argument("--delay", help="task_id:days, to show a delay against the baseline")
    args = parser.parse_args(argv)

    schedule = load_example(args.example)
    base = analyze(schedule)
    if args.delay:
        task_id, days = args.delay.split(":")
        task = next(t for t in schedule.tasks if t.id == task_id)
        changed = schedule.model_copy(deep=True)
        next(t for t in changed.tasks if t.id == task_id).delay_days += int(days)
        after = analyze(changed)
        title = f"{schedule.project_name}: {task.name} slips {days} working days"
        svg = render_svg(changed, after, before=base, title=title)
    else:
        svg = render_svg(schedule, base)
    Path(args.out).write_text(svg)
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
