# Schedule grid rendering — fixed-window/fixed-granularity issue

## Summary

The admin Schedule tab renders presentations using a **hardcoded grid**: 9 AM
to 9 PM in fixed 15-minute cells. The scheduler, however, emits assignments
with arbitrary symposium windows (whatever timeframes the admin set) and
arbitrary per-presentation durations (5-minute aligned, but values like 15,
20, 25 minutes are common). When these don't fit the hardcoded grid, the
visual output looks broken — presentations appear stacked or overflowing at
the bottom of a column even though the **underlying scheduler output is
correct** and contains no time overlaps.

This is a presentation-layer bug. The scheduler itself enforces no-overlap
as a hard constraint (verification sweep blocks any save with a hard
overlap) and the saved `temporary_timeframes` rows in the DB have correct
start/end times with proper buffer gaps.

## Reproduction

1. Run the seeded "Massive Symposium" via `backend/seed_massive_symposium.py`.
   It has timeframes `14:00–23:00` on three consecutive days and per-
   presentation durations sampled from `{15, 20, 25}` minutes with a
   5-minute buffer.
2. Run the scheduler with `student_availability="soft"` (default constraints
   would refuse to save because some students can't fit their hard windows).
3. Open the Schedule tab in the admin UI.

Observed: presentations after about 21:00 appear visually clipped or stacked
on top of each other at the bottom of each room column. Two example
presentations the user reported: "Class 13 — Student 6" (21:20–21:40) and
"Class 13 — Student 4" (21:45–22:00) appear to overlap in the rendered grid,
though the saved DB rows show a clean 5-minute gap between them.

Direct DB query confirming the data is correct (every consecutive pair in
the same room has exactly the expected buffer between them, 0 overlaps
across all 8 rooms × 200 presentations):

```bash
.venv/bin/python -c "
# query temporary_timeframes for symposium 3d559c66-... and pairwise-check
# every pair within the same room. Result: 0 overlaps.
"
```

## Root cause

`app/lib/utils.ts:3`

```ts
export const totalSlots = 48; // 9:00 AM to 9:00 PM in 15-minute increments
```

This constant assumes:

1. **The symposium runs 9 AM to 9 PM.** Any timeframe outside that range
   (e.g. 21:00–23:00) is rendered outside the visible grid container.
2. **Slot granularity is 15 minutes.** A presentation of duration 20 or 25
   minutes (or a buffer of 5 minutes) does not align to 15-minute cell
   boundaries, so the renderer either rounds positions or stacks cards
   imprecisely.

`schedule-tab.tsx` and `availability-editor.tsx` both consume `totalSlots`
and assume a uniform grid built from it. Anything the scheduler emits that
doesn't fit (which is now common — the hierarchical solver routinely places
classes in late evenings, and per-presentation buffers default to 5 min) is
displayed incorrectly.

## What the fix needs to do

Make the rendering dimensions a function of the **selected symposium's
timeframes and presentation data**, not a global constant. Concretely:

1. **Replace `totalSlots`/`SLOT_MINUTES` constants with values derived per
   symposium.** From the symposium's `timeframes`:
   - `gridStart` = earliest `start_time` of any timeframe on the displayed
     day, clamped to the day boundary.
   - `gridEnd` = latest `end_time` on the displayed day.
   - `slotMinutes` = greatest common divisor of all presentation durations
     and buffers within the displayed schedule (5 is a safe default; 1
     would let the scheduler pick anything but produces a very tall grid).

   The grid then has `(gridEnd - gridStart) / slotMinutes` rows.

2. **Update both consumers in lockstep** so the availability editor and the
   schedule tab use the same grid dimensions:
   - `app/pages/schedule-tab.tsx` (rendering, click-to-edit, modal start
     time defaults at line ~596)
   - `app/pages/availability-editor.tsx` (drag-to-select uses the same grid
     via `totalSlots`)

3. **Position each card by minutes-from-`gridStart`, not by slot index.**
   The current code seems to use slot-index-based positioning. Switch to
   `top: (start - gridStart) / totalDuration * gridPx` and
   `height: durationMinutes / totalDuration * gridPx`. This makes the
   layout robust to any slot granularity.

4. **Keep buffer gaps visible.** A 5-minute buffer should render as a
   visible gap (proportional to the cell height). Today the eye sees two
   adjacent 15-min cells and reads them as touching; on a 5-min grid the
   gap between two 15-minute talks with a 5-minute buffer becomes a
   distinct row.

5. **Backend gives you everything you need.** No backend changes required.
   `GET /api/events/temporary_timeframes` and `GET /api/events/symposiums/{id}`
   together expose the symposium's time windows and every presentation's
   start/end. The scheduler already enforces no-overlap as a hard
   constraint (`verify_assignments_split` returns hard issues for any
   actual overlap; status="invalid" is returned and the schedule is not
   saved).

## What the fix should NOT do

- **Don't round scheduler output to 15-minute boundaries** as a workaround
  — that would force every preso to be a multiple of 15 minutes and waste
  symposium time. The scheduler is correct; the renderer is wrong.
- **Don't change `default_buffer` or any of the constraint defaults** — the
  display-layer mismatch is independent of constraint policy.

## Files to touch

- `app/lib/utils.ts` — replace `totalSlots` with a hook/function that
  derives the grid dimensions from a symposium.
- `app/pages/schedule-tab.tsx` — render cards by minute-offsets; update
  the schedule-edit modal's default-time logic.
- `app/pages/availability-editor.tsx` — same per-symposium grid dimensions
  for drag-to-select.
- (Probably a small shared util in `app/lib/`) — a `useGridGeometry(symposium)`
  hook that returns `{ gridStart, gridEnd, slotMinutes, slotsPerDay }`.

## Verification

After the fix, with the Massive Symposium loaded:

- The Schedule tab shows presentations from 14:00 to 23:00 (or whatever
  the symposium's actual range is), with 5-minute granularity.
- Each card's height is proportional to its duration; a 25-minute card
  is visibly taller than a 15-minute card.
- Buffer gaps between consecutive cards in the same room are visible as
  small empty rows.
- No card extends below or above its room column's bounds.

Sanity-checking the underlying data (already confirmed clean today):

```python
# pairwise overlap check across temporary_timeframes for any symposium
# should return 0
```
