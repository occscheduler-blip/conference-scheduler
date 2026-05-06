"""CLI entrypoint: `python -m benchmarks [...]` from the backend/ directory."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import reporting
from .reporting import (
    diff_against_baseline,
    render_critical_details,
    render_regressions,
    render_table,
    write_json,
)
from .runner import run_scenarios
from .scenarios import scenarios_by_name, scenarios_for_mode


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="python -m benchmarks",
        description="Run the scheduler benchmark suite.",
    )
    p.add_argument(
        "--mode",
        choices=("quick", "default", "full"),
        default="default",
        help="Which scenarios to run. quick=~5s, default=~30s, full=several minutes.",
    )
    p.add_argument(
        "--scenario",
        help="Comma-separated scenario name(s) to run. Overrides --mode.",
    )
    p.add_argument(
        "--out",
        type=Path,
        help="Write a JSON report to this path.",
    )
    p.add_argument(
        "--detail",
        action="store_true",
        help="Expand the soft-score column into per-constraint sub-columns.",
    )
    p.add_argument(
        "--baseline",
        type=Path,
        help="Compare against a prior JSON report; exit 1 on regression.",
    )
    p.add_argument(
        "--no-color",
        action="store_true",
        help="Disable ANSI colour in console output.",
    )
    p.add_argument(
        "--list",
        action="store_true",
        help="List scenarios that would run, then exit.",
    )
    args = p.parse_args(argv)

    if args.scenario:
        names = [s.strip() for s in args.scenario.split(",") if s.strip()]
        scenarios = scenarios_by_name(names)
    else:
        scenarios = scenarios_for_mode(args.mode)

    if args.list:
        for s in scenarios:
            print(f"  {s.name}\t({s.family}, time_limit={s.time_limit_seconds}s)")
        return 0

    color = not args.no_color
    print(f"Running {len(scenarios)} scenarios in --mode {args.mode} ...")
    results = run_scenarios(scenarios)
    print()
    print(render_table(results, detail=args.detail, color=color))
    crit = render_critical_details(results, color=color)
    if crit:
        print(crit)

    if args.out:
        write_json(results, args.out)
        print(f"\nWrote JSON report to {args.out}")

    exit_code = 0
    if any(r.critical for r in results):
        exit_code = 2
    elif any(
        not r.expected_match or not r.verification.all_passed for r in results
    ):
        exit_code = 1

    if args.baseline:
        regressions = diff_against_baseline(results, args.baseline)
        print()
        print(render_regressions(regressions, color=color))
        if regressions:
            exit_code = max(exit_code, 1)

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
