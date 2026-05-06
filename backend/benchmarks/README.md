# Scheduler benchmark suite

Standalone, in-memory benchmarks for the CP-SAT scheduler in
`backend/app/scheduler/`. No Supabase needed. Not run by `make test`.

## Running

From the `backend/` directory:

```bash
python -m benchmarks                        # default: ~30s on a laptop
python -m benchmarks --mode quick           # ~5s, just sanity scenarios
python -m benchmarks --mode full            # several minutes; sweeps + huge fixtures
python -m benchmarks --scenario medium,massive
python -m benchmarks --out report.json
python -m benchmarks --detail               # per-soft-constraint columns
python -m benchmarks --baseline base.json   # diff vs prior; exit 1 on regression
python -m benchmarks --list                 # show what would run
python -m benchmarks --no-color
```

Exit codes:

- `0` — all scenarios matched expectations, no regressions
- `1` — at least one scenario produced an unexpected solver status, or a
  baseline regression was detected
- `2` — at least one **critical** failure: solver returned `optimal`/`feasible`
  but a hard-constraint check found a real violation (room overlap, double-booking,
  etc.). This is a correctness bug.

## Solver dispatch

The runner mirrors `app.scheduler.service.build_schedule_for_symposium`:
problems above the hierarchical thresholds (>100 presentations or >15 classes)
go to `solve_hierarchical`, smaller ones stay on the flat `solve_schedule`.
The `solver` column in the report shows which path each scenario took, so it
is obvious whether the hierarchical work is being exercised.

## What it measures

For every scenario:

- **Hard-constraint correctness** (10 verifiers, see `verification.py`):
  no room overlap, no resource double-booking, in-symposium-window,
  in-prof-window, same-class-same-room, buffer respected, slot aligned,
  room index in range, assignments unique, unscheduled list consistent.
- **Quality of partial results** — scheduled fraction, makespan, dept/class/prof
  span, room load imbalance, soft-availability violations.
- **Wall-clock time**.
- **Soft-constraint satisfaction** — each soft objective is normalized to
  a 0.0–1.0 score (1.0 = ideal). Aggregated as a geometric mean.

## Scenario families

### Scale (`tiny`, `small`, `medium`, `large`, `massive`, `huge`)

Programmatic versions of the seed-script scale presets, parametrized with a
fixed RNG seed. `massive` (200 presentations) and `huge` (400 presentations)
exercise the hierarchical solver dispatch above 100 presentations / 15 classes.

### Failure modes

Deliberately broken inputs that test graceful degradation:

- `prof-bottleneck` — prof window shorter than presentation duration → all
  presentations should fail pre-filter.
- `class-crunch` — same-class-same-room with required time exceeding the
  symposium window → at least one unscheduled.
- `prof-student-gap` — prof and student windows never overlap → all
  unscheduled (with `student_availability=hard`).
- `no-rooms` — `rooms_available=0` → status `invalid`.
- `no-windows` — empty `symposium_windows` → infeasible.
- `no-presentations` — empty input → trivially optimal.
- `oversubscribed` — far more presentations than time × rooms → forced
  partial result.
- `cross-listed-prof` / `double-major-student` — same person under two
  row-ids in two classes; tests `resource_identity` dedup so the solver
  doesn't double-book the underlying person.
- `tight-feasibility` — exactly enough room-time to fit everything; verifies
  the solver finds the packing.

### Sweeps (full mode only)

- `medium@1s/3s/10s/30s` and `massive@3s/10s/30s/60s` — same fixture at
  several solver budgets to characterize the anytime curve.
- `medium-cov-{tight|mid|loose}` — varying availability coverage.
- `medium-slot-{1|5|10|15}` — varying slot alignment.
- `medium-stu-{soft|hard}_class-{soft|hard}` — constraint-mode variants.

## Output

### Console

```
scenario        status    sched%  wall(s)  make(min)  hard  soft
--------------  --------  ------  -------  ---------  ----  ----
tiny            optimal   100%    0.04     85         PASS  0.94
small           feasible  100%    0.31     245        PASS  0.81
medium          feasible  100%    4.20     470        PASS  0.78
prof-bottleneck infeasible 0%     0.01     0          PASS  0.00
...

42 scenarios | 0 critical | 0 hard-fail | 0 status-mismatch | 0 partial
```

`--detail` expands the `soft` column into the seven sub-scores.

### JSON

`--out report.json` writes a structured record with:

- git SHA, timestamp, platform
- per-scenario: fixture metadata, solver config, status, full quality
  metrics, full soft scores, full verification report, diagnostics

The JSON is suitable for diffing across runs (`--baseline`) or feeding into
external tooling.

## Findings on first run

When this suite was first added, two scenarios produced **CRITICAL**
hard-constraint failures, surfacing a real correctness gap in the flat
CP-SAT solver: `cross-listed-prof` and `double-major-student` both
double-booked the same underlying person across rooms.

Root cause: `cp_sat.py` was building `presentations_by_resource` (and the
soft-conflict / professor-span loops) keyed by raw `resource_id`, never
consulting `problem.resource_identity` for canonicalization. The
hierarchical solver (`hierarchical.py:115`) already canonicalised, so
problems above the hierarchical-dispatch threshold (>100 presentations or
>15 classes) were unaffected.

The fix canonicalises in three spots in `cp_sat.py`:
`presentations_by_resource` construction, the soft `person_conflicts` time
sweep, and the `professor_resource_ids` span-minimization loop. Both
scenarios now PASS and remain in the suite as ongoing regression tests.

## Layout

```
backend/benchmarks/
  fixtures.py        # programmatic ScheduleProblem builders
  scenarios.py       # named-scenario registry, run modes
  verification.py    # 10 hard-constraint correctness checks
  quality.py         # raw metrics + soft-constraint satisfaction scoring
  reporting.py       # console table, JSON, baseline diff
  runner.py          # orchestration
  __main__.py        # CLI entrypoint
```
