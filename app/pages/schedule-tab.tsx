"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type {
  ClassRecord,
  DepartmentRecord,
  SchedulePresentation,
  SymposiumOption,
  Timeframe,
} from "./types";
import {
  totalSlots,
  formatTimeLabel,
  parseBackendDateTime,
  toBackendDateTime,
  dayKey,
  dayLabel,
  timeLabel,
  normalizeId,
  detectScheduleConflict,
  DEFAULT_CONSTRAINTS,
  type ScheduleConstraints,
  type ConflictContext,
} from "../lib/utils";
import { apiFetch, apiGet, apiPost, apiPut } from "../lib/api";
import { useScheduleDrag, formatMinuteTime } from "../lib/useScheduleDrag";

/** Convert a Date to a datetime-local input value (YYYY-MM-DDTHH:MM). */
function toDatetimeLocal(d: Date): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())}T${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}`;
}

import { FIELD_CLASS as fieldClass } from "../lib/styles";

const SLOT_HEIGHT = 24;

// Color palette for presentation blocks (cycles through)
const BLOCK_COLORS = [
  { bg: "#1635a7", text: "#fff" },
  { bg: "#2e7d32", text: "#fff" },
  { bg: "#c62828", text: "#fff" },
  { bg: "#6a1b9a", text: "#fff" },
  { bg: "#ef6c00", text: "#fff" },
  { bg: "#00838f", text: "#fff" },
];

function getRoomLabel(roomNames: Array<string | null> | null | undefined, roomIndex: number): string {
  const roomName = roomNames?.[roomIndex];
  return typeof roomName === "string" && roomName.trim() ? roomName.trim() : `Room ${roomIndex + 1}`;
}

export default function ScheduleTab({
  token,
}: {
  token: string;
}) {
  const authHeaders = useMemo(() => ({ Authorization: `Bearer ${token}` }), [token]);

  // Symposium selection
  const [symposiumOptions, setSymposiumOptions] = useState<SymposiumOption[]>([]);
  const [selectedSymposiumId, setSelectedSymposiumId] = useState("");
  const [isLoadingSymposia, setIsLoadingSymposia] = useState(false);

  // Schedule data
  const [presentations, setPresentations] = useState<SchedulePresentation[]>([]);
  const [symposiumTimeframes, setSymposiumTimeframes] = useState<Timeframe[]>([]);
  const [roomsAvailable, setRoomsAvailable] = useState(1);
  const [roomNames, setRoomNames] = useState<Array<string | null>>([]);
  const [isLoadingSchedule, setIsLoadingSchedule] = useState(false);
  const [selectedDay, setSelectedDay] = useState("");
  const [message, setMessage] = useState<string | null>(null);

  // Scheduler
  const [isRunningScheduler, setIsRunningScheduler] = useState(false);
  const [schedulerMessage, setSchedulerMessage] = useState<string | null>(null);
  const [schedulerFailure, setSchedulerFailure] = useState<{ unscheduledCount: number } | null>(null);

  // Edit modal
  const [editingPresentation, setEditingPresentation] = useState<SchedulePresentation | null>(null);
  const [editRoom, setEditRoom] = useState("");
  const [editStartTime, setEditStartTime] = useState("");
  const isSavingAssignment = false; // kept for disabled prop; modal save is now synchronous
  const [assignmentMessage, setAssignmentMessage] = useState<string | null>(null);

  // Person name lookup for conflict messages
  const [personNames, setPersonNames] = useState<Map<string, string>>(new Map());

  // Constraint settings
  const [constraints, setConstraints] = useState<ScheduleConstraints>({ ...DEFAULT_CONSTRAINTS });
  const [constraintsOpen, setConstraintsOpen] = useState(false);

  // Resource availability for constraint checking
  const [resourceAvailability, setResourceAvailability] = useState<
    Map<string, Array<{ start_time: string; end_time: string }>>
  >(new Map());
  const [allProfessorIds, setAllProfessorIds] = useState<Set<string>>(new Set());

  // Pending changes (batched saves)
  const [pendingChanges, setPendingChanges] = useState<
    Map<string, { room: number; start_time: string; end_time: string }>
  >(new Map());
  const [isBulkSaving, setIsBulkSaving] = useState(false);
  const [bulkSaveMessage, setBulkSaveMessage] = useState<string | null>(null);

  // Load symposia list
  const fetchSymposia = useCallback(async () => {
    setIsLoadingSymposia(true);
    try {
      const rows = await apiFetch<SymposiumOption>("/api/events/symposiums", { headers: authHeaders });
      setSymposiumOptions(rows);
      if (rows.length > 0 && !selectedSymposiumId) {
        setSelectedSymposiumId(rows[0].id);
      }
    } catch (error) {
      const msg = error instanceof Error ? error.message : "Unknown error";
      setMessage(msg);
    } finally {
      setIsLoadingSymposia(false);
    }
  }, [authHeaders, selectedSymposiumId]);

  // Load full schedule data for a symposium
  const fetchScheduleData = useCallback(
    async (symposiumId: string) => {
      if (!symposiumId.trim()) {
        setPresentations([]);
        setSymposiumTimeframes([]);
        setRoomsAvailable(1);
        setRoomNames([]);
        setSelectedDay("");
        return;
      }

      setIsLoadingSchedule(true);
      setMessage(null);
      setSchedulerMessage(null);

      try {
        // Fetch symposium detail
        const symposiumRes = await fetch(`/api/backend/api/events/symposiums/${symposiumId}`, {
          headers: { "Content-Type": "application/json", ...authHeaders },
        });
        const symposiumPayload = (await symposiumRes.json().catch(() => ({}))) as {
          detail?: string;
          symposium?: { id: string; name: string; rooms_available?: number | null; room_names?: Array<string | null> | null };
          timeframes?: Timeframe[];
        };
        if (!symposiumRes.ok) throw new Error(symposiumPayload.detail ?? "Failed to load symposium.");

        const symTimeframes = (symposiumPayload.timeframes ?? []).slice().sort((a, b) => {
          return parseBackendDateTime(a.start_time).getTime() - parseBackendDateTime(b.start_time).getTime();
        });
        setSymposiumTimeframes(symTimeframes);
        const parsedRooms = Number(symposiumPayload.symposium?.rooms_available ?? 1);
        setRoomsAvailable(Number.isFinite(parsedRooms) && parsedRooms > 0 ? Math.floor(parsedRooms) : 1);
        setRoomNames(symposiumPayload.symposium?.room_names ?? []);

        // Fetch departments
        let departmentRows: DepartmentRecord[] = [];
        try {
          departmentRows = await apiFetch<DepartmentRecord>(
            `/api/events/departments?symposium_id=${encodeURIComponent(symposiumId)}`
          );
        } catch {
          // continue with empty
        }

        if (departmentRows.length === 0) {
          setPresentations([]);
          const days = Array.from(new Set(symTimeframes.map((tf) => dayKey(parseBackendDateTime(tf.start_time)))));
          setSelectedDay(days[0] ?? "");
          return;
        }

        // Bulk-fetch classes for all departments in one call
        const departmentIdParam = departmentRows.map((d) => d.id).join(",");
        let classRows: ClassRecord[] = [];
        try {
          classRows = await apiFetch<ClassRecord>(
            `/api/events/classes?department_id=${encodeURIComponent(departmentIdParam)}`
          );
        } catch {
          classRows = [];
        }

        // Department lookup
        const deptById = new Map(departmentRows.map((d) => [d.id, d]));
        const deptIdByClassId = new Map(classRows.map((c) => [c.id, c.department_id]));

        // Fetch presentations, students, and professors for all classes in parallel (3 calls total)
        type RawPresentation = {
          id?: string;
          class_id?: string;
          title?: string;
          minutes?: number;
          buffer?: number;
          room?: number | null;
          presenting_students?: Array<{ id?: string; student_id?: string; name?: string }>;
        };
        type RawStudent = { id?: string; name?: string };

        type RawProfessor = { id?: string; name?: string; class_id?: string };

        const classIdParam = classRows.map((row) => row.id).join(",");
        const [rawPresentations, rawStudents, rawProfessors] = classIdParam
          ? await Promise.all([
              apiFetch<RawPresentation>(
                `/api/events/presentations?class_id=${encodeURIComponent(classIdParam)}`
              ).catch(() => [] as RawPresentation[]),
              apiFetch<RawStudent>(
                `/api/events/students?class_id=${encodeURIComponent(classIdParam)}`
              ).catch(() => [] as RawStudent[]),
              apiFetch<RawProfessor>(
                `/api/events/professors?class_id=${encodeURIComponent(classIdParam)}`
              ).catch(() => [] as RawProfessor[]),
            ])
          : [[] as RawPresentation[], [] as RawStudent[], [] as RawProfessor[]];

        // Professor IDs grouped by class_id (all professors in a class are resources for all its presentations)
        const professorIdsByClass = new Map<string, string[]>();
        const personNameById = new Map<string, string>();
        for (const prof of rawProfessors) {
          const cid = prof.class_id ?? "";
          const pid = prof.id ?? "";
          if (cid && pid) {
            const arr = professorIdsByClass.get(cid) ?? [];
            arr.push(normalizeId(pid));
            professorIdsByClass.set(cid, arr);
            const name = prof.name?.trim() ?? "";
            if (name) personNameById.set(normalizeId(pid), name);
          }
        }

        const studentNameById = new Map(
          rawStudents
            .filter((r): r is { id: string; name: string } => Boolean(r.id && r.name?.trim()))
            .map((r) => [normalizeId(r.id), r.name.trim()])
        );

        // Bulk-fetch timeframes for all presentations in one call
        const presentationIds = rawPresentations
          .map((row) => row.id ?? "")
          .filter((id) => id.length > 0);
        let allPresentationTimeframes: Timeframe[] = [];
        if (presentationIds.length > 0) {
          try {
            allPresentationTimeframes = await apiFetch<Timeframe>(
              `/api/events/timeframes?linked_id=${encodeURIComponent(presentationIds.join(","))}`
            );
          } catch {
            allPresentationTimeframes = [];
          }
        }
        const timeframeByPresentation = new Map<string, Timeframe>();
        for (const tf of allPresentationTimeframes) {
          const key = normalizeId(tf.linked_id ?? "");
          if (!key) continue;
          const existing = timeframeByPresentation.get(key);
          if (
            !existing ||
            parseBackendDateTime(tf.start_time).getTime() <
              parseBackendDateTime(existing.start_time).getTime()
          ) {
            timeframeByPresentation.set(key, tf);
          }
        }

        const presentationRows: SchedulePresentation[] = rawPresentations
          .map((row) => {
            const presenterNames = (row.presenting_students ?? [])
              .map((s) => {
                const directName = s.name?.trim() ?? "";
                if (directName) return directName;
                const sid = s.id ?? s.student_id ?? "";
                return studentNameById.get(normalizeId(sid)) ?? "";
              })
              .filter((name) => name.length > 0);

            const deptId = deptIdByClassId.get(row.class_id ?? "");
            const dept = deptId ? deptById.get(deptId) : undefined;

            // Build resource IDs: professors (via class) + presenting students
            const classId = row.class_id ?? "";
            const resourceIds = new Set<string>(professorIdsByClass.get(classId) ?? []);
            for (const s of row.presenting_students ?? []) {
              const sid = normalizeId(s.id ?? s.student_id ?? "");
              if (sid) {
                resourceIds.add(sid);
                const name = s.name?.trim() ?? "";
                if (name) personNameById.set(sid, name);
              }
            }

            return {
              id: row.id ?? "",
              title: row.title?.trim() ?? "",
              class_id: row.class_id ?? "",
              minutes: row.minutes ?? 0,
              buffer: row.buffer ?? 0,
              room: row.room ?? null,
              timeframe: timeframeByPresentation.get(normalizeId(row.id ?? "")) ?? null,
              presenterNames: Array.from(new Set(presenterNames)),
              departmentName: dept?.department_name ?? "",
              resourceIds: Array.from(resourceIds),
            };
          })
          .filter((r): r is SchedulePresentation => Boolean(r.id && r.class_id));

        // Collect all professor and student IDs for availability fetching
        const profIdSet = new Set<string>();
        for (const ids of professorIdsByClass.values()) {
          for (const pid of ids) profIdSet.add(pid);
        }
        const allResourceIds = new Set(profIdSet);
        for (const row of rawStudents) {
          const sid = normalizeId(row.id ?? "");
          if (sid) allResourceIds.add(sid);
        }

        // Bulk-fetch availability timeframes for all professors and students in one call
        const resAvailMap = new Map<string, Array<{ start_time: string; end_time: string }>>();
        const resourceIdList = Array.from(allResourceIds);
        if (resourceIdList.length > 0) {
          try {
            const allAvailTfs = await apiFetch<Timeframe>(
              `/api/events/timeframes?linked_id=${encodeURIComponent(resourceIdList.join(","))}`,
            );
            for (const tf of allAvailTfs) {
              const key = normalizeId(tf.linked_id ?? "");
              if (!key) continue;
              const existing = resAvailMap.get(key);
              if (existing) {
                existing.push({ start_time: tf.start_time, end_time: tf.end_time });
              } else {
                resAvailMap.set(key, [{ start_time: tf.start_time, end_time: tf.end_time }]);
              }
            }
          } catch {
            // skip — no availability means fully available
          }
        }

        setPresentations(presentationRows);
        setPersonNames(new Map(personNameById));
        setAllProfessorIds(profIdSet);
        setResourceAvailability(resAvailMap);

        const days = Array.from(new Set(symTimeframes.map((tf) => dayKey(parseBackendDateTime(tf.start_time)))));
        setSelectedDay((prev) => (days.includes(prev) ? prev : days[0] ?? ""));
      } catch (error) {
        const msg = error instanceof Error ? error.message : "Unknown error";
        setMessage(msg);
        setPresentations([]);
        setSymposiumTimeframes([]);
        setRoomsAvailable(1);
        setRoomNames([]);
      } finally {
        setIsLoadingSchedule(false);
      }
    },
    [authHeaders]
  );

  useEffect(() => {
    void fetchSymposia();
  }, [fetchSymposia]);

  useEffect(() => {
    void fetchScheduleData(selectedSymposiumId);
  }, [selectedSymposiumId, fetchScheduleData]);

  // Derived state
  const days = useMemo(
    () => Array.from(new Set(symposiumTimeframes.map((tf) => dayKey(parseBackendDateTime(tf.start_time))))),
    [symposiumTimeframes]
  );

  // Compute which time slots are active on the selected day (from symposium timeframes)
  const activeSlots = useMemo(() => {
    const slots = new Set<number>();
    for (const tf of symposiumTimeframes) {
      const start = parseBackendDateTime(tf.start_time);
      if (dayKey(start) !== selectedDay) continue;
      const end = parseBackendDateTime(tf.end_time);
      const startMinutes = start.getUTCHours() * 60 + start.getUTCMinutes();
      const endMinutes = end.getUTCHours() * 60 + end.getUTCMinutes();
      const firstSlot = Math.floor((startMinutes - 9 * 60) / 15);
      const lastSlot = Math.ceil((endMinutes - 9 * 60) / 15);
      for (let s = firstSlot; s < lastSlot; s++) {
        if (s >= 0 && s < totalSlots) slots.add(s);
      }
    }
    return slots;
  }, [symposiumTimeframes, selectedDay]);

  const minSlot = useMemo(() => (activeSlots.size > 0 ? Math.min(...activeSlots) : 0), [activeSlots]);
  const maxSlot = useMemo(() => (activeSlots.size > 0 ? Math.max(...activeSlots) + 1 : totalSlots), [activeSlots]);
  const visibleSlotCount = maxSlot - minSlot;

  // Scheduled presentations for the selected day
  const scheduledForDay = useMemo(() => {
    return presentations.filter((p) => {
      if (p.room === null || !p.timeframe) return false;
      return dayKey(parseBackendDateTime(p.timeframe.start_time)) === selectedDay;
    });
  }, [presentations, selectedDay]);

  // Unscheduled presentations (no room or no timeframe)
  const unscheduled = useMemo(() => {
    return presentations.filter((p) => p.room === null || !p.timeframe);
  }, [presentations]);

  // Color map by presentation id (consistent colors)
  const colorMap = useMemo(() => {
    const map = new Map<string, { bg: string; text: string }>();
    presentations.forEach((p, i) => {
      map.set(p.id, BLOCK_COLORS[i % BLOCK_COLORS.length]);
    });
    return map;
  }, [presentations]);

  // Grid ref for drag-and-drop coordinate calculations
  const gridRef = useRef<HTMLDivElement | null>(null);

  // Conflict context for constraint checking (shared by drag hook + edit modal)
  const conflictContext: ConflictContext = useMemo(() => ({
    allPresentations: presentations,
    personNames,
    roomNames,
    constraints,
    symposiumTimeframes,
    resourceAvailability,
    professorIds: allProfessorIds,
    slotMinutes: 1,
  }), [presentations, personNames, roomNames, constraints, symposiumTimeframes, resourceAvailability, allProfessorIds]);

  // Handlers
  const handleRunScheduler = async (skipConfirm: boolean = false) => {
    if (!selectedSymposiumId) return;
    if (!skipConfirm && !window.confirm("This will regenerate the schedule. Existing assignments will be replaced. Continue?")) return;

    setIsRunningScheduler(true);
    setSchedulerMessage("Starting scheduler...");
    setSchedulerFailure(null);
    try {
      const { raw: startRaw } = await apiPost("/api/events/schedule", {
        symposium_id: selectedSymposiumId,
        constraints: {
          room_conflicts: constraints.roomConflicts,
          person_conflicts: constraints.personConflicts,
          symposium_windows: constraints.symposiumWindows,
          professor_availability: constraints.professorAvailability,
          student_availability: constraints.studentAvailability,
          same_class_same_room: constraints.sameClassSameRoom,
          slot_alignment: constraints.slotAlignment,
          minimize_makespan: constraints.minimizeMakespan,
          minimize_class_span: constraints.minimizeClassSpan,
          minimize_professor_span: constraints.minimizeProfessorSpan,
          balance_rooms: constraints.balanceRooms,
        },
      }, authHeaders);

      const jobId = startRaw.job_id as string;
      setSchedulerMessage("Scheduler running...");

      // Poll until the job completes or fails (5 minute timeout)
      const POLL_TIMEOUT_MS = 5 * 60 * 1000;
      const pollStart = Date.now();
      const raw = await new Promise<Record<string, unknown>>((resolve, reject) => {
        const poll = async () => {
          if (Date.now() - pollStart > POLL_TIMEOUT_MS) {
            reject(new Error("Scheduler timed out after 5 minutes."));
            return;
          }
          try {
            const job = await apiGet(
              `/api/events/schedule_job/${encodeURIComponent(jobId)}`,
              authHeaders,
            );
            const jobStatus = job.status as string;
            if (jobStatus === "completed") {
              resolve(job.result as Record<string, unknown>);
            } else if (jobStatus === "failed") {
              reject(new Error((job.error as string) ?? "Scheduler failed"));
            } else {
              setTimeout(() => void poll(), 2000);
            }
          } catch (err) {
            reject(err);
          }
        };
        void poll();
      });

      const status = raw.status as string;
      const assignments = (raw.assignments as unknown[]) ?? [];
      const unscheduledIds = (raw.unscheduled_presentations as unknown[]) ?? [];
      setSchedulerMessage(
        `Schedule ${status}. ${assignments.length} assigned, ${unscheduledIds.length} unscheduled.`
      );
      setPendingChanges(new Map());
      setBulkSaveMessage(null);
      await fetchScheduleData(selectedSymposiumId);
      if (unscheduledIds.length > 0) {
        setSchedulerFailure({ unscheduledCount: unscheduledIds.length });
      }
    } catch (error) {
      const msg = error instanceof Error ? error.message : "Unknown error";
      setSchedulerMessage(`Error: ${msg}`);
    } finally {
      setIsRunningScheduler(false);
    }
  };

  const handleOpenEditModal = (pres: SchedulePresentation) => {
    setEditingPresentation(pres);
    setEditRoom(pres.room !== null ? String(pres.room) : "0");
    if (pres.timeframe) {
      const start = parseBackendDateTime(pres.timeframe.start_time);
      setEditStartTime(toDatetimeLocal(start));
    } else {
      // Default to start of the selected day's first symposium slot
      const dayTimeframes = symposiumTimeframes.filter(
        (tf) => dayKey(parseBackendDateTime(tf.start_time)) === selectedDay
      );
      if (dayTimeframes.length > 0) {
        const start = parseBackendDateTime(dayTimeframes[0].start_time);
        setEditStartTime(toDatetimeLocal(start));
      } else {
        setEditStartTime("");
      }
    }
    setAssignmentMessage(null);
  };

  // Drag-and-drop
  const handleDrop = useCallback(
    (presId: string, room: number, startTime: Date, endTime: Date) => {
      const startISO = toBackendDateTime(startTime);
      const endISO = toBackendDateTime(endTime);

      setPendingChanges((prev) => {
        const next = new Map(prev);
        next.set(presId, { room, start_time: startISO, end_time: endISO });
        return next;
      });

      setPresentations((prev) =>
        prev.map((p) =>
          p.id === presId
            ? {
                ...p,
                room,
                timeframe: { id: p.timeframe?.id ?? "", linked_id: p.id, start_time: startISO, end_time: endISO },
              }
            : p
        )
      );
      setBulkSaveMessage(null);
    },
    [],
  );

  const { dragState, isDragging, handleBlockPointerDown, handleUnscheduledPointerDown } =
    useScheduleDrag({
      roomsAvailable,
      minSlot,
      maxSlot,
      selectedDay,
      conflictContext,
      gridRef,
      onDrop: handleDrop,
      onClickBlock: handleOpenEditModal,
    });

  const handleSaveAssignment = () => {
    if (!editingPresentation || !selectedSymposiumId) return;
    if (!editStartTime) {
      setAssignmentMessage("Please select a start time.");
      return;
    }

    const startDate = new Date(`${editStartTime}:00Z`);
    if (Number.isNaN(startDate.getTime())) {
      setAssignmentMessage("Invalid start time.");
      return;
    }

    const room = Number(editRoom);
    const endDate = new Date(startDate.getTime() + editingPresentation.minutes * 60 * 1000);
    const startISO = toBackendDateTime(startDate);
    const endISO = toBackendDateTime(endDate);

    const conflict = detectScheduleConflict(editingPresentation, room, startDate, conflictContext);
    if (conflict?.blocked) {
      setAssignmentMessage(conflict.message);
      return;
    }
    if (conflict) {
      setAssignmentMessage(`Warning: ${conflict.message}`);
    }

    // Store in pending changes
    setPendingChanges((prev) => {
      const next = new Map(prev);
      next.set(editingPresentation.id, { room, start_time: startISO, end_time: endISO });
      return next;
    });

    // Optimistically update local presentations state
    setPresentations((prev) =>
      prev.map((p) =>
        p.id === editingPresentation.id
          ? {
              ...p,
              room,
              timeframe: { id: p.timeframe?.id ?? "", linked_id: p.id, start_time: startISO, end_time: endISO },
            }
          : p
      )
    );

    setBulkSaveMessage(null);
    setEditingPresentation(null);
  };

  const handleBulkSave = async () => {
    if (pendingChanges.size === 0 || !selectedSymposiumId) return;

    setIsBulkSaving(true);
    setBulkSaveMessage(null);
    try {
      const assignments = Array.from(pendingChanges.entries()).map(([presId, change]) => ({
        presentation_id: presId,
        room: change.room,
        start_time: change.start_time,
        end_time: change.end_time,
      }));

      await apiPut(
        "/api/events/bulk_update_schedule_assignments",
        { symposium_id: selectedSymposiumId, assignments },
        authHeaders
      );

      setPendingChanges(new Map());
      setBulkSaveMessage(`Saved ${assignments.length} assignment(s).`);
      await fetchScheduleData(selectedSymposiumId);
    } catch (error) {
      const msg = error instanceof Error ? error.message : "Unknown error";
      setBulkSaveMessage(msg);
    } finally {
      setIsBulkSaving(false);
    }
  };

  const handleDiscardChanges = async () => {
    setPendingChanges(new Map());
    setBulkSaveMessage(null);
    if (selectedSymposiumId) {
      await fetchScheduleData(selectedSymposiumId);
    }
  };

  // Computed end time for display in modal
  const editEndTimeDisplay = useMemo(() => {
    if (!editStartTime || !editingPresentation) return "";
    const start = new Date(`${editStartTime}:00Z`);
    if (Number.isNaN(start.getTime())) return "";
    const end = new Date(start.getTime() + editingPresentation.minutes * 60 * 1000);
    return end.toLocaleTimeString([], { hour: "numeric", minute: "2-digit", timeZone: "UTC" });
  }, [editStartTime, editingPresentation]);

  return (
    <div className="space-y-4">
      {/* Symposium selector */}
      <div className="rounded-xl border border-[#d8e2ff] bg-white p-4">
        <label className="block text-xs font-bold uppercase tracking-wide text-[#1b338f]">
          Select Symposium
        </label>
        <select
          value={selectedSymposiumId}
          onChange={(e) => { setSelectedSymposiumId(e.target.value); setPendingChanges(new Map()); setBulkSaveMessage(null); }}
          disabled={isLoadingSymposia}
          className={fieldClass + " mt-2"}
        >
          {symposiumOptions.length === 0 ? <option value="">No symposia found</option> : null}
          {symposiumOptions.map((s) => (
            <option key={s.id} value={s.id}>
              {s.name || s.symposium_name || s.id}
            </option>
          ))}
        </select>
      </div>

      {/* Generate Schedule button */}
      {selectedSymposiumId ? (
        <div className="flex items-center gap-4">
          <button
            type="button"
            onClick={() => handleRunScheduler()}
            disabled={isRunningScheduler}
            className="rounded-lg bg-[#1b6e2b] px-6 py-2.5 text-base font-semibold text-white transition hover:bg-[#15572b] disabled:opacity-50"
          >
            {isRunningScheduler ? "Generating..." : "Generate Schedule"}
          </button>
          {schedulerMessage ? (
            <p className={`text-sm font-medium ${schedulerMessage.startsWith("Error") ? "text-[#9a1f1f]" : "text-[#1b6e2b]"}`}>
              {schedulerMessage}
            </p>
          ) : null}
        </div>
      ) : null}

      {/* Constraint settings menu */}
      {selectedSymposiumId ? (
        <div className="relative">
          <button
            type="button"
            onClick={() => setConstraintsOpen((v) => !v)}
            className="flex items-center gap-2 rounded-lg border border-[#c7d4ff] bg-white px-4 py-2 text-sm font-semibold text-[#1b338f] transition hover:bg-[#f0f4ff]"
          >
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" className="h-4 w-4">
              <path fillRule="evenodd" d="M7.84 1.804A1 1 0 0 1 8.82 1h2.36a1 1 0 0 1 .98.804l.331 1.652a6.993 6.993 0 0 1 1.929 1.115l1.598-.54a1 1 0 0 1 1.186.447l1.18 2.044a1 1 0 0 1-.205 1.251l-1.267 1.113a7.047 7.047 0 0 1 0 2.228l1.267 1.113a1 1 0 0 1 .206 1.25l-1.18 2.045a1 1 0 0 1-1.187.447l-1.598-.54a6.993 6.993 0 0 1-1.929 1.115l-.33 1.652a1 1 0 0 1-.98.804H8.82a1 1 0 0 1-.98-.804l-.331-1.652a6.993 6.993 0 0 1-1.929-1.115l-1.598.54a1 1 0 0 1-1.186-.447l-1.18-2.044a1 1 0 0 1 .205-1.251l1.267-1.114a7.05 7.05 0 0 1 0-2.227L1.821 7.773a1 1 0 0 1-.206-1.25l1.18-2.045a1 1 0 0 1 1.187-.447l1.598.54A6.993 6.993 0 0 1 7.51 3.456l.33-1.652ZM10 13a3 3 0 1 0 0-6 3 3 0 0 0 0 6Z" clipRule="evenodd" />
            </svg>
            Constraints
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" className={`h-3.5 w-3.5 transition ${constraintsOpen ? "rotate-180" : ""}`}>
              <path fillRule="evenodd" d="M5.22 8.22a.75.75 0 0 1 1.06 0L10 11.94l3.72-3.72a.75.75 0 1 1 1.06 1.06l-4.25 4.25a.75.75 0 0 1-1.06 0L5.22 9.28a.75.75 0 0 1 0-1.06Z" clipRule="evenodd" />
            </svg>
          </button>
          {constraintsOpen ? (
            <>
            <div className="fixed inset-0 z-20" onClick={() => setConstraintsOpen(false)} />
            <div className="absolute left-0 top-full z-30 mt-1 w-[22rem] rounded-lg border border-[#d8e2ff] bg-white p-3 shadow-xl">
              <div className="mb-2 flex items-center justify-between">
                <p className="text-[11px] font-bold uppercase tracking-wide text-[#888]">
                  Constraints
                </p>
                <div className="flex gap-[2px] text-[9px] font-bold uppercase tracking-wide text-[#aaa]">
                  <span className="w-[34px] text-center">Off</span>
                  <span className="w-[34px] text-center">Soft</span>
                  <span className="w-[34px] text-center">Hard</span>
                </div>
              </div>
              {([
                { key: "roomConflicts" as const, label: "Room conflicts", desc: "No double-booking a room" },
                { key: "personConflicts" as const, label: "Person conflicts", desc: "No double-booking professors/students" },
                { key: "symposiumWindows" as const, label: "Symposium time windows", desc: "Must fall within symposium hours" },
                { key: "professorAvailability" as const, label: "Professor availability", desc: "Must fit professor availability" },
                { key: "studentAvailability" as const, label: "Student availability", desc: "Must fit student availability" },
                { key: "sameClassSameRoom" as const, label: "Same class \u2192 same room", desc: "Class presentations share a room" },
              ]).map(({ key, label, desc }) => (
                <div key={key} className="flex items-center justify-between gap-2 rounded-md px-2 py-1.5 transition hover:bg-[#f5f8ff]">
                  <div className="min-w-0 flex-1">
                    <div className="text-sm font-medium text-[#111]">{label}</div>
                    <div className="text-[11px] text-[#888]">{desc}</div>
                  </div>
                  <div className="flex shrink-0 overflow-hidden rounded-md border border-[#d0d8f0]">
                    {(["off", "soft", "hard"] as const).map((mode) => (
                      <button
                        key={mode}
                        type="button"
                        onClick={() => setConstraints((prev) => ({ ...prev, [key]: mode }))}
                        className={`w-[34px] py-0.5 text-[10px] font-semibold transition ${
                          constraints[key] === mode
                            ? mode === "off"
                              ? "bg-[#e0e0e0] text-[#555]"
                              : mode === "soft"
                                ? "bg-[#fff3cd] text-[#856404]"
                                : "bg-[#1635a7] text-white"
                            : "bg-white text-[#aaa] hover:bg-[#f5f5f5]"
                        }`}
                      >
                        {mode === "off" ? "Off" : mode === "soft" ? "Soft" : "Hard"}
                      </button>
                    ))}
                  </div>
                </div>
              ))}
              {/* Slot alignment — numeric selector */}
              <div className="flex items-center justify-between gap-2 rounded-md px-2 py-1.5 transition hover:bg-[#f5f8ff]">
                <div className="min-w-0 flex-1">
                  <div className="text-sm font-medium text-[#111]">Slot alignment</div>
                  <div className="text-[11px] text-[#888]">Snap start times to a fixed interval</div>
                </div>
                <div className="flex shrink-0 overflow-hidden rounded-md border border-[#d0d8f0]">
                  {([1, 5, 10, 15, 20] as const).map((mins) => (
                    <button
                      key={mins}
                      type="button"
                      onClick={() => setConstraints((prev) => ({ ...prev, slotAlignment: mins }))}
                      className={`w-[34px] py-0.5 text-[10px] font-semibold transition ${
                        constraints.slotAlignment === mins
                          ? "bg-[#1635a7] text-white"
                          : "bg-white text-[#aaa] hover:bg-[#f5f5f5]"
                      }`}
                    >
                      {`${mins}m`}
                    </button>
                  ))}
                </div>
              </div>
              <hr className="my-2 border-[#e5eaff]" />
              <div className="mb-2 flex items-center justify-between">
                <p className="text-[11px] font-bold uppercase tracking-wide text-[#888]">
                  Optimization (auto-scheduler)
                </p>
                <div className="flex gap-[2px] text-[9px] font-bold uppercase tracking-wide text-[#aaa]">
                  <span className="w-[34px] text-center">Off</span>
                  <span className="w-[34px] text-center">Soft</span>
                  <span className="w-[34px] text-center">Hard</span>
                </div>
              </div>
              {([
                { key: "minimizeMakespan" as const, label: "Minimize total duration", desc: "Finish the schedule as early as possible" },
                { key: "minimizeClassSpan" as const, label: "Group class presentations", desc: "Keep same-class presentations close in time" },
                { key: "minimizeProfessorSpan" as const, label: "Group professor presentations", desc: "Keep same-professor presentations close in time" },
                { key: "balanceRooms" as const, label: "Balance room usage", desc: "Distribute presentations evenly across rooms" },
              ]).map(({ key, label, desc }) => (
                <div key={key} className="flex items-center justify-between gap-2 rounded-md px-2 py-1.5 transition hover:bg-[#f5f8ff]">
                  <div className="min-w-0 flex-1">
                    <div className="text-sm font-medium text-[#111]">{label}</div>
                    <div className="text-[11px] text-[#888]">{desc}</div>
                  </div>
                  <div className="flex shrink-0 overflow-hidden rounded-md border border-[#d0d8f0]">
                    {(["off", "soft", "hard"] as const).map((mode) => (
                      <button
                        key={mode}
                        type="button"
                        onClick={() => setConstraints((prev) => ({ ...prev, [key]: mode }))}
                        className={`w-[34px] py-0.5 text-[10px] font-semibold transition ${
                          constraints[key] === mode
                            ? mode === "off"
                              ? "bg-[#e0e0e0] text-[#555]"
                              : mode === "soft"
                                ? "bg-[#fff3cd] text-[#856404]"
                                : "bg-[#1635a7] text-white"
                            : "bg-white text-[#aaa] hover:bg-[#f5f5f5]"
                        }`}
                      >
                        {mode === "off" ? "Off" : mode === "soft" ? "Soft" : "Hard"}
                      </button>
                    ))}
                  </div>
                </div>
              ))}
            </div>
            </>
          ) : null}
        </div>
      ) : null}

      {/* Save / Discard buttons for pending changes */}
      {pendingChanges.size > 0 ? (
        <div className="flex items-center gap-3 rounded-lg border border-[#d6b676] bg-[#fffbe6] px-4 py-2.5">
          <span className="text-sm font-semibold text-[#7a6100]">
            {pendingChanges.size} unsaved change{pendingChanges.size !== 1 ? "s" : ""}
          </span>
          <button
            type="button"
            onClick={handleBulkSave}
            disabled={isBulkSaving}
            className="rounded-lg bg-[#0f33a8] px-5 py-2 text-sm font-semibold text-white transition hover:bg-[#1237af] disabled:opacity-50"
          >
            {isBulkSaving ? "Saving..." : "Save Changes"}
          </button>
          <button
            type="button"
            onClick={handleDiscardChanges}
            disabled={isBulkSaving}
            className="rounded-lg border border-[#9a1f1f] bg-white px-5 py-2 text-sm font-semibold text-[#9a1f1f] transition hover:bg-[#fff0f0] disabled:opacity-50"
          >
            Discard
          </button>
        </div>
      ) : null}

      {bulkSaveMessage ? (
        <p className={`text-sm font-semibold ${bulkSaveMessage.startsWith("Saved") ? "text-[#1b6e2b]" : "text-[#9a1f1f]"}`}>
          {bulkSaveMessage}
        </p>
      ) : null}

      {message ? <p className="text-sm font-semibold text-[#9a1f1f]">{message}</p> : null}

      {isLoadingSchedule ? (
        <p className="text-sm text-[#555]">Loading schedule...</p>
      ) : null}

      {/* Day tabs + Unscheduled tab */}
      {!isLoadingSchedule && days.length > 0 ? (
        <div className="overflow-hidden rounded-lg border-2 border-[#1635a7]">
          <div className="flex">
            {days.map((day) => {
              const active = day === selectedDay;
              return (
                <button
                  key={day}
                  type="button"
                  onClick={() => setSelectedDay(day)}
                  className={`flex-1 whitespace-nowrap px-4 py-2.5 text-sm font-semibold ${
                    active
                      ? "bg-white text-[#111]"
                      : "bg-[#1635a7] text-white hover:bg-[#0b2a8d]"
                  }`}
                >
                  {dayLabel(day)}
                </button>
              );
            })}
            <button
              type="button"
              onClick={() => setSelectedDay("unscheduled")}
              className={`flex-1 whitespace-nowrap px-4 py-2.5 text-sm font-semibold ${
                selectedDay === "unscheduled"
                  ? "bg-white text-[#111]"
                  : "bg-[#1635a7] text-white hover:bg-[#0b2a8d]"
              }`}
            >
              Unscheduled{unscheduled.length > 0 ? ` (${unscheduled.length})` : ""}
            </button>
          </div>
        </div>
      ) : null}

      {/* Schedule grid + unscheduled side panel */}
      {!isLoadingSchedule && selectedDay && selectedDay !== "unscheduled" && activeSlots.size > 0 ? (
        <div className="flex gap-3">
        <div className="min-w-0 flex-1 overflow-x-auto rounded-lg border border-[#d8e2ff] bg-white">
          <div
            ref={gridRef}
            className="grid"
            style={{
              gridTemplateColumns: `72px repeat(${roomsAvailable}, minmax(140px, 1fr))`,
              gridTemplateRows: `auto repeat(${visibleSlotCount}, ${SLOT_HEIGHT}px)`,
            }}
          >
            {/* Header row */}
            <div
              className="border-b border-r border-[#d8e2ff] bg-[#f0f4ff] px-2 py-2 text-xs font-bold uppercase text-[#2d3d7a]"
              style={{ gridRow: 1, gridColumn: 1 }}
            >
              Time
            </div>
            {Array.from({ length: roomsAvailable }, (_, i) => (
              <div
                key={i}
                className="whitespace-nowrap border-b border-r border-[#d8e2ff] bg-[#f0f4ff] px-2 py-2 text-center text-xs font-bold uppercase text-[#2d3d7a] last:border-r-0"
                style={{ gridRow: 1, gridColumn: i + 2 }}
              >
                {getRoomLabel(roomNames, i)}
              </div>
            ))}

            {/* Time slot rows (background cells) */}
            {Array.from({ length: visibleSlotCount }, (_, i) => {
              const slotIndex = minSlot + i;
              const showLabel = slotIndex % 2 === 0;
              const gridRow = i + 2; // +2 because header is row 1
              return (
                <div key={`time-${slotIndex}`} className="contents">
                  <div
                    className={`flex items-center justify-end border-b border-r border-[#e5e7eb] px-1 text-[11px] leading-none text-[#888] ${
                      slotIndex % 4 === 0 ? "bg-[#f9fafb]" : "bg-white"
                    }`}
                    style={{ gridRow, gridColumn: 1 }}
                  >
                    {showLabel ? formatTimeLabel(slotIndex) : ""}
                  </div>
                  {Array.from({ length: roomsAvailable }, (_, roomIdx) => (
                    <div
                      key={roomIdx}
                      className={`border-b border-r border-[#e5e7eb] last:border-r-0 ${
                        slotIndex % 4 === 0 ? "bg-[#f9fafb]" : "bg-white"
                      }`}
                      style={{ gridRow, gridColumn: roomIdx + 2 }}
                    />
                  ))}
                </div>
              );
            })}

            {/* Presentation blocks (placed via grid-row/grid-column) */}
            {scheduledForDay.map((pres) => {
              if (pres.room === null || !pres.timeframe) return null;
              const start = parseBackendDateTime(pres.timeframe.start_time);
              const end = parseBackendDateTime(pres.timeframe.end_time);
              const startMinutes = start.getUTCHours() * 60 + start.getUTCMinutes();
              const endMinutes = end.getUTCHours() * 60 + end.getUTCMinutes();
              const startSlotRaw = (startMinutes - 9 * 60) / 15;
              const endSlotRaw = (endMinutes - 9 * 60) / 15;

              // Convert to grid row (1-indexed, +2 for header row offset)
              const gridRowStart = Math.floor(startSlotRaw - minSlot) + 2;
              const gridRowEnd = Math.ceil(endSlotRaw - minSlot) + 2;
              const gridCol = pres.room + 2; // +2 for time column offset (col 1)

              // Sub-slot positioning for non-15-minute-aligned times
              const fracStart = (startSlotRaw - minSlot) - Math.floor(startSlotRaw - minSlot);
              const verticalInset = 1;
              const topOffset = fracStart * SLOT_HEIGHT + verticalInset;
              const blockHeight = Math.max(8, (endSlotRaw - startSlotRaw) * SLOT_HEIGHT - verticalInset * 2);
              const durationSlots = endSlotRaw - startSlotRaw;

              const color = colorMap.get(pres.id) ?? BLOCK_COLORS[0];

              const isBeingDragged = dragState?.presentation.id === pres.id;

              return (
                <div
                  key={pres.id}
                  onPointerDown={(e) => handleBlockPointerDown(e, pres)}
                  className={`z-10 mx-[1px] overflow-hidden rounded-md px-1.5 py-0.5 text-left shadow-sm transition hover:brightness-110 hover:shadow-md ${isBeingDragged ? "opacity-30" : ""}`}
                  style={{
                    gridRow: `${gridRowStart} / ${gridRowEnd}`,
                    gridColumn: gridCol,
                    backgroundColor: color.bg,
                    color: color.text,
                    position: "relative",
                    top: `${topOffset}px`,
                    height: `${blockHeight}px`,
                    alignSelf: "start",
                    touchAction: "none",
                    cursor: isDragging ? "grabbing" : "grab",
                  }}
                  title={`${pres.title} (${pres.minutes} min)\n${pres.presenterNames.join(", ")}`}
                >
                  <div className="truncate text-xs font-semibold leading-tight">{pres.title}</div>
                  {durationSlots > 1 ? (
                    <div className="truncate text-[10px] leading-tight opacity-80">
                      {pres.presenterNames.join(", ") || "No presenters"}
                    </div>
                  ) : null}
                  {durationSlots > 2 ? (
                    <div className="truncate text-[10px] leading-tight opacity-60">
                      {pres.minutes} min
                    </div>
                  ) : null}
                </div>
              );
            })}

            {/* Snap-target highlight during drag */}
            {isDragging && dragState?.snapTarget ? (() => {
              const { room, minuteInDay } = dragState.snapTarget;
              const minuteFromDayStart = minuteInDay - 9 * 60;
              const slotFloat = minuteFromDayStart / 15;
              const relativeSlot = slotFloat - minSlot;
              const durationSlots = dragState.presentation.minutes / 15;
              const gridRowStart = Math.floor(relativeSlot) + 2;
              const gridRowEnd = Math.ceil(relativeSlot + durationSlots) + 2;
              const gridCol = room + 2;
              const fracStart = relativeSlot - Math.floor(relativeSlot);
              const topOffset = fracStart * SLOT_HEIGHT;
              const blockHeight = durationSlots * SLOT_HEIGHT;
              const conflict = dragState.conflict;
              const isBlocked = conflict?.blocked === true;
              const isWarning = conflict !== null && !conflict.blocked;

              return (
                <div
                  style={{
                    gridRow: `${gridRowStart} / ${gridRowEnd}`,
                    gridColumn: gridCol,
                    position: "relative",
                    top: `${topOffset}px`,
                    height: `${blockHeight}px`,
                    alignSelf: "start",
                    pointerEvents: "none",
                  }}
                  className={`z-20 m-[1px] rounded-md border-2 border-dashed ${
                    isBlocked
                      ? "border-[#c62828] bg-[#c62828]/10"
                      : isWarning
                        ? "border-[#e68a00] bg-[#e68a00]/10"
                        : "border-[#2e7d32] bg-[#2e7d32]/10"
                  }`}
                >
                  {conflict ? (
                    <div className={`truncate px-1.5 py-0.5 text-[10px] font-semibold ${isBlocked ? "text-[#c62828]" : "text-[#b36b00]"}`}>
                      {isWarning ? "Warning: " : ""}{conflict.message}
                    </div>
                  ) : null}
                </div>
              );
            })() : null}
          </div>
        </div>

        {/* Unscheduled side panel */}
        {unscheduled.length > 0 ? (
          <div className="max-h-[calc(100vh-180px)] w-56 shrink-0 overflow-hidden rounded-lg border border-[#d8e2ff] bg-white">
            <div className="border-b border-[#d8e2ff] bg-[#f0f4ff] px-3 py-2 text-xs font-bold uppercase tracking-wide text-[#2d3d7a]">
              Unscheduled ({unscheduled.length})
            </div>
            <div className="h-full overflow-y-auto p-2">
              <div className="space-y-1.5">
                {unscheduled.map((pres) => {
                  const color = colorMap.get(pres.id) ?? BLOCK_COLORS[0];
                  return (
                    <div
                      key={pres.id}
                      onPointerDown={(e) => handleUnscheduledPointerDown(e, pres)}
                      className="rounded-md px-2 py-1.5 text-left shadow-sm transition hover:brightness-110 hover:shadow-md"
                      style={{
                        backgroundColor: color.bg,
                        color: color.text,
                        touchAction: "none",
                        cursor: isDragging ? "grabbing" : "grab",
                      }}
                    >
                      <div className="truncate text-xs font-semibold leading-tight">{pres.title}</div>
                      <div className="truncate text-[10px] leading-tight opacity-80">
                        {pres.minutes} min &mdash; {pres.departmentName || "No dept"}
                      </div>
                      {pres.presenterNames.length > 0 ? (
                        <div className="truncate text-[10px] leading-tight opacity-60">
                          {pres.presenterNames.join(", ")}
                        </div>
                      ) : null}
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        ) : null}
        </div>
      ) : null}

      {/* Ghost block following cursor during drag */}
      {isDragging && dragState ? (() => {
        const color = colorMap.get(dragState.presentation.id) ?? BLOCK_COLORS[0];
        const durationSlots = Math.ceil(dragState.presentation.minutes / 15);
        const blockHeight = durationSlots * SLOT_HEIGHT;
        const snap = dragState.snapTarget;
        const timeLabel = snap ? formatMinuteTime(snap.minuteInDay) : null;
        const endMinute = snap ? snap.minuteInDay + dragState.presentation.minutes : null;
        const endLabel = endMinute !== null ? formatMinuteTime(endMinute) : null;

        return (
          <>
            <div
              style={{
                position: "fixed",
                left: dragState.currentX - dragState.offsetX,
                top: dragState.currentY - dragState.offsetY,
                width: 160,
                height: blockHeight,
                backgroundColor: color.bg,
                color: color.text,
                opacity: 0.7,
                pointerEvents: "none",
                zIndex: 9999,
              }}
              className="overflow-hidden rounded-md px-1.5 py-0.5 shadow-lg"
            >
              <div className="truncate text-xs font-semibold leading-tight">
                {dragState.presentation.title}
              </div>
              <div className="truncate text-[10px] leading-tight opacity-80">
                {dragState.presentation.presenterNames.join(", ") || "No presenters"}
              </div>
            </div>
            {timeLabel ? (
              <div
                style={{
                  position: "fixed",
                  left: dragState.currentX - dragState.offsetX + 164,
                  top: dragState.currentY - dragState.offsetY,
                  pointerEvents: "none",
                  zIndex: 10000,
                }}
                className="whitespace-nowrap rounded bg-[#1e293b] px-2 py-1 text-xs font-semibold text-white shadow-lg"
              >
                {timeLabel} – {endLabel}
              </div>
            ) : null}
          </>
        );
      })() : null}

      {/* Unscheduled presentations (tab content) */}
      {!isLoadingSchedule && selectedDay === "unscheduled" ? (
        <div className="rounded-xl border border-[#d8e2ff] bg-white p-4">
          {unscheduled.length > 0 ? (
            <div className="space-y-2">
              {unscheduled.map((pres) => (
                <div
                  key={pres.id}
                  className="flex items-center justify-between rounded-lg border border-[#e5e7eb] bg-[#fefefe] px-4 py-2.5"
                >
                  <div>
                    <span className="text-sm font-semibold text-[#111]">{pres.title}</span>
                    <span className="ml-2 text-xs text-[#666]">
                      ({pres.minutes} min) &mdash; {pres.departmentName || "No dept"}
                    </span>
                    {pres.presenterNames.length > 0 ? (
                      <span className="ml-2 text-xs text-[#888]">
                        {pres.presenterNames.join(", ")}
                      </span>
                    ) : null}
                  </div>
                  <button
                    type="button"
                    onClick={() => handleOpenEditModal(pres)}
                    className="rounded-md border border-[#0f33a8] bg-white px-3 py-1 text-xs font-semibold text-[#0f33a8] transition hover:bg-[#eef3ff]"
                  >
                    Assign
                  </button>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-sm text-[#555]">All presentations have been scheduled.</p>
          )}
        </div>
      ) : null}

      {/* No presentations message */}
      {!isLoadingSchedule && selectedSymposiumId && presentations.length === 0 && !message ? (
        <p className="text-sm text-[#555]">No presentations found for this symposium.</p>
      ) : null}

      {/* Edit modal */}
      {editingPresentation ? (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 px-4"
          onClick={() => setEditingPresentation(null)}
        >
          <div
            className="w-full max-w-lg overflow-hidden rounded-xl border border-[#d6b676] bg-white shadow-2xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="bg-[#1635a7] px-5 py-3 text-lg font-semibold text-white">
              {editingPresentation.timeframe
                ? timeLabel(editingPresentation.timeframe.start_time, editingPresentation.timeframe.end_time)
                : "Assign Time & Room"}
            </div>
            <div className="space-y-4 px-5 py-4">
              {/* Read-only info */}
              <div>
                <h2 className="text-xl font-extrabold text-[#111]">{editingPresentation.title}</h2>
                <div className="mt-1 space-y-0.5 text-sm text-[#333]">
                  <p>
                    <span className="font-semibold">Department:</span> {editingPresentation.departmentName || "N/A"}
                  </p>
                  <p>
                    <span className="font-semibold">Presenters:</span>{" "}
                    {editingPresentation.presenterNames.length > 0
                      ? editingPresentation.presenterNames.join(", ")
                      : "None"}
                  </p>
                  <p>
                    <span className="font-semibold">Duration:</span> {editingPresentation.minutes} minutes
                  </p>
                </div>
              </div>

              {/* Room selector */}
              <div>
                <label className="block text-xs font-bold uppercase tracking-wide text-[#2d3d7a]">
                  Room
                </label>
                <select
                  value={editRoom}
                  onChange={(e) => setEditRoom(e.target.value)}
                  className={fieldClass + " mt-1"}
                >
                  {Array.from({ length: roomsAvailable }, (_, i) => (
                    <option key={i} value={String(i)}>
                      {getRoomLabel(roomNames, i)}
                    </option>
                  ))}
                </select>
              </div>

              {/* Start time */}
              <div>
                <label className="block text-xs font-bold uppercase tracking-wide text-[#2d3d7a]">
                  Start Time
                </label>
                <input
                  type="datetime-local"
                  value={editStartTime}
                  onChange={(e) => setEditStartTime(e.target.value)}
                  step={900}
                  className={fieldClass + " mt-1"}
                />
              </div>

              {/* End time (auto-calculated) */}
              {editEndTimeDisplay ? (
                <p className="text-sm text-[#555]">
                  <span className="font-semibold">End Time:</span> {editEndTimeDisplay} (auto-calculated from duration)
                </p>
              ) : null}

              {/* Error message */}
              {assignmentMessage ? (
                <p className="text-sm font-semibold text-[#9a1f1f]">{assignmentMessage}</p>
              ) : null}

              {/* Actions */}
              <div className="flex gap-3 pt-1">
                <button
                  type="button"
                  onClick={handleSaveAssignment}
                  disabled={isSavingAssignment}
                  className="rounded-lg bg-[#0f33a8] px-5 py-2 text-sm font-semibold text-white transition hover:bg-[#1237af] disabled:opacity-50"
                >
                  Apply
                </button>
                <button
                  type="button"
                  onClick={() => setEditingPresentation(null)}
                  className="rounded-lg border border-[#0f33a8] bg-white px-5 py-2 text-sm font-semibold text-[#0f33a8] transition hover:bg-[#eef3ff]"
                >
                  Cancel
                </button>
              </div>
            </div>
          </div>
        </div>
      ) : null}

      {/* Scheduler failure popup — appears whenever the scheduler leaves presentations unscheduled. */}
      {schedulerFailure ? (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 px-4"
          onClick={() => setSchedulerFailure(null)}
        >
          <div
            className="w-full max-w-lg overflow-hidden rounded-xl border border-[#d6b676] bg-white shadow-2xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="bg-[#9a1f1f] px-5 py-3 text-lg font-semibold text-white">
              Schedule incomplete
            </div>
            <div className="space-y-4 px-5 py-4">
              <p className="text-sm text-[#111]">
                The scheduler could not place{" "}
                <span className="font-bold">{schedulerFailure.unscheduledCount}</span>{" "}
                presentation{schedulerFailure.unscheduledCount !== 1 ? "s" : ""}. Try relaxing one or more of the constraints below, then re-run.
              </p>

              <div className="space-y-1">
                {([
                  { key: "professorAvailability" as const, label: "Professor availability" },
                  { key: "studentAvailability" as const, label: "Student availability" },
                  { key: "sameClassSameRoom" as const, label: "Same class \u2192 same room" },
                ]).map(({ key, label }) => (
                  <div
                    key={key}
                    className="flex items-center justify-between gap-2 rounded-md border border-[#e5eaff] px-3 py-2"
                  >
                    <span className="text-sm font-medium text-[#111]">{label}</span>
                    <div className="flex shrink-0 overflow-hidden rounded-md border border-[#d0d8f0]">
                      {(["off", "soft", "hard"] as const).map((mode) => (
                        <button
                          key={mode}
                          type="button"
                          onClick={() => setConstraints((prev) => ({ ...prev, [key]: mode }))}
                          className={`w-[42px] py-1 text-[10px] font-semibold transition ${
                            constraints[key] === mode
                              ? mode === "off"
                                ? "bg-[#e0e0e0] text-[#555]"
                                : mode === "soft"
                                  ? "bg-[#fff3cd] text-[#856404]"
                                  : "bg-[#1635a7] text-white"
                              : "bg-white text-[#aaa] hover:bg-[#f5f5f5]"
                          }`}
                        >
                          {mode === "off" ? "Off" : mode === "soft" ? "Soft" : "Hard"}
                        </button>
                      ))}
                    </div>
                  </div>
                ))}
              </div>

              <p className="text-[11px] text-[#888]">
                Soft constraints are preferred but can be violated; Off removes the constraint entirely.
              </p>

              <div className="flex gap-3 pt-1">
                <button
                  type="button"
                  onClick={() => {
                    setSchedulerFailure(null);
                    void handleRunScheduler(true);
                  }}
                  disabled={isRunningScheduler}
                  className="rounded-lg bg-[#0f33a8] px-5 py-2 text-sm font-semibold text-white transition hover:bg-[#1237af] disabled:opacity-50"
                >
                  {isRunningScheduler ? "Re-running..." : "Re-run scheduler"}
                </button>
                <button
                  type="button"
                  onClick={() => setSchedulerFailure(null)}
                  className="rounded-lg border border-[#0f33a8] bg-white px-5 py-2 text-sm font-semibold text-[#0f33a8] transition hover:bg-[#eef3ff]"
                >
                  Dismiss
                </button>
              </div>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
