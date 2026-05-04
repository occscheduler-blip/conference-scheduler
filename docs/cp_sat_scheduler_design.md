# CP-SAT Scheduler Design

This project is a good fit for OR-Tools CP-SAT because the schedule is mostly a finite combinatorial assignment problem:

- Choose one valid start time for each presentation
- Choose one room for each presentation
- Prevent overlapping use of rooms and people
- Respect availability windows

## Why CP-SAT fits this project

CP-SAT is stronger than a greedy or simple heuristic approach when several constraints interact:

- limited rooms
- different presentation durations
- professors advising multiple classes
- student presenters grouped into one presentation
- fragmented availability windows across multiple days

Those constraints create backtracking-heavy cases where "pick earliest available slot" starts failing quickly.

## Recommended solver model

Use discrete start-time options rather than continuous time.

1. Build candidate start times from symposium windows in fixed increments.
2. Filter those candidates by participant availability.
3. Let CP-SAT choose exactly one `(presentation, start, room)` combination.

### Decision variables

For each valid tuple `(presentation p, start option s, room r)`, create:

- `x[p, s, r] in {0, 1}`

Meaning: presentation `p` starts at candidate time `s` in room `r`.

### Hard constraints

- Every presentation is assigned exactly once.
- No room can host overlapping presentations.
- No shared resource can be double-booked.
- A presentation must fit completely inside a symposium timeframe.
- A presentation must fit completely inside every required participant's availability.

### Objective

Start with a simple objective:

- minimize makespan (finish the symposium as early as possible)

Then add soft preferences later if needed:

- minimize gaps for each department
- keep the same class close together
- avoid very early or very late slots
- spread presentations across rooms evenly

## Current schema gaps

The solver can still be built now, but these gaps should be addressed if you want the schedule to be explainable and persistable.

### 1. No room assignment is stored

`presentations` has `start_time` and `end_time`, but no room column.

Recommended fix:

- add `room_index integer` or `room_label text` to `presentations`

### 2. Resource ownership must be explicit

The solver needs a normalized resource list for every presentation:

- presenting students
- class professors/advisors
- possibly department heads, judges, or moderators if they become constraints

Right now those relationships can be derived, but the scheduling service should build a flattened resource list before solving.

### 3. Time granularity should not assume 15 minutes

The UI uses 15-minute cells, but `minutes` allows any value from 1 to 60. A 20-minute presentation does not map cleanly to a 15-minute grid.

Recommended fix:

- run the solver at 5-minute granularity
- keep the UI at 15 minutes if you want, but round only for display, not optimization

## Edge cases to handle

- A presentation with no presenters attached
- A class with multiple professors
- A student presenting in multiple presentations
- Availability windows that overlap or touch
- Presentation duration longer than any valid window
- Too many presentations to fit even if all availability is respected
- Day boundaries with fragmented windows like `09:00-11:00` and `13:00-15:00`
- Time zone normalization between frontend and backend

## Suggested integration path

1. Keep the solver pure and detached from FastAPI and Supabase.
2. Add a service layer that reads one symposium's data and converts it into `ScheduleProblem`.
3. Expose a new route such as `POST /api/events/schedule`.
4. Return diagnostics when infeasible instead of only returning a generic failure.
5. Persist `start_time`, `end_time`, and room assignment together in one write phase.

## Files added

- `backend/app/scheduler/models.py`
- `backend/app/scheduler/cp_sat.py`
- `backend/tests/test_scheduler_cp_sat.py`

These give you a working baseline for the solver and a place to expand constraints without mixing OR-Tools code into route handlers.
