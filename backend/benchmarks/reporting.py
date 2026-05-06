"""Reporting: console tables, JSON output, baseline diff."""
from __future__ import annotations

import json
import platform
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from .fixtures import FixtureMeta
from .quality import QualityMetrics, SoftScores
from .verification import VerificationReport


# ── Result record ─────────────────────────────────────────────────────────


@dataclass
class ScenarioResult:
    scenario: str
    family: str
    fixture: FixtureMeta
    time_limit_seconds: float
    slot_minutes: int
    solver_status: str
    solver_label: str  # "flat" | "hierarchical" — which dispatch path was taken
    expected_status: str | None
    expected_match: bool
    quality: QualityMetrics
    soft_scores: SoftScores
    verification: VerificationReport
    diagnostics: tuple[str, ...] = ()
    suggestions: tuple[str, ...] = ()
    critical: bool = False  # solver claimed success but a hard-check failed
    notes: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "scenario": self.scenario,
            "family": self.family,
            "fixture": {
                "presentations": self.fixture.presentations,
                "professors": self.fixture.professors,
                "students": self.fixture.students,
                "classes": self.fixture.classes,
                "departments": self.fixture.departments,
                "rooms": self.fixture.rooms,
                "days": self.fixture.days,
                "notes": self.fixture.notes,
            },
            "config": {
                "time_limit_seconds": self.time_limit_seconds,
                "slot_minutes": self.slot_minutes,
            },
            "result": {
                "solver_status": self.solver_status,
                "solver_label": self.solver_label,
                "expected_status": self.expected_status,
                "expected_match": self.expected_match,
            },
            "quality": self.quality.to_dict(),
            "soft_scores": self.soft_scores.to_dict(),
            "verification": self.verification.to_dict(),
            "diagnostics": list(self.diagnostics),
            "suggestions": list(self.suggestions),
            "critical": self.critical,
            "notes": self.notes,
        }


# ── ANSI helpers ──────────────────────────────────────────────────────────


_ANSI = {
    "reset": "\033[0m",
    "bold": "\033[1m",
    "dim": "\033[2m",
    "red": "\033[31m",
    "green": "\033[32m",
    "yellow": "\033[33m",
    "blue": "\033[34m",
    "magenta": "\033[35m",
    "cyan": "\033[36m",
}


def _color(text: str, color: str, *, enable: bool) -> str:
    if not enable:
        return text
    return f"{_ANSI[color]}{text}{_ANSI['reset']}"


def _use_color() -> bool:
    return sys.stdout.isatty()


# ── Console table ─────────────────────────────────────────────────────────


def _row_color(r: ScenarioResult) -> str:
    if r.critical:
        return "red"
    if not r.expected_match:
        return "red"
    if not r.verification.all_passed:
        return "red"
    if r.quality.unscheduled_count > 0 and r.expected_status not in {"infeasible", "invalid"}:
        return "yellow"
    return "green"


def render_table(
    results: list[ScenarioResult],
    *,
    detail: bool = False,
    color: bool | None = None,
) -> str:
    use_col = _use_color() if color is None else color

    if detail:
        header = (
            "scenario",
            "solver",
            "status",
            "sched%",
            "wall(s)",
            "make(min)",
            "hard",
            "soft.complete",
            "soft.makespan",
            "soft.dept",
            "soft.class",
            "soft.prof",
            "soft.balance",
            "soft.studentA",
            "soft.agg",
        )
    else:
        header = (
            "scenario",
            "solver",
            "status",
            "sched%",
            "wall(s)",
            "make(min)",
            "hard",
            "soft",
        )

    def _fmt_row(r: ScenarioResult) -> tuple[str, ...]:
        sched_pct = f"{r.quality.scheduled_pct * 100:.0f}%"
        hard = "PASS" if r.verification.all_passed else "FAIL"
        if r.critical:
            hard = "CRITICAL"
        if detail:
            return (
                r.scenario,
                r.solver_label,
                r.solver_status,
                sched_pct,
                f"{r.quality.wall_time_seconds:.2f}",
                f"{r.quality.makespan_minutes:.0f}",
                hard,
                f"{r.soft_scores.scheduling_completeness:.2f}",
                f"{r.soft_scores.minimize_makespan:.2f}",
                f"{r.soft_scores.minimize_dept_span:.2f}",
                f"{r.soft_scores.minimize_class_span:.2f}",
                f"{r.soft_scores.minimize_prof_span:.2f}",
                f"{r.soft_scores.balance_rooms:.2f}",
                f"{r.soft_scores.student_availability:.2f}",
                f"{r.soft_scores.aggregate_soft_score:.2f}",
            )
        return (
            r.scenario,
            r.solver_label,
            r.solver_status,
            sched_pct,
            f"{r.quality.wall_time_seconds:.2f}",
            f"{r.quality.makespan_minutes:.0f}",
            hard,
            f"{r.soft_scores.aggregate_soft_score:.2f}",
        )

    rows: list[tuple[str, ...]] = [_fmt_row(r) for r in results]
    widths = [
        max(len(h), max((len(r[i]) for r in rows), default=0))
        for i, h in enumerate(header)
    ]

    def _line(parts: tuple[str, ...], color_name: str | None = None) -> str:
        line = "  ".join(p.ljust(widths[i]) for i, p in enumerate(parts))
        if color_name:
            return _color(line, color_name, enable=use_col)
        return line

    out_lines: list[str] = []
    out_lines.append(_color(_line(header), "bold", enable=use_col))
    out_lines.append("  ".join("-" * w for w in widths))
    for result, row in zip(results, rows):
        out_lines.append(_line(row, _row_color(result)))

    # Footer summary
    total = len(results)
    crit = sum(1 for r in results if r.critical)
    failed = sum(1 for r in results if not r.verification.all_passed)
    mismatched = sum(1 for r in results if not r.expected_match)
    partial = sum(
        1
        for r in results
        if r.quality.unscheduled_count > 0 and r.expected_status not in {"infeasible", "invalid"}
    )
    summary = (
        f"\n{total} scenarios | "
        f"{_color(str(crit) + ' critical', 'red', enable=use_col) if crit else '0 critical'} | "
        f"{_color(str(failed) + ' hard-fail', 'red', enable=use_col) if failed else '0 hard-fail'} | "
        f"{_color(str(mismatched) + ' status-mismatch', 'red', enable=use_col) if mismatched else '0 status-mismatch'} | "
        f"{_color(str(partial) + ' partial', 'yellow', enable=use_col) if partial else '0 partial'}"
    )
    out_lines.append(summary)

    return "\n".join(out_lines)


