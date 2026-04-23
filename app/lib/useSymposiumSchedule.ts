/**
 * Shared fetch for the symposium → departments → classes → presentations →
 * (students, professors, timeframes) chain that `schedule-tab.tsx`, `home.tsx`,
 * `professor.tsx`, and `student.tsx` all re-implement.
 *
 * Exports:
 *   - `fetchSymposiumSchedule` — one-shot async function callers can await from
 *     their own effects. Useful when the caller wants tight control (refetch,
 *     race guards, interleaved loading states).
 *   - `useSymposiumSchedule`   — a React hook wrapper that owns the loading /
 *     error / data state for simpler callers.
 *
 * The hook intentionally returns raw row shapes (`RawPresentation` etc.) —
 * each page still owns the transformation to its own view model
 * (`PresentationRecord` vs `SchedulePresentation`) because those differ.
 */
import { useCallback, useEffect, useState } from "react";

import { apiFetch } from "./api";
import type {
  ClassRecord,
  DepartmentRecord,
  SymposiumDetails,
  Timeframe,
} from "../pages/types";

// ── Raw row shapes from the API ────────────────────────────────────────────

export type RawPresentation = {
  id?: string;
  class_id?: string;
  title?: string;
  minutes?: number;
  buffer?: number;
  room?: number | null;
  temporary_room?: number | null;
  presenting_students?: Array<{ id?: string; student_id?: string; name?: string }>;
};

export type RawStudent = { id?: string; name?: string; class_id?: string };

export type RawProfessor = { id?: string; name?: string; class_id?: string };

// ── Options & return shape ─────────────────────────────────────────────────

export type SymposiumScheduleMode = "published" | "draft";

export type UseSymposiumScheduleOptions = {
  /**
   * "published" fetches `/api/events/timeframes` (live schedule, `room` field).
   * "draft" fetches `/api/events/temporary_timeframes` (editor, `temporary_room`).
   * Defaults to "published".
   */
  mode?: SymposiumScheduleMode;
  /** Fetch `/api/events/professors?class_id=…` too. Off by default. */
  includeProfessors?: boolean;
  /** Passed on every request. Omit for public GET endpoints. */
  authHeaders?: Record<string, string>;
};

export type SymposiumScheduleData = {
  symposium: SymposiumDetails | null;
  symposiumTimeframes: Timeframe[];
  departments: DepartmentRecord[];
  classes: ClassRecord[];
  presentations: RawPresentation[];
  students: RawStudent[];
  professors: RawProfessor[];
  /** Timeframes for each presentation (polymorphic `linked_id = presentation_id`). */
  presentationTimeframes: Timeframe[];
};

const EMPTY_DATA: SymposiumScheduleData = {
  symposium: null,
  symposiumTimeframes: [],
  departments: [],
  classes: [],
  presentations: [],
  students: [],
  professors: [],
  presentationTimeframes: [],
};

// ── Core fetcher ───────────────────────────────────────────────────────────

