"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
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
  dayKey,
  normalizeId,
} from "../lib/utils";
import { apiFetch, apiPost, apiPut } from "../lib/api";

function dayLabel(key: string) {
  return new Date(`${key}T00:00:00`).toLocaleDateString(undefined, {
    weekday: "long",
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

function timeLabel(start: string, end: string) {
  const s = parseBackendDateTime(start);
  const e = parseBackendDateTime(end);
  return `${s.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })} - ${e.toLocaleTimeString([], {
    hour: "numeric",
    minute: "2-digit",
  })}`;
}

/** Convert a Date to a datetime-local input value (YYYY-MM-DDTHH:MM). */
function toDatetimeLocal(d: Date): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

const fieldClass =
  "w-full rounded-lg border-2 border-[#2f53c4] bg-white px-3 py-2.5 text-base text-black shadow-sm outline-none transition focus:border-[#1237af] focus:ring-2 focus:ring-[#c7d4ff] placeholder:text-[#6b6b6b]";

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
  const [isLoadingSchedule, setIsLoadingSchedule] = useState(false);
  const [selectedDay, setSelectedDay] = useState("");
  const [message, setMessage] = useState<string | null>(null);

  // Scheduler
  const [isRunningScheduler, setIsRunningScheduler] = useState(false);
  const [schedulerMessage, setSchedulerMessage] = useState<string | null>(null);

  // Edit modal
  const [editingPresentation, setEditingPresentation] = useState<SchedulePresentation | null>(null);
  const [editRoom, setEditRoom] = useState("");
  const [editStartTime, setEditStartTime] = useState("");
  const [isSavingAssignment, setIsSavingAssignment] = useState(false);
  const [assignmentMessage, setAssignmentMessage] = useState<string | null>(null);

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
          symposium?: { id: string; name: string; rooms_available?: number | null };
          timeframes?: Timeframe[];
        };
        if (!symposiumRes.ok) throw new Error(symposiumPayload.detail ?? "Failed to load symposium.");

        const symTimeframes = (symposiumPayload.timeframes ?? []).slice().sort((a, b) => {
          return parseBackendDateTime(a.start_time).getTime() - parseBackendDateTime(b.start_time).getTime();
        });
        setSymposiumTimeframes(symTimeframes);
        const parsedRooms = Number(symposiumPayload.symposium?.rooms_available ?? 1);
        setRoomsAvailable(Number.isFinite(parsedRooms) && parsedRooms > 0 ? Math.floor(parsedRooms) : 1);

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

        // Fetch classes
        const classRows = (
          await Promise.all(
            departmentRows.map(async (dept) => {
              try {
                return await apiFetch<ClassRecord>(
                  `/api/events/classes?department_id=${encodeURIComponent(dept.id)}`
                );
              } catch {
                return [];
              }
            })
          )
        ).flat();

        // Department lookup
        const deptById = new Map(departmentRows.map((d) => [d.id, d]));
        const deptIdByClassId = new Map(classRows.map((c) => [c.id, c.department_id]));

        // Fetch presentations and students
        type RawPresentation = {
          id?: string;
          class_id?: string;
          title?: string;
          minutes?: number;
          room?: number | null;
          presenting_students?: Array<{ id?: string; student_id?: string; name?: string }>;
        };
        type RawStudent = { id?: string; name?: string };

        const [rawPresentations, rawStudents] = await Promise.all([
          Promise.all(
            classRows.map(async (row) => {
              try {
                return await apiFetch<RawPresentation>(
                  `/api/events/presentations?class_id=${encodeURIComponent(row.id)}`
                );
              } catch {
                return [];
              }
            })
          ),
          Promise.all(
            classRows.map(async (row) => {
              try {
                return await apiFetch<RawStudent>(
                  `/api/events/students?class_id=${encodeURIComponent(row.id)}`
                );
              } catch {
                return [];
              }
            })
          ),
        ]);

        const studentNameById = new Map(
          rawStudents
            .flat()
            .filter((r): r is { id: string; name: string } => Boolean(r.id && r.name?.trim()))
            .map((r) => [normalizeId(r.id), r.name.trim()])
        );

        const flatPresentations = rawPresentations.flat();

        // Fetch timeframes for all presentations
        const presentationTimeframes = await Promise.all(
          flatPresentations.map(async (row) => {
            if (!row.id) return null;
            try {
              const tfs = await apiFetch<Timeframe>(
                `/api/events/timeframes?linked_id=${encodeURIComponent(row.id)}`
              );
              return tfs[0] ?? null;
            } catch {
              return null;
            }
          })
        );

        const presentationRows: SchedulePresentation[] = flatPresentations
          .map((row, i) => {
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

            return {
              id: row.id ?? "",
              title: row.title?.trim() ?? "",
              class_id: row.class_id ?? "",
              minutes: row.minutes ?? 0,
              room: row.room ?? null,
              timeframe: presentationTimeframes[i] ?? null,
              presenterNames: Array.from(new Set(presenterNames)),
              departmentName: dept?.department_name ?? "",
            };
          })
          .filter((r): r is SchedulePresentation => Boolean(r.id && r.class_id));

        setPresentations(presentationRows);

        const days = Array.from(new Set(symTimeframes.map((tf) => dayKey(parseBackendDateTime(tf.start_time)))));
        setSelectedDay((prev) => (days.includes(prev) ? prev : days[0] ?? ""));
      } catch (error) {
        const msg = error instanceof Error ? error.message : "Unknown error";
        setMessage(msg);
        setPresentations([]);
        setSymposiumTimeframes([]);
        setRoomsAvailable(1);
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
      const startMinutes = start.getHours() * 60 + start.getMinutes();
      const endMinutes = end.getHours() * 60 + end.getMinutes();
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

  // Handlers
  const handleRunScheduler = async () => {
    if (!selectedSymposiumId) return;
    if (!window.confirm("This will regenerate the schedule. Existing assignments will be replaced. Continue?")) return;

    setIsRunningScheduler(true);
    setSchedulerMessage(null);
    try {
      const { raw } = await apiPost("/api/events/schedule", { symposium_id: selectedSymposiumId }, authHeaders);
      const status = raw.status as string;
      const assignments = (raw.assignments as unknown[]) ?? [];
      const unscheduledIds = (raw.unscheduled_presentations as unknown[]) ?? [];
      setSchedulerMessage(
        `Schedule ${status}. ${assignments.length} assigned, ${unscheduledIds.length} unscheduled.`
      );
      await fetchScheduleData(selectedSymposiumId);
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

  const handleSaveAssignment = async () => {
    if (!editingPresentation || !selectedSymposiumId) return;
    if (!editStartTime) {
      setAssignmentMessage("Please select a start time.");
      return;
    }

    const startDate = new Date(editStartTime);
    if (Number.isNaN(startDate.getTime())) {
      setAssignmentMessage("Invalid start time.");
      return;
    }

    const endDate = new Date(startDate.getTime() + editingPresentation.minutes * 60 * 1000);

    setIsSavingAssignment(true);
    setAssignmentMessage(null);
    try {
      await apiPut(
        "/api/events/update_schedule_assignment",
        {
          symposium_id: selectedSymposiumId,
          presentation_id: editingPresentation.id,
          room: Number(editRoom),
          start_time: startDate.toISOString(),
          end_time: endDate.toISOString(),
        },
        authHeaders
      );
      setEditingPresentation(null);
      await fetchScheduleData(selectedSymposiumId);
    } catch (error) {
      const msg = error instanceof Error ? error.message : "Unknown error";
      setAssignmentMessage(msg);
    } finally {
      setIsSavingAssignment(false);
    }
  };

  // Computed end time for display in modal
  const editEndTimeDisplay = useMemo(() => {
    if (!editStartTime || !editingPresentation) return "";
    const start = new Date(editStartTime);
    if (Number.isNaN(start.getTime())) return "";
    const end = new Date(start.getTime() + editingPresentation.minutes * 60 * 1000);
    return end.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
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
          onChange={(e) => setSelectedSymposiumId(e.target.value)}
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
            onClick={handleRunScheduler}
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

      {/* Schedule grid */}
      {!isLoadingSchedule && selectedDay && selectedDay !== "unscheduled" && activeSlots.size > 0 ? (
        <div className="overflow-x-auto rounded-lg border border-[#d8e2ff] bg-white">
          <div
            className="grid"
            style={{
              gridTemplateColumns: `72px repeat(${roomsAvailable}, minmax(140px, 1fr))`,
              gridTemplateRows: `auto repeat(${visibleSlotCount}, ${SLOT_HEIGHT}px)`,
            }}
          >
            {/* Header row */}
            <div className="border-b border-r border-[#d8e2ff] bg-[#f0f4ff] px-2 py-2 text-xs font-bold uppercase text-[#2d3d7a]">
              Time
            </div>
            {Array.from({ length: roomsAvailable }, (_, i) => (
              <div
                key={i}
                className="border-b border-r border-[#d8e2ff] bg-[#f0f4ff] px-2 py-2 text-center text-xs font-bold uppercase text-[#2d3d7a] last:border-r-0"
              >
                Room {i + 1}
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
              const startMinutes = start.getHours() * 60 + start.getMinutes();
              const endMinutes = end.getHours() * 60 + end.getMinutes();
              const startSlotRaw = (startMinutes - 9 * 60) / 15;
              const endSlotRaw = (endMinutes - 9 * 60) / 15;

              // Convert to grid row (1-indexed, +2 for header row offset)
              const gridRowStart = Math.floor(startSlotRaw - minSlot) + 2;
              const gridRowEnd = Math.ceil(endSlotRaw - minSlot) + 2;
              const gridCol = pres.room + 2; // +2 for time column offset (col 1)

              // Sub-slot positioning for non-15-minute-aligned times
              const fracStart = (startSlotRaw - minSlot) - Math.floor(startSlotRaw - minSlot);
              const topOffset = fracStart * SLOT_HEIGHT;
              const blockHeight = (endSlotRaw - startSlotRaw) * SLOT_HEIGHT;
              const durationSlots = endSlotRaw - startSlotRaw;

              const color = colorMap.get(pres.id) ?? BLOCK_COLORS[0];

              return (
                <button
                  key={pres.id}
                  type="button"
                  onClick={() => handleOpenEditModal(pres)}
                  className="z-10 m-[1px] overflow-hidden rounded-md px-1.5 py-0.5 text-left shadow-sm transition hover:brightness-110 hover:shadow-md"
                  style={{
                    gridRow: `${gridRowStart} / ${gridRowEnd}`,
                    gridColumn: gridCol,
                    backgroundColor: color.bg,
                    color: color.text,
                    position: "relative",
                    top: `${topOffset}px`,
                    height: `${blockHeight}px`,
                    alignSelf: "start",
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
                </button>
              );
            })}
          </div>
        </div>
      ) : null}

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
                      Room {i + 1}
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
                  {isSavingAssignment ? "Saving..." : "Save"}
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
    </div>
  );
}