# ── Critical-failure detail ───────────────────────────────────────────────


def render_critical_details(results: list[ScenarioResult], *, color: bool | None = None) -> str:
    use_col = _use_color() if color is None else color
    crit = [r for r in results if r.critical or not r.verification.all_passed]
    if not crit:
        return ""

    out = ["\n" + _color("=== Hard-constraint failures ===", "red", enable=use_col)]
    for r in crit:
        out.append(_color(f"\n[{r.scenario}]  status={r.solver_status}", "red", enable=use_col))
        for c in r.verification.failures:
            out.append(f"  - {c.name}: {c.reason}")
            if c.offending:
                offenders = ", ".join(c.offending[:5])
                if len(c.offending) > 5:
                    offenders += f" (+{len(c.offending) - 5} more)"
                out.append(f"      offending: {offenders}")
    return "\n".join(out)


# ── JSON output ───────────────────────────────────────────────────────────


def _git_sha() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=Path(__file__).resolve().parents[2],
            stderr=subprocess.DEVNULL,
        ).decode().strip()
    except Exception:
        return "unknown"


def write_json(results: list[ScenarioResult], path: Path) -> None:
    payload = {
        "git_sha": _git_sha(),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "platform": platform.platform(),
        "python": sys.version.split()[0],
        "results": [r.to_dict() for r in results],
    }
    path.write_text(json.dumps(payload, indent=2, default=str))


# ── Baseline diff ─────────────────────────────────────────────────────────


@dataclass
class Regression:
    scenario: str
    metric: str
    baseline: float
    current: float
    delta: float


def diff_against_baseline(
    current: list[ScenarioResult],
    baseline_path: Path,
    *,
    soft_score_tolerance: float = 0.05,
    scheduled_pct_tolerance: float = 0.02,
) -> list[Regression]:
    """Return regressions where current is meaningfully worse than baseline.

    A regression is reported when:
    - aggregate_soft_score drops by more than `soft_score_tolerance`, OR
    - scheduled_pct drops by more than `scheduled_pct_tolerance`, OR
    - a hard-constraint check that previously passed now fails.
    """
    baseline = json.loads(baseline_path.read_text())
    by_name = {r["scenario"]: r for r in baseline.get("results", [])}
    out: list[Regression] = []
    for r in current:
        b = by_name.get(r.scenario)
        if not b:
            continue
        b_soft = float(b["soft_scores"]["aggregate_soft_score"])
        if r.soft_scores.aggregate_soft_score + soft_score_tolerance < b_soft:
            out.append(
                Regression(
                    scenario=r.scenario,
                    metric="aggregate_soft_score",
                    baseline=b_soft,
                    current=r.soft_scores.aggregate_soft_score,
                    delta=r.soft_scores.aggregate_soft_score - b_soft,
                )
            )
        b_pct = float(b["quality"]["scheduled_pct"])
        if r.quality.scheduled_pct + scheduled_pct_tolerance < b_pct:
            out.append(
                Regression(
                    scenario=r.scenario,
                    metric="scheduled_pct",
                    baseline=b_pct,
                    current=r.quality.scheduled_pct,
                    delta=r.quality.scheduled_pct - b_pct,
                )
            )
        # Hard-check regression
        b_pass = bool(b["verification"]["all_passed"])
        if b_pass and not r.verification.all_passed:
            out.append(
                Regression(
                    scenario=r.scenario,
                    metric="hard_constraints",
                    baseline=1.0, current=0.0, delta=-1.0,
                )
            )
    return out


def render_regressions(regressions: list[Regression], *, color: bool | None = None) -> str:
    use_col = _use_color() if color is None else color
    if not regressions:
        return _color("No regressions vs baseline.", "green", enable=use_col)
    lines = [_color("=== Regressions vs baseline ===", "red", enable=use_col)]
    for r in regressions:
        lines.append(
            f"  {r.scenario}.{r.metric}: {r.baseline:.3f} -> {r.current:.3f} (delta {r.delta:+.3f})"
        )
    return "\n".join(lines)
