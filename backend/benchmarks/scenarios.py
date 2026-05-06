"""Named scenario registry.

A "scenario" is a fixture + a solver config (time limit, etc.) + a mode tag
that controls when it runs. The registry below is the source of truth for
which benchmarks belong to `quick`, `default`, and `full` modes.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from . import fixtures
from .fixtures import Fixture


@dataclass(frozen=True)
class Scenario:
    name: str
    builder: Callable[[], Fixture]
    time_limit_seconds: float
    modes: frozenset[str]  # subset of {"quick", "default", "full"}
    family: str            # "scale" | "failure" | "sweep"
    tags: frozenset[str] = frozenset()


# Convenience: every scenario in `default` is also in `full`; every scenario
# in `quick` is also in `default` and `full`. We model that explicitly so
# `--mode default` doesn't need to merge sets at call time.

_QUICK = frozenset({"quick", "default", "full"})
_DEFAULT = frozenset({"default", "full"})
_FULL_ONLY = frozenset({"full"})


def _scale_scenarios() -> list[Scenario]:
    return [
        Scenario("tiny", fixtures.fixture_tiny, 5.0, _QUICK, "scale"),
        Scenario("small", fixtures.fixture_small, 10.0, _QUICK, "scale"),
        Scenario("medium", fixtures.fixture_medium, 30.0, _DEFAULT, "scale"),
        Scenario("large", fixtures.fixture_large, 30.0, _DEFAULT, "scale"),
        Scenario(
            "massive",
            fixtures.fixture_massive,
            60.0,
            _FULL_ONLY,
            "scale",
            tags=frozenset({"hierarchical"}),
        ),
        Scenario(
            "huge",
            fixtures.fixture_huge,
            120.0,
            _FULL_ONLY,
            "scale",
            tags=frozenset({"hierarchical"}),
        ),
    ]


def _failure_scenarios() -> list[Scenario]:
    return [
        Scenario("prof-bottleneck", fixtures.fixture_prof_bottleneck, 5.0, _QUICK, "failure"),
        Scenario("class-crunch", fixtures.fixture_class_crunch, 5.0, _QUICK, "failure"),
        Scenario("prof-student-gap", fixtures.fixture_prof_student_gap, 5.0, _QUICK, "failure"),
        Scenario("no-rooms", fixtures.fixture_no_rooms, 1.0, _QUICK, "failure"),
        Scenario("no-windows", fixtures.fixture_no_windows, 1.0, _QUICK, "failure"),
        Scenario("no-presentations", fixtures.fixture_no_presentations, 1.0, _QUICK, "failure"),
        Scenario("oversubscribed", fixtures.fixture_oversubscribed, 5.0, _DEFAULT, "failure"),
        Scenario("cross-listed-prof", fixtures.fixture_cross_listed_prof, 10.0, _DEFAULT, "failure"),
        Scenario("double-major-student", fixtures.fixture_double_major_student, 5.0, _DEFAULT, "failure"),
        Scenario("tight-feasibility", fixtures.fixture_tight_feasibility, 10.0, _DEFAULT, "failure"),
    ]


def _sweep_scenarios() -> list[Scenario]:
    out: list[Scenario] = []

    # Time-limit sweep on `medium`: same fixture, varying solver budget.
    for tl in (1.0, 3.0, 10.0, 30.0):
        out.append(
            Scenario(
                name=f"medium@{int(tl)}s",
                builder=fixtures.fixture_medium,
                time_limit_seconds=tl,
                modes=_FULL_ONLY,
                family="sweep",
                tags=frozenset({"time-limit"}),
            )
        )

    # Time-limit sweep on `massive`: tests partial-result quality at low budget.
    for tl in (3.0, 10.0, 30.0, 60.0):
        out.append(
            Scenario(
                name=f"massive@{int(tl)}s",
                builder=fixtures.fixture_massive,
                time_limit_seconds=tl,
                modes=_FULL_ONLY,
                family="sweep",
                tags=frozenset({"time-limit", "hierarchical"}),
            )
        )

    # Coverage (loose vs tight availability).
    for cov, label in [(0.5, "tight"), (0.75, "mid"), (1.0, "loose")]:
        builder = lambda c=cov, l=label: fixtures.fixture_medium_with_coverage(c, l)
        out.append(
            Scenario(
                name=f"medium-cov-{label}",
                builder=builder,
                time_limit_seconds=30.0,
                modes=_FULL_ONLY,
                family="sweep",
                tags=frozenset({"coverage"}),
            )
        )

    # Slot alignment.
    for slot in (1, 5, 10, 15):
        builder = lambda s=slot: fixtures.fixture_medium_with_slot(s)
        out.append(
            Scenario(
                name=f"medium-slot-{slot}",
                builder=builder,
                time_limit_seconds=30.0,
                modes=_FULL_ONLY,
                family="sweep",
                tags=frozenset({"slot"}),
            )
        )

    # Constraint variants.
    for stu_avail in ("soft", "hard"):
        for sc_room in ("soft", "hard"):
            label = f"stu-{stu_avail}_class-{sc_room}"
            builder = lambda s=stu_avail, c=sc_room, l=label: fixtures.fixture_medium_with_constraints(
                student_availability=s, same_class_same_room=c, label=l,
            )
            out.append(
                Scenario(
                    name=f"medium-{label}",
                    builder=builder,
                    time_limit_seconds=30.0,
                    modes=_FULL_ONLY,
                    family="sweep",
                    tags=frozenset({"constraints"}),
                )
            )

    return out


def all_scenarios() -> list[Scenario]:
    return _scale_scenarios() + _failure_scenarios() + _sweep_scenarios()


def scenarios_for_mode(mode: str) -> list[Scenario]:
    if mode not in {"quick", "default", "full"}:
        raise ValueError(f"Unknown mode: {mode!r}. Expected quick|default|full.")
    return [s for s in all_scenarios() if mode in s.modes]


def scenarios_by_name(names: list[str]) -> list[Scenario]:
    by_name = {s.name: s for s in all_scenarios()}
    missing = [n for n in names if n not in by_name]
    if missing:
        raise ValueError(
            f"Unknown scenario(s): {missing}. Available: {sorted(by_name)}"
        )
    return [by_name[n] for n in names]
