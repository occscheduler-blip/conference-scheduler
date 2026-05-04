"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type {
  SchedulePresentation,
  SymposiumOption,
  Timeframe,
} from "./types";
import {
  totalSlots,
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
import { fetchSymposiumSchedule } from "../lib/useSymposiumSchedule";

/** Convert a Date to a datetime-local input value (YYYY-MM-DDTHH:MM). */
function toDatetimeLocal(d: Date): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())}T${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}`;
}

import { FIELD_CLASS as fieldClass } from "../lib/styles";
import {
  DEPARTMENT_BASE_COLORS,
  COLOR_SHADES,
  rgbToHex,
  getTextColor,
  buildPresentationColorMap,
} from "../lib/scheduleColors";
import { ScheduleGrid, getRoomLabel, SLOT_HEIGHT, type GridBlock } from "../lib/ScheduleGrid";

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
  const [symposiumName, setSymposiumName] = useState("");
  const [defaultBuffer, setDefaultBuffer] = useState(0);
  const [isLoadingSchedule, setIsLoadingSchedule] = useState(false);
  const [selectedDay, setSelectedDay] = useState("");
  const [message, setMessage] = useState<string | null>(null);

  // Scheduler
  const [isRunningScheduler, setIsRunningScheduler] = useState(false);
  const [schedulerMessage, setSchedulerMessage] = useState<string | null>(null);
  const [schedulerFailure, setSchedulerFailure] = useState<{ unscheduledCount: number; diagnostics: string[]; suggestions: string[] } | null>(null);
  const [debuggerFindings, setDebuggerFindings] = useState<string[] | null>(null);
  const [debuggerRecommendations, setDebuggerRecommendations] = useState<Partial<Record<"professorAvailability" | "studentAvailability" | "sameClassSameRoom" | "roomConflicts" | "personConflicts", "off" | "soft" | "hard">>>({});
  const [debugBestAssignments, setDebugBestAssignments] = useState<{ presentation_id: string; room_index: number; start: string; end: string }[]>([]);

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
        const schedule = await fetchSymposiumSchedule(symposiumId, {
          mode: "draft",
          includeProfessors: true,
          authHeaders,
        });

        setSymposiumTimeframes(schedule.symposiumTimeframes);
        const parsedRooms = Number(schedule.symposium?.rooms_available ?? 1);
        setRoomsAvailable(Number.isFinite(parsedRooms) && parsedRooms > 0 ? Math.floor(parsedRooms) : 1);
        setRoomNames(schedule.symposium?.room_names ?? []);
        setSymposiumName(schedule.symposium?.name ?? "");
        setDefaultBuffer(Number(schedule.symposium?.default_buffer ?? 0));

        if (schedule.departments.length === 0) {
          setPresentations([]);
          const days = Array.from(
            new Set(schedule.symposiumTimeframes.map((tf) => dayKey(parseBackendDateTime(tf.start_time))))
          );
          setSelectedDay(days[0] ?? "");
          return;
        }

        // Department lookup
        const deptById = new Map(schedule.departments.map((d) => [d.id, d]));
        const deptIdByClassId = new Map(schedule.classes.map((c) => [c.id, c.department_id]));

        // Professor IDs grouped by class_id (all professors in a class are resources for all its presentations)
        const professorIdsByClass = new Map<string, string[]>();
        const personNameById = new Map<string, string>();
        for (const prof of schedule.professors) {
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
          schedule.students
            .filter((r): r is { id: string; name: string } => Boolean(r.id && r.name?.trim()))
            .map((r) => [normalizeId(r.id), r.name.trim()])
        );

        // Earliest timeframe wins per presentation
        const timeframeByPresentation = new Map<string, Timeframe>();
        for (const tf of schedule.presentationTimeframes) {
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

        const presentationRows: SchedulePresentation[] = schedule.presentations
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
              room: row.temporary_room ?? null,
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
        for (const row of schedule.students) {
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

        const days = Array.from(
          new Set(schedule.symposiumTimeframes.map((tf) => dayKey(parseBackendDateTime(tf.start_time))))
        );
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

  // Color map by presentation id (department-based, consistent colors)
  const colorMap = useMemo(() => buildPresentationColorMap(presentations), [presentations]);

  // Blocks shaped for ScheduleGrid
  const gridBlocks = useMemo<GridBlock[]>(() => {
    const defaultColor = COLOR_SHADES[0][0];
    return scheduledForDay
      .filter((p): p is typeof p & { room: number; timeframe: NonNullable<typeof p.timeframe> } =>
        p.room !== null && p.timeframe !== null
      )
      .map((p) => ({
        id: p.id,
        timeframe: p.timeframe,
        roomIndex: p.room,
        title: p.title,
        presenterNames: p.presenterNames,
        color: colorMap.get(p.id) ?? { bg: rgbToHex(defaultColor.r, defaultColor.g, defaultColor.b), text: getTextColor(defaultColor) },
        durationMinutes: p.minutes,
      }));
  }, [scheduledForDay, colorMap]);

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
  const handleRunScheduler = async (skipConfirm: boolean = false, debugMode: boolean = false) => {
    if (!selectedSymposiumId) return;
    if (!skipConfirm && !window.confirm("This will regenerate the schedule. Existing assignments will be replaced. Continue?")) return;

    setIsRunningScheduler(true);
    setSchedulerMessage(debugMode ? "Running exhaustive constraint analysis (up to 10 minutes)..." : "Starting scheduler...");
    setSchedulerFailure(null);
    setDebuggerFindings(null);
    setDebuggerRecommendations({});
    setDebugBestAssignments([]);
    try {
      const { raw: startRaw } = await apiPost("/api/events/schedule", {
        symposium_id: selectedSymposiumId,
        debug_mode: debugMode,
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
      setSchedulerMessage(debugMode ? "Testing all constraint combinations... (up to 10 minutes)" : "Scheduler running...");

      const POLL_TIMEOUT_MS = debugMode ? 10 * 60 * 1000 : 5 * 60 * 1000;
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
      const diagnostics = (raw.diagnostics as string[]) ?? [];
      const suggestions = (raw.suggestions as string[]) ?? [];
      const rawDebugBest = (raw.debug_best_assignments as { presentation_id: string; room_index: number; start: string; end: string }[]) ?? [];
      setSchedulerMessage(
        `Schedule ${status}. ${assignments.length} assigned, ${unscheduledIds.length} unscheduled.`
      );
      setPendingChanges(new Map());
      setBulkSaveMessage(null);
      await fetchScheduleData(selectedSymposiumId);
      if (unscheduledIds.length > 0) {
        const hints = suggestions.filter((s) => s.startsWith("[Debugger]")).map((s) => s.replace(/^\[Debugger\]\s*/, ""));
        const regularSuggestions = suggestions.filter((s) => !s.startsWith("[Debugger]"));
        setSchedulerFailure({ unscheduledCount: unscheduledIds.length, diagnostics, suggestions: regularSuggestions });
        if (hints.length > 0) {
          setDebuggerFindings(hints);
          if (rawDebugBest.length > 0) setDebugBestAssignments(rawDebugBest);
          const recSigMap = [
            { key: "professorAvailability" as const, signal: "professor availability" },
            { key: "studentAvailability" as const, signal: "student availability" },
            { key: "sameClassSameRoom" as const, signal: "same class" },
            { key: "roomConflicts" as const, signal: "room conflicts" },
            { key: "personConflicts" as const, signal: "person conflicts" },
          ] as const;
          const recs: Partial<Record<"professorAvailability" | "studentAvailability" | "sameClassSameRoom" | "roomConflicts" | "personConflicts", "off" | "soft" | "hard">> = {};
          for (const hint of hints) {
            const lower = hint.toLowerCase();
            for (const { key, signal } of recSigMap) {
              if (lower.includes(signal)) {
                const match = lower.match(/\bto (soft|hard|off)\b/);
                if (match) recs[key] = match[1] as "off" | "soft" | "hard";
              }
            }
          }
          setDebuggerRecommendations(recs);
        }
      }
    } catch (error) {
      const msg = error instanceof Error ? error.message : "Unknown error";
      setSchedulerMessage(`Error: ${msg}`);
    } finally {
      setIsRunningScheduler(false);
    }
  };

  const [isAddingRoom, setIsAddingRoom] = useState(false);
  const [pendingRooms, setPendingRooms] = useState<number | null>(null);
  const [isApplyingRooms, setIsApplyingRooms] = useState(false);
  const [pendingBuffer, setPendingBuffer] = useState<number | null>(null);
  const [isApplyingBuffer, setIsApplyingBuffer] = useState(false);

  const handleApplyBuffer = async () => {
    if (!selectedSymposiumId || pendingBuffer === null) return;
    setIsApplyingBuffer(true);
    try {
      await apiPut("/api/events/update_presentation_buffers", {
        symposium_id: selectedSymposiumId,
        buffer_minutes: pendingBuffer,
      }, authHeaders);
      await apiPut("/api/events/update_symposium", {
        symposium_id: selectedSymposiumId,
        symposium_name: symposiumName,
        rooms_available: roomsAvailable,
        room_names: roomNames,
        default_buffer: pendingBuffer,
        timeframes: symposiumTimeframes.map((tf) => ({
          start_time: tf.start_time,
          end_time: tf.end_time,
        })),
      }, authHeaders);
      setDefaultBuffer(pendingBuffer);
      setPendingBuffer(null);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Failed to update buffers.");
    } finally {
      setIsApplyingBuffer(false);
    }
  };

  const handleApplyRooms = async () => {
    if (!selectedSymposiumId || pendingRooms === null) return;
    setIsApplyingRooms(true);
    try {
      await apiPut("/api/events/update_symposium", {
        symposium_id: selectedSymposiumId,
        symposium_name: symposiumName,
        rooms_available: pendingRooms,
        room_names: roomNames,
        default_buffer: defaultBuffer,
        timeframes: symposiumTimeframes.map((tf) => ({
          start_time: tf.start_time,
          end_time: tf.end_time,
        })),
      }, authHeaders);
      setRoomsAvailable(pendingRooms);
      setPendingRooms(null);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Failed to update rooms.");
    } finally {
      setIsApplyingRooms(false);
    }
  };

  const handleAddRoom = async () => {
    if (!selectedSymposiumId) return;
    setIsAddingRoom(true);
    try {
      const newCount = roomsAvailable + 1;
      await apiPut("/api/events/update_symposium", {
        symposium_id: selectedSymposiumId,
        symposium_name: symposiumName,
        rooms_available: newCount,
        room_names: roomNames,
        default_buffer: defaultBuffer,
        timeframes: symposiumTimeframes.map((tf) => ({
          start_time: tf.start_time,
          end_time: tf.end_time,
        })),
      }, authHeaders);
      setRoomsAvailable(newCount);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Failed to add room.");
    } finally {
      setIsAddingRoom(false);
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

  const [isPublishing, setIsPublishing] = useState(false);
  const [publishMessage, setPublishMessage] = useState<string | null>(null);

  const handlePublishSchedule = async () => {
    if (!selectedSymposiumId) return;
    if (!window.confirm("Publish this schedule? This will update the live schedule that attendees see.")) return;
    setIsPublishing(true);
    setPublishMessage(null);
    try {
      await apiPost("/api/events/publish_schedule", { symposium_id: selectedSymposiumId }, authHeaders);
      setPublishMessage("Schedule published successfully.");
    } catch (error) {
      const msg = error instanceof Error ? error.message : "Unknown error";
      setPublishMessage(`Error: ${msg}`);
    } finally {
      setIsPublishing(false);
    }
  };

  const [exportOpen, setExportOpen] = useState(false);

  const handleExportIcal = () => {
    const scheduled = presentations.filter((p) => p.room !== null && p.timeframe);
    if (scheduled.length === 0) return;

    const pad = (n: number) => String(n).padStart(2, "0");
    const toIcalDate = (d: Date) =>
      `${d.getUTCFullYear()}${pad(d.getUTCMonth() + 1)}${pad(d.getUTCDate())}T${pad(d.getUTCHours())}${pad(d.getUTCMinutes())}00Z`;

    const events = scheduled.map((p) => {
      const start = toIcalDate(parseBackendDateTime(p.timeframe!.start_time));
      const end = toIcalDate(parseBackendDateTime(p.timeframe!.end_time));
      const room = getRoomLabel(roomNames, p.room!);
      const presenters = p.presenterNames.join(", ") || "TBD";
      const desc = `Presenters: ${presenters}\\nDepartment: ${p.departmentName}`;
      return [
        "BEGIN:VEVENT",
        `DTSTART:${start}`,
        `DTEND:${end}`,
        `SUMMARY:${p.title}`,
        `LOCATION:${room}`,
        `DESCRIPTION:${desc}`,
        "END:VEVENT",
      ].join("\r\n");
    });

    const ical = [
      "BEGIN:VCALENDAR",
      "VERSION:2.0",
      "PRODID:-//Conference Scheduler//EN",
      "CALSCALE:GREGORIAN",
      ...events,
      "END:VCALENDAR",
    ].join("\r\n");

    const blob = new Blob([ical], { type: "text/calendar;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "schedule.ics";
    a.click();
    URL.revokeObjectURL(url);
  };

  const handleExportXlsx = async () => {
    const scheduled = presentations.filter((p) => p.room !== null && p.timeframe);
    if (scheduled.length === 0) return;

    const XLSX = await import("xlsx");

    const rows = scheduled
      .slice()
      .sort((a, b) => {
        const ta = parseBackendDateTime(a.timeframe!.start_time).getTime();
        const tb = parseBackendDateTime(b.timeframe!.start_time).getTime();
        return ta !== tb ? ta - tb : (a.room ?? 0) - (b.room ?? 0);
      })
      .map((p) => {
        const opts = { hour: "numeric", minute: "2-digit", timeZone: "UTC" } as const;
        const start = parseBackendDateTime(p.timeframe!.start_time);
        const end = parseBackendDateTime(p.timeframe!.end_time);
        return {
          Day: dayLabel(dayKey(start)),
          "Start Time": start.toLocaleTimeString([], opts),
          "End Time": end.toLocaleTimeString([], opts),
          Room: getRoomLabel(roomNames, p.room!),
          Title: p.title,
          Presenters: p.presenterNames.join("; "),
          Department: p.departmentName,
        };
      });

    const ws = XLSX.utils.json_to_sheet(rows);
    const wb = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(wb, ws, "Schedule");
    XLSX.writeFile(wb, "schedule.xlsx");
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

      {/* Generate / Publish Schedule buttons */}
      {selectedSymposiumId ? (
        <div className="flex flex-wrap items-center gap-4">
          <button
            type="button"
            onClick={() => handleRunScheduler()}
            disabled={isRunningScheduler}
            className="rounded-lg bg-[#1b6e2b] px-6 py-2.5 text-base font-semibold text-white transition hover:bg-[#15572b] disabled:opacity-50"
          >
            {isRunningScheduler ? "Generating..." : "Generate Schedule"}
          </button>
          <button
            type="button"
            onClick={() => void handlePublishSchedule()}
            disabled={isPublishing}
            className="rounded-lg bg-[#1635a7] px-6 py-2.5 text-base font-semibold text-white transition hover:bg-[#0b2a8d] disabled:opacity-50"
          >
            {isPublishing ? "Publishing..." : "Publish Schedule"}
          </button>
          <div className="relative">
            <button
              type="button"
              onClick={() => setExportOpen((v) => !v)}
              disabled={presentations.filter((p) => p.room !== null && p.timeframe).length === 0}
              className="flex items-center gap-2 rounded-lg border border-[#1635a7] bg-white px-6 py-2.5 text-base font-semibold text-[#1635a7] transition hover:bg-[#eef2ff] disabled:opacity-50"
            >
              Export
              <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" className={`h-4 w-4 transition ${exportOpen ? "rotate-180" : ""}`}>
                <path fillRule="evenodd" d="M5.22 8.22a.75.75 0 0 1 1.06 0L10 11.94l3.72-3.72a.75.75 0 1 1 1.06 1.06l-4.25 4.25a.75.75 0 0 1-1.06 0L5.22 9.28a.75.75 0 0 1 0-1.06Z" clipRule="evenodd" />
              </svg>
            </button>
            {exportOpen ? (
              <>
                <div className="fixed inset-0 z-20" onClick={() => setExportOpen(false)} />
                <div className="absolute left-0 top-full z-30 mt-1 w-40 overflow-hidden rounded-lg border border-[#d8e2ff] bg-white shadow-lg">
                  <button
                    type="button"
                    onClick={() => { setExportOpen(false); void handleExportXlsx(); }}
                    className="w-full px-4 py-2.5 text-left text-sm font-medium text-[#111] hover:bg-[#eef2ff]"
                  >
                    Export as XLSX
                  </button>
                  <button
                    type="button"
                    onClick={() => { setExportOpen(false); handleExportIcal(); }}
                    className="w-full px-4 py-2.5 text-left text-sm font-medium text-[#111] hover:bg-[#eef2ff]"
                  >
                    Export as iCal
                  </button>
                </div>
              </>
            ) : null}
          </div>
          {schedulerMessage ? (
            <p className={`text-sm font-medium ${schedulerMessage.startsWith("Error") ? "text-[#9a1f1f]" : "text-[#1b6e2b]"}`}>
              {schedulerMessage}
            </p>
          ) : null}
          {publishMessage ? (
            <p className={`text-sm font-medium ${publishMessage.startsWith("Error") ? "text-[#9a1f1f]" : "text-[#1b6e2b]"}`}>
              {publishMessage}
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
            <ScheduleGrid
              roomsAvailable={roomsAvailable}
              roomNames={roomNames}
              minSlot={minSlot}
              maxSlot={maxSlot}
              blocks={gridBlocks}
              gridRef={gridRef}
              onBlockPointerDown={(e, id) => {
                const pres = scheduledForDay.find((p) => p.id === id);
                if (pres) handleBlockPointerDown(e, pres);
              }}
              draggingId={dragState?.presentation.id ?? null}
              isDragging={isDragging}
              snapTarget={
                isDragging && dragState?.snapTarget
                  ? {
                      room: dragState.snapTarget.room,
                      minuteInDay: dragState.snapTarget.minuteInDay,
                      durationMinutes: dragState.presentation.minutes,
                      conflict: dragState.conflict,
                    }
                  : null
              }
            />
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
                    const defaultColor = COLOR_SHADES[0][0];
                    const color = colorMap.get(pres.id) ?? { bg: rgbToHex(defaultColor.r, defaultColor.g, defaultColor.b), text: getTextColor(defaultColor) };
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
        const defaultColor = COLOR_SHADES[0][0];
        const color = colorMap.get(dragState.presentation.id) ?? { bg: rgbToHex(defaultColor.r, defaultColor.g, defaultColor.b), text: getTextColor(defaultColor) };
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
      {schedulerFailure ? (() => {
        const titleById = new Map(presentations.map((p) => [p.id, p.title]));
        const uuidPattern = /[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/i;
        const humanize = (msg: string): string => {
          const match = msg.match(uuidPattern);
          if (!match) return msg;
          const title = titleById.get(match[0]);
          return title ? msg.replace(match[0], `"${title}"`) : msg;
        };

        const allSuggestions = schedulerFailure.suggestions ?? [];
        const regularSuggestions = allSuggestions;

        const constraintMap = [
          { key: "professorAvailability" as const, label: "Professor availability", signal: "professor availability" },
          { key: "studentAvailability" as const, label: "Student availability", signal: "student availability" },
          { key: "sameClassSameRoom" as const, label: "Same class \u2192 same room", signal: "same class" },
        ] as const;

        const renderToggle = (key: "professorAvailability" | "studentAvailability" | "sameClassSameRoom", label: string) => (
          <div key={key} className="flex items-center justify-between gap-2 rounded-md border border-[#d0d8f0] bg-white px-3 py-1.5">
            <span className="text-xs font-medium text-[#1a3580]">{label}</span>
            <div className="flex shrink-0 overflow-hidden rounded border border-[#d0d8f0]">
              {(["off", "soft", "hard"] as const).map((mode) => (
                <button
                  key={mode}
                  type="button"
                  onClick={() => setConstraints((prev) => ({ ...prev, [key]: mode }))}
                  className={`w-[42px] py-1 text-[10px] font-semibold transition ${
                    constraints[key] === mode
                      ? mode === "off" ? "bg-[#e0e0e0] text-[#555]"
                        : mode === "soft" ? "bg-[#fff3cd] text-[#856404]"
                        : "bg-[#1635a7] text-white"
                      : "bg-white text-[#aaa] hover:bg-[#f5f5f5]"
                  }`}
                >
                  {mode === "off" ? "Off" : mode === "soft" ? "Soft" : "Hard"}
                </button>
              ))}
            </div>
          </div>
        );

        const needsBuffer = regularSuggestions.some((s) => /buffer/i.test(s));

        const mentionedConstraints = constraintMap.filter(({ signal }) =>
          regularSuggestions.some((s) => s.toLowerCase().includes(signal))
        );
        const hasQuickActions = true;

        return (
          <div
            className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 px-4"
            onClick={() => setSchedulerFailure(null)}
          >
            <div
              className="flex w-full max-w-lg flex-col overflow-hidden rounded-xl bg-white shadow-2xl"
              style={{ maxHeight: "90vh" }}
              onClick={(e) => e.stopPropagation()}
            >
              {/* Header */}
              <div className="shrink-0 bg-[#9a1f1f] px-5 py-3">
                <p className="text-base font-semibold text-white">Schedule incomplete</p>
                <p className="text-sm text-red-200">
                  {schedulerFailure.unscheduledCount} presentation{schedulerFailure.unscheduledCount !== 1 ? "s" : ""} could not be placed
                </p>
              </div>

              {/* Scrollable body */}
              <div className="space-y-5 overflow-y-auto px-5 py-4">

                {/* Why it failed */}
                {(schedulerFailure.diagnostics ?? []).length > 0 && (
                  <section className="rounded-lg border border-red-200 bg-red-50 px-4 py-3">
                    <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-[#9a1f1f]">Why it failed</p>
                    <ul className="list-disc space-y-1 pl-4">
                      {(schedulerFailure.diagnostics ?? []).map((d, i) => (
                        <li key={i} className="text-sm text-[#444]">{humanize(d)}</li>
                      ))}
                    </ul>
                  </section>
                )}

                {/* Suggestions */}
                {regularSuggestions.length > 0 && (
                  <section className="rounded-lg border border-blue-200 bg-blue-50 px-4 py-3">
                    <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-[#1635a7]">Suggestions</p>
                    <ul className="list-disc space-y-1 pl-4">
                      {regularSuggestions.map((s, i) => (
                        <li key={i} className="text-sm text-[#333]">{s}</li>
                      ))}
                    </ul>
                  </section>
                )}

                {/* Quick actions — all toggles + room/buffer controls */}
                {hasQuickActions && (
                  <section className="rounded-lg border border-gray-200 bg-gray-50 px-4 py-3">
                    <p className="mb-3 text-xs font-semibold uppercase tracking-wide text-[#555]">Quick actions</p>
                    <div className="space-y-2">
                      {mentionedConstraints.map(({ key, label }) => renderToggle(key, label))}
                      <div className="flex items-center gap-3 pt-1">
                        <span className="text-sm text-[#333]">Rooms: <strong>{pendingRooms ?? roomsAvailable}</strong></span>
                        <div className="flex items-center gap-1">
                          <button type="button" onClick={() => setPendingRooms((pendingRooms ?? roomsAvailable) - 1)} disabled={(pendingRooms ?? roomsAvailable) <= 1} className="flex h-6 w-6 items-center justify-center rounded border border-[#c7d4f7] bg-white text-sm font-bold text-[#1635a7] hover:bg-[#eef3ff] disabled:opacity-40">−</button>
                          <span className="w-8 text-center text-xs font-semibold text-[#1635a7]">{pendingRooms ?? roomsAvailable}</span>
                          <button type="button" onClick={() => setPendingRooms((pendingRooms ?? roomsAvailable) + 1)} className="flex h-6 w-6 items-center justify-center rounded border border-[#c7d4f7] bg-white text-sm font-bold text-[#1635a7] hover:bg-[#eef3ff]">+</button>
                        </div>
                        <button
                          type="button"
                          onClick={() => void handleApplyRooms()}
                          disabled={isApplyingRooms || pendingRooms === null || pendingRooms === roomsAvailable}
                          className="rounded-lg bg-[#1635a7] px-3 py-1.5 text-xs font-semibold text-white transition hover:bg-[#0f2a8a] disabled:opacity-50"
                        >
                          {isApplyingRooms ? "Applying…" : "Apply"}
                        </button>
                      </div>
                      {needsBuffer && (
                        <div className="flex items-center gap-3 pt-1">
                          <span className="text-sm text-[#333]">Buffer: <strong>{defaultBuffer} min</strong></span>
                          <div className="flex items-center gap-1">
                            <button type="button" onClick={() => setPendingBuffer((pendingBuffer ?? defaultBuffer) - 1)} disabled={(pendingBuffer ?? defaultBuffer) <= 0} className="flex h-6 w-6 items-center justify-center rounded border border-[#c7d4f7] bg-white text-sm font-bold text-[#1635a7] hover:bg-[#eef3ff] disabled:opacity-40">−</button>
                            <span className="w-8 text-center text-xs font-semibold text-[#1635a7]">{pendingBuffer ?? defaultBuffer}</span>
                            <button type="button" onClick={() => setPendingBuffer((pendingBuffer ?? defaultBuffer) + 1)} className="flex h-6 w-6 items-center justify-center rounded border border-[#c7d4f7] bg-white text-sm font-bold text-[#1635a7] hover:bg-[#eef3ff]">+</button>
                          </div>
                          <button
                            type="button"
                            onClick={() => void handleApplyBuffer()}
                            disabled={isApplyingBuffer || pendingBuffer === null || pendingBuffer === defaultBuffer}
                            className="rounded-lg bg-[#1635a7] px-3 py-1.5 text-xs font-semibold text-white transition hover:bg-[#0f2a8a] disabled:opacity-50"
                          >
                            {isApplyingBuffer ? "Applying…" : "Apply to all"}
                          </button>
                        </div>
                      )}
                    </div>
                  </section>
                )}

              </div>

              {/* Footer */}
              <div className="shrink-0 flex flex-wrap gap-3 border-t border-gray-100 px-5 py-3">
                <button
                  type="button"
                  onClick={() => { setSchedulerFailure(null); void handleRunScheduler(true); }}
                  disabled={isRunningScheduler}
                  className="rounded-lg bg-[#0f33a8] px-5 py-2 text-sm font-semibold text-white transition hover:bg-[#1237af] disabled:opacity-50"
                >
                  {isRunningScheduler ? "Re-running..." : "Re-run scheduler"}
                </button>
                <div className="group relative">
                  <button
                    type="button"
                    onClick={() => { setSchedulerFailure(null); void handleRunScheduler(true, true); }}
                    disabled={isRunningScheduler}
                    className="rounded-lg bg-[#7c4f00] px-5 py-2 text-sm font-semibold text-white transition hover:bg-[#5e3b00] disabled:opacity-50"
                  >
                    {isRunningScheduler ? "Analyzing..." : "Run Debugger"}
                  </button>
                  <div className="pointer-events-none absolute bottom-full left-0 z-10 mb-1.5 hidden w-64 rounded-lg bg-gray-900 px-3 py-2 text-xs text-white shadow-lg group-hover:block">
                    Tests every combination of hard/soft constraints (up to 10 min) to find the settings that schedule the most presentations.
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => setSchedulerFailure(null)}
                  className="rounded-lg border border-gray-300 bg-white px-5 py-2 text-sm font-semibold text-[#333] transition hover:bg-gray-50"
                >
                  Dismiss
                </button>
              </div>
            </div>
          </div>
        );
      })() : null}

      {/* Debugger findings popup — only appears after a Run Debugger run */}
      {debuggerFindings ? (() => {
        const constraintMap = [
          { key: "professorAvailability" as const, label: "Professor availability", signal: "professor availability" },
          { key: "studentAvailability" as const, label: "Student availability", signal: "student availability" },
          { key: "sameClassSameRoom" as const, label: "Same class \u2192 same room", signal: "same class" },
          { key: "roomConflicts" as const, label: "Room conflicts", signal: "room conflicts" },
          { key: "personConflicts" as const, label: "Person conflicts", signal: "person conflicts" },
        ] as const;

        const recommendedConstraints = constraintMap.filter(({ key }) => key in debuggerRecommendations);
        const hasRecommendations = recommendedConstraints.length > 0;

        // Summary bullets: skip "Set X to Y" lines — those are shown as toggles instead.
        const summaryHints = debuggerFindings.filter((h) => !/\bto (soft|hard|off)\b/i.test(h));

        return (
          <div
            className="fixed inset-0 flex items-center justify-center bg-black/50 px-4"
            style={{ zIndex: 60 }}
            onClick={() => setDebuggerFindings(null)}
          >
            <div
              className="flex w-full max-w-lg flex-col overflow-hidden rounded-xl bg-white shadow-2xl"
              style={{ maxHeight: "90vh" }}
              onClick={(e) => e.stopPropagation()}
            >
              <div className="shrink-0 bg-[#7c4f00] px-5 py-3">
                <p className="text-base font-semibold text-white">Debugger findings</p>
                <p className="text-sm text-amber-200">Results from exhaustive constraint analysis</p>
              </div>

              <div className="space-y-4 overflow-y-auto px-5 py-4">
                {/* Summary */}
                {summaryHints.length > 0 && (
                  <section className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3">
                    <ul className="list-disc space-y-1.5 pl-4">
                      {summaryHints.map((hint, i) => (
                        <li key={i} className="text-sm text-amber-900">{hint}</li>
                      ))}
                    </ul>
                  </section>
                )}

                {/* Recommended constraint settings */}
                {hasRecommendations && (
                  <section className="rounded-lg border border-gray-200 bg-gray-50 px-4 py-3">
                    <p className="mb-3 text-xs font-semibold uppercase tracking-wide text-[#555]">
                      Recommended settings
                    </p>
                    <div className="space-y-2">
                      {recommendedConstraints.map(({ key, label }) => {
                        const recommended = debuggerRecommendations[key]!;
                        return (
                          <div key={key} className="flex items-center justify-between gap-2 rounded-md border border-[#d0d8f0] bg-white px-3 py-1.5">
                            <span className="text-xs font-medium text-[#1a3580]">{label}</span>
                            <div className="flex shrink-0 overflow-hidden rounded border border-[#d0d8f0]">
                              {(["off", "soft", "hard"] as const).map((mode) => {
                                const isRec = mode === recommended;
                                const isCurrent = mode === constraints[key];
                                return (
                                  <button
                                    key={mode}
                                    type="button"
                                    onClick={() => setDebuggerRecommendations((prev) => ({ ...prev, [key]: mode }))}
                                    className={`w-[42px] py-1 text-[10px] font-semibold transition ${
                                      isRec
                                        ? mode === "off" ? "bg-[#e0e0e0] text-[#555]"
                                          : "bg-[#b45309] text-white"
                                        : isCurrent
                                          ? "bg-[#e8eeff] text-[#888]"
                                          : "bg-white text-[#aaa] hover:bg-[#f5f5f5]"
                                    }`}
                                  >
                                    {mode === "off" ? "Off" : mode === "soft" ? "Soft" : "Hard"}
                                  </button>
                                );
                              })}
                            </div>
                          </div>
                        );
                      })}
                    </div>
                    <p className="mt-2 text-[11px] text-[#888]">
                      Amber = recommended. Click to adjust before accepting.
                    </p>
                  </section>
                )}
              </div>

              <div className="shrink-0 flex gap-3 border-t border-gray-100 px-5 py-3">
                {hasRecommendations && debugBestAssignments.length > 0 && (
                  <button
                    type="button"
                    onClick={async () => {
                      try {
                        setConstraints((prev) => ({ ...prev, ...debuggerRecommendations }));
                        await apiPost("/api/events/schedule/apply-debug", {
                          symposium_id: selectedSymposiumId,
                          assignments: debugBestAssignments,
                        }, authHeaders);
                        setDebuggerFindings(null);
                        setSchedulerFailure(null);
                        setDebugBestAssignments([]);
                        await fetchScheduleData(selectedSymposiumId);
                      } catch (err) {
                        const msg = err instanceof Error ? err.message : "Unknown error";
                        setSchedulerMessage(`Error applying schedule: ${msg}`);
                      }
                    }}
                    disabled={isRunningScheduler}
                    className="rounded-lg bg-[#1b6e2b] px-5 py-2 text-sm font-semibold text-white transition hover:bg-[#15572b] disabled:opacity-50"
                  >
                    Accept & Apply
                  </button>
                )}
                <button
                  type="button"
                  onClick={() => setDebuggerFindings(null)}
                  className="rounded-lg border border-gray-300 bg-white px-5 py-2 text-sm font-semibold text-[#333] transition hover:bg-gray-50"
                >
                  Dismiss
                </button>
              </div>
            </div>
          </div>
        );
      })() : null}
    </div>
  );
}