export async function fetchSymposiumSchedule(
  symposiumId: string,
  options: UseSymposiumScheduleOptions = {},
): Promise<SymposiumScheduleData> {
  const { mode = "published", includeProfessors = false, authHeaders } = options;
  if (!symposiumId.trim()) return { ...EMPTY_DATA };

  const headers = authHeaders
    ? { "Content-Type": "application/json", ...authHeaders }
    : { "Content-Type": "application/json" };

  // 1. Symposium detail — non-standard shape ({ symposium, timeframes }) so
  //    we use raw fetch rather than apiFetch's list normalization.
  const symRes = await fetch(`/api/backend/api/events/symposiums/${symposiumId}`, { headers });
  const symPayload = (await symRes.json().catch(() => ({}))) as {
    detail?: string;
    symposium?: SymposiumDetails;
    timeframes?: Timeframe[];
  };
  if (!symRes.ok) {
    throw new Error(symPayload.detail ?? "Failed to load symposium.");
  }

  const symposium = symPayload.symposium ?? null;
  const symposiumTimeframes = (symPayload.timeframes ?? [])
    .slice()
    .sort((a, b) => a.start_time.localeCompare(b.start_time));

  // 2. Departments — a missing endpoint or network hiccup here shouldn't crash
  //    the whole load; continue with whatever we managed to fetch.
  let departments: DepartmentRecord[] = [];
  try {
    departments = await apiFetch<DepartmentRecord>(
      `/api/events/departments?symposium_id=${encodeURIComponent(symposiumId)}`,
      { headers: authHeaders },
    );
  } catch {
    /* keep empty */
  }

  if (departments.length === 0) {
    return { ...EMPTY_DATA, symposium, symposiumTimeframes, departments };
  }

  // 3. Classes for every department (one bulk call, comma-separated).
  const departmentIdParam = departments.map((d) => d.id).join(",");
  let classes: ClassRecord[] = [];
  try {
    classes = await apiFetch<ClassRecord>(
      `/api/events/classes?department_id=${encodeURIComponent(departmentIdParam)}`,
      { headers: authHeaders },
    );
  } catch {
    /* keep empty */
  }

  // 4. Presentations + students (+ optional professors) in parallel.
  const classIdParam = classes.map((c) => c.id).join(",");
  const presentationsPromise: Promise<RawPresentation[]> = classIdParam
    ? apiFetch<RawPresentation>(
        `/api/events/presentations?class_id=${encodeURIComponent(classIdParam)}`,
        { headers: authHeaders },
      ).catch(() => [])
    : Promise.resolve([]);
  const studentsPromise: Promise<RawStudent[]> = classIdParam
    ? apiFetch<RawStudent>(
        `/api/events/students?class_id=${encodeURIComponent(classIdParam)}`,
        { headers: authHeaders },
      ).catch(() => [])
    : Promise.resolve([]);
  const professorsPromise: Promise<RawProfessor[]> =
    includeProfessors && classIdParam
      ? apiFetch<RawProfessor>(
          `/api/events/professors?class_id=${encodeURIComponent(classIdParam)}`,
          { headers: authHeaders },
        ).catch(() => [])
      : Promise.resolve([]);

  const [presentations, students, professors] = await Promise.all([
    presentationsPromise,
    studentsPromise,
    professorsPromise,
  ]);

  // 5. Presentation timeframes — draft vs published endpoint chosen by mode.
  const presentationIdParam = presentations
    .map((p) => p.id ?? "")
    .filter((id) => id.length > 0)
    .join(",");
  const timeframeEndpoint = mode === "draft" ? "temporary_timeframes" : "timeframes";
  let presentationTimeframes: Timeframe[] = [];
  if (presentationIdParam) {
    try {
      presentationTimeframes = await apiFetch<Timeframe>(
        `/api/events/${timeframeEndpoint}?linked_id=${encodeURIComponent(presentationIdParam)}`,
        { headers: authHeaders },
      );
    } catch {
      /* keep empty */
    }
  }

  return {
    symposium,
    symposiumTimeframes,
    departments,
    classes,
    presentations,
    students,
    professors,
    presentationTimeframes,
  };
}

// ── Hook wrapper ───────────────────────────────────────────────────────────

export type UseSymposiumScheduleResult = {
  data: SymposiumScheduleData | null;
  isLoading: boolean;
  error: string | null;
  refetch: () => Promise<void>;
};

export function useSymposiumSchedule(
  symposiumId: string,
  options: UseSymposiumScheduleOptions = {},
): UseSymposiumScheduleResult {
  const [data, setData] = useState<SymposiumScheduleData | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Destructure to make effect deps explicit; options object itself changes
  // identity every render so we'd otherwise refetch on every render.
  const { mode, includeProfessors, authHeaders } = options;

  const load = useCallback(async () => {
    if (!symposiumId.trim()) {
      setData(null);
      setError(null);
      return;
    }
    setIsLoading(true);
    setError(null);
    try {
      const result = await fetchSymposiumSchedule(symposiumId, {
        mode,
        includeProfessors,
        authHeaders,
      });
      setData(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load schedule.");
      setData(null);
    } finally {
      setIsLoading(false);
    }
  }, [symposiumId, mode, includeProfessors, authHeaders]);

  useEffect(() => {
    void load();
  }, [load]);

  return { data, isLoading, error, refetch: load };
}
