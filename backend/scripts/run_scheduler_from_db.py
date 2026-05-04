from __future__ import annotations

import sys
from datetime import datetime

from app.scheduler import build_problem_from_symposium, build_schedule_for_symposium


def _format_timestamp(value: datetime) -> str:
    local_value = value.astimezone()
    return local_value.strftime("%a %b %d, %Y %I:%M %p")


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: python3 scripts/run_scheduler_from_db.py <symposium_id> [slot_minutes]")
        return 1

    symposium_id = sys.argv[1]
    slot_minutes = int(sys.argv[2]) if len(sys.argv) > 2 else 5

    problem = build_problem_from_symposium(symposium_id, slot_minutes=slot_minutes)
    result = build_schedule_for_symposium(symposium_id, slot_minutes=slot_minutes)

    print("Scheduler Result")
    print(f"Symposium ID: {problem.symposium_id}")
    print(f"Rooms Available: {problem.rooms_available}")
    print(f"Presentations: {len(problem.presentations)}")
    print(f"Slot Size: {problem.slot_minutes} minutes")
    print(f"Status: {result.status.upper()}")

    if result.diagnostics:
        print("\nDiagnostics")
        for message in result.diagnostics:
            print(f"- {message}")

    if result.suggestions:
        print("\nSuggestions")
        for message in result.suggestions:
            print(f"- {message}")

    if result.assignments:
        presentation_by_id = {item.id: item for item in problem.presentations}
        print("\nSchedule")
        for index, assignment in enumerate(result.assignments, start=1):
            presentation = presentation_by_id[assignment.presentation_id]
            print(
                f"{index}. {presentation.title}\n"
                f"   Room {assignment.room_index + 1}\n"
                f"   {_format_timestamp(assignment.start)} - {_format_timestamp(assignment.end)}"
            )

    if result.unscheduled_presentations:
        presentation_by_id = {item.id: item for item in problem.presentations}
        print("\nUnscheduled Presentations")
        for presentation_id in result.unscheduled_presentations:
            title = presentation_by_id.get(presentation_id)
            print(f"- {title.title if title else presentation_id}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
