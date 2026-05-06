"""Benchmark orchestration: build fixtures, run solver, collect metrics."""
from __future__ import annotations

import time

from app.scheduler import solve_schedule
from app.scheduler.models import ScheduleResult

from .fixtures import Fixture
from .quality import measure_quality, score_soft_constraints
from .reporting import ScenarioResult
from .scenarios import Scenario
from .verification import verify


def _expected_match(expected: str | None, actual: str) -> bool:
    if expected is None:
        return actual in {"optimal", "feasible", "infeasible"}
    return expected == actual


def run_scenario(scenario: Scenario) -> ScenarioResult:
    """Build the fixture, run the solver, measure, verify, and bundle."""
    fixture: Fixture = scenario.builder()
    problem = fixture.problem
    meta = fixture.meta

    t0 = time.perf_counter()
    result: ScheduleResult = solve_schedule(
        problem, time_limit_seconds=scenario.time_limit_seconds
    )
    wall = time.perf_counter() - t0

    quality = measure_quality(problem, result, wall)
    soft = score_soft_constraints(problem, result, quality)
    ver = verify(problem, result)

    expected_match = _expected_match(meta.expected_status, result.status)

    # Critical: solver said success but a hard check failed.
    critical = (
        result.status in {"optimal", "feasible"}
        and result.assignments
        and not ver.all_passed
    )

    # Min-unscheduled enforcement for failure-mode fixtures.
    min_unscheduled = meta.extra.get("min_unscheduled") if meta.extra else None
    required_scheduled = meta.extra.get("required_scheduled") if meta.extra else None
    if isinstance(min_unscheduled, int) and quality.unscheduled_count < min_unscheduled:
        expected_match = False
    if isinstance(required_scheduled, int) and quality.scheduled_count < required_scheduled:
        expected_match = False

    return ScenarioResult(
        scenario=scenario.name,
        family=scenario.family,
        fixture=meta,
        time_limit_seconds=scenario.time_limit_seconds,
        slot_minutes=problem.slot_minutes,
        solver_status=result.status,
        expected_status=meta.expected_status,
        expected_match=expected_match,
        quality=quality,
        soft_scores=soft,
        verification=ver,
        diagnostics=result.diagnostics,
        suggestions=result.suggestions,
        critical=bool(critical),
        notes=meta.notes,
    )


def run_scenarios(scenarios: list[Scenario]) -> list[ScenarioResult]:
    out: list[ScenarioResult] = []
    for s in scenarios:
        print(f"  running {s.name} (time_limit={s.time_limit_seconds}s) ...", flush=True)
        out.append(run_scenario(s))
    return out
