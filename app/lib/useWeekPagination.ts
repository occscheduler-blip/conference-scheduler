import { useMemo, useState } from "react";

type WeekGroup = {
  /** Human-readable label like "Mar 9 – Mar 13" */
  label: string;
  /** Original indices into the full day array */
  dayIndices: number[];
};

/** Get the Sunday of the week containing the given date. */
function getSunday(date: Date): string {
  const d = new Date(date);
  const day = d.getDay(); // 0=Sun, 1=Mon, ...
  d.setDate(d.getDate() - day);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

function shortDate(key: string): string {
  return new Date(`${key}T00:00:00`).toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
  });
}

/**
 * Groups an array of days into calendar weeks (Mon–Sun) and provides
 * navigation state. Only shows the week toggle when there are multiple weeks.
 *
 * @param dateKeys Array of "YYYY-MM-DD" strings (one per day column).
 */
export function useWeekPagination(dateKeys: string[]) {
  const [weekIndex, setWeekIndex] = useState(0);

  const weeks: WeekGroup[] = useMemo(() => {
    if (dateKeys.length === 0) return [];

    const groups: WeekGroup[] = [];
    let currentSunday: string | null = null;
    let currentGroup: number[] = [];

    for (let i = 0; i < dateKeys.length; i++) {
      const sunday = getSunday(new Date(`${dateKeys[i]}T00:00:00`));
      if (sunday !== currentSunday) {
        if (currentGroup.length > 0) {
          const first = dateKeys[currentGroup[0]];
          const last = dateKeys[currentGroup[currentGroup.length - 1]];
          groups.push({
            label: first === last ? shortDate(first) : `${shortDate(first)} – ${shortDate(last)}`,
            dayIndices: currentGroup,
          });
        }
        currentSunday = sunday;
        currentGroup = [i];
      } else {
        currentGroup.push(i);
      }
    }
    if (currentGroup.length > 0) {
      const first = dateKeys[currentGroup[0]];
      const last = dateKeys[currentGroup[currentGroup.length - 1]];
      groups.push({
        label: first === last ? shortDate(first) : `${shortDate(first)} – ${shortDate(last)}`,
        dayIndices: currentGroup,
      });
    }

    return groups;
  }, [dateKeys]);

  // Clamp weekIndex to valid range
  const safeIndex = weeks.length === 0 ? 0 : Math.min(weekIndex, weeks.length - 1);

  const hasMultipleWeeks = weeks.length > 1;
  const currentWeek = weeks[safeIndex] ?? { label: "", dayIndices: [] as number[] };

  return {
    /** Whether the week toggle should be shown */
    hasMultipleWeeks,
    /** Current week's day indices into the original array */
    visibleDayIndices: currentWeek.dayIndices,
    /** Label for the current week, e.g. "Mar 9 – Mar 13" */
    weekLabel: currentWeek.label,
    /** 1-based index for display */
    weekNumber: safeIndex + 1,
    /** Total number of weeks */
    totalWeeks: weeks.length,
    /** Go to previous week */
    prevWeek: () => setWeekIndex((i) => Math.max(0, i - 1)),
    /** Go to next week */
    nextWeek: () => setWeekIndex((i) => Math.min(weeks.length - 1, i + 1)),
    /** Whether there's a previous week */
    hasPrev: safeIndex > 0,
    /** Whether there's a next week */
    hasNext: safeIndex < weeks.length - 1,
  };
}
