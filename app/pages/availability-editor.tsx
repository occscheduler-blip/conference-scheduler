"use client";

import { useEffect, useMemo, useState } from "react";
import { apiFetch, apiPut, ApiError } from "../lib/api";
import { toBackendDateTime } from "../lib/utils";
import {
  buildCalendarWithGeometry,
  computeGridGeometry,
  formatMinutesOfDay,
  slotIsHourBoundary,
  type GridGeometry,
  type TimeframeLite,
} from "../lib/useGridGeometry";
import { useCalendarGrid } from "../lib/useCalendarGrid";
import { useWeekPagination } from "../lib/useWeekPagination";
import type { CalendarDay } from "./types";

type Props = {
  token: string;
  symposiumId: string;
  linkedId: string;
  entityName: string;
  entityKind: "Professor" | "Student";
  onClose: () => void;
};

export default function AvailabilityEditor({
  token,
  symposiumId,
  linkedId,
  entityName,
  entityKind,
  onClose,
}: Props) {
  const authHeaders = useMemo(() => ({ Authorization: `Bearer ${token}` }), [token]);
  const [calendarDays, setCalendarDays] = useState<CalendarDay[]>([]);
  const [editableSlots, setEditableSlots] = useState<boolean[][]>([]);
  const FALLBACK_GEOMETRY: GridGeometry = useMemo(
    () => computeGridGeometry({ timeframes: [] }),
    [],
  );
  const [geometry, setGeometry] = useState<GridGeometry>(FALLBACK_GEOMETRY);
  const { availability, setAvailability, handleCellMouseDown, handleCellMouseEnter } =
    useCalendarGrid(calendarDays.length, editableSlots);
  const weekPagination = useWeekPagination(calendarDays.map((day) => day.key));
  const [isLoading, setIsLoading] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [statusMessage, setStatusMessage] = useState<string>("");
  const [errorMessage, setErrorMessage] = useState<string>("");

  useEffect(() => {
    const handleKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handleKey);
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", handleKey);
      document.body.style.overflow = previousOverflow;
    };
  }, [onClose]);

  useEffect(() => {
    if (!symposiumId || !linkedId) return;
    let ignore = false;
    const load = async () => {
      setIsLoading(true);
      setErrorMessage("");
      setStatusMessage("");
      try {
        const [symposiumRows, entityRows] = await Promise.all([
          apiFetch<{ start_time?: string; end_time?: string }>(
            `/api/events/timeframes?linked_id=${encodeURIComponent(symposiumId)}`,
            { headers: authHeaders, cache: "no-store" }
          ),
          apiFetch<{ start_time?: string; end_time?: string }>(
            `/api/events/timeframes?linked_id=${encodeURIComponent(linkedId)}`,
            { headers: authHeaders, cache: "no-store" }
          ),
        ]);
        const symTfs: TimeframeLite[] = symposiumRows
          .filter((r): r is { start_time: string; end_time?: string } => Boolean(r.start_time))
          .map((r) => ({ start_time: r.start_time, end_time: r.end_time ?? null }));
        const entTfs: TimeframeLite[] = entityRows
          .filter((r): r is { start_time: string; end_time?: string } => Boolean(r.start_time))
          .map((r) => ({ start_time: r.start_time, end_time: r.end_time ?? null }));
        const newGeometry = computeGridGeometry({ timeframes: symTfs });
        const built = buildCalendarWithGeometry(symTfs, entTfs, newGeometry);
        if (ignore) return;
        setGeometry(newGeometry);
        setCalendarDays(built.calendarDays);
        setEditableSlots(built.editableSlots);
        setAvailability(built.availability);
        if (built.calendarDays.length === 0) {
          setStatusMessage("No symposium dates are configured.");
        }
      } catch (error) {
        if (ignore) return;
        setErrorMessage(error instanceof Error ? error.message : "Failed to load availability.");
      } finally {
        if (!ignore) setIsLoading(false);
      }
    };
    void load();
    return () => {
      ignore = true;
    };
  }, [authHeaders, linkedId, setAvailability, symposiumId]);

  const handleSave = async () => {
    setErrorMessage("");
    setStatusMessage("");
    if (calendarDays.length === 0) {
      setErrorMessage("No symposium dates are configured.");
      return;
    }

    const timeframes: Array<{ start_time: string; end_time: string }> = [];
    const slotMinutesAtIndex = (slotIndex: number) =>
      geometry.gridStartMinutes + slotIndex * geometry.slotMinutes;

    for (let dayIndex = 0; dayIndex < calendarDays.length; dayIndex += 1) {
      const day = calendarDays[dayIndex];
      const [year, month, dayOfMonth] = day.key.split("-").map((part) => Number.parseInt(part, 10));
      if (!year || !month || !dayOfMonth) continue;

      let rangeStart: Date | null = null;
      let rangeEnd: Date | null = null;

      for (let slotIndex = 0; slotIndex < geometry.slotsPerDay; slotIndex += 1) {
        const editable = editableSlots[dayIndex]?.[slotIndex] ?? false;
        const available = availability[dayIndex]?.[slotIndex] ?? false;

        if (editable && available) {
          const startMin = slotMinutesAtIndex(slotIndex);
          const endMin = startMin + geometry.slotMinutes;
          const slotStart = new Date(Date.UTC(year, month - 1, dayOfMonth, 0, 0, 0, 0));
          slotStart.setUTCMinutes(startMin);
          const slotEnd = new Date(Date.UTC(year, month - 1, dayOfMonth, 0, 0, 0, 0));
          slotEnd.setUTCMinutes(endMin);
          if (!rangeStart) {
            rangeStart = slotStart;
            rangeEnd = slotEnd;
          } else {
            rangeEnd = slotEnd;
          }
        } else if (rangeStart && rangeEnd) {
          timeframes.push({ start_time: toBackendDateTime(rangeStart), end_time: toBackendDateTime(rangeEnd) });
          rangeStart = null;
          rangeEnd = null;
        }
      }

      if (rangeStart && rangeEnd) {
        timeframes.push({ start_time: toBackendDateTime(rangeStart), end_time: toBackendDateTime(rangeEnd) });
      }
    }

    setIsSaving(true);
    try {
      await apiPut("/api/events/update_timeframes", { linked_id: linkedId, timeframes }, authHeaders);
      setStatusMessage(`Saved ${timeframes.length} availability slot${timeframes.length === 1 ? "" : "s"}.`);
    } catch (error) {
      if (error instanceof ApiError && error.isBusy()) {
        setErrorMessage("This symposium is busy with another change. Please wait a moment and retry.");
      } else if (error instanceof ApiError && error.isStale()) {
        setErrorMessage("These availability slots were changed by another tab — please reload the editor.");
      } else {
        setErrorMessage(error instanceof Error ? error.message : "Save failed.");
      }
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      onClick={onClose}
    >
      <div
        className="grid w-full max-w-5xl overflow-hidden rounded-xl border border-[#d6b676] bg-white shadow-2xl"
        style={{ height: "calc(100vh - 2rem)", gridTemplateRows: "auto minmax(0, 1fr) auto" }}
        onClick={(event) => event.stopPropagation()}
      >
        <div className="flex items-center justify-between gap-3 bg-[#1635a7] px-5 py-3 text-white">
          <div>
            <p className="text-xs font-semibold uppercase tracking-wide opacity-80">{entityKind} Availability</p>
            <p className="text-lg font-bold">{entityName}</p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-md border border-white/40 bg-white/10 px-3 py-1 text-sm font-semibold transition hover:bg-white/20"
          >
            Close
          </button>
        </div>
        <div
          className="space-y-4 px-5 py-4"
          style={{ overflowY: "auto", overflowX: "hidden", minHeight: 0 }}
        >
          {isLoading ? (
            <p className="text-sm font-semibold text-[#333]">Loading availability...</p>
          ) : (
            <>
              <div className="flex flex-wrap items-center gap-5 text-sm font-semibold text-[#333]">
                <div className="flex items-center gap-2">
                  <span>Unavailable</span>
                  <span className="inline-block h-6 w-8 border border-[#777] bg-[#f0d7d9]" />
                </div>
                <div className="flex items-center gap-2">
                  <span>Available</span>
                  <span className="inline-block h-6 w-8 border border-[#777] bg-[#38a000]" />
                </div>
                <div className="flex items-center gap-2">
                  <span>Outside symposium</span>
                  <span className="inline-block h-6 w-8 border border-[#777] bg-[#d1d5db]" />
                </div>
              </div>

              <p className="text-sm font-semibold text-[#444]">
                Click and drag cells to toggle availability. Save to apply changes.
              </p>

              {weekPagination.hasMultipleWeeks ? (
                <div className="flex items-center gap-3">
                  <button
                    type="button"
                    onClick={weekPagination.prevWeek}
                    disabled={!weekPagination.hasPrev}
                    className="rounded-lg border border-[#c7c7c7] bg-white px-3 py-1 text-sm font-semibold text-[#333] transition hover:bg-[#f5f5f5] disabled:cursor-not-allowed disabled:opacity-40"
                    aria-label="Previous week"
                  >
                    &larr;
                  </button>
                  <span className="text-sm font-semibold text-[#333]">
                    Week {weekPagination.weekNumber} of {weekPagination.totalWeeks}: {weekPagination.weekLabel}
                  </span>
                  <button
                    type="button"
                    onClick={weekPagination.nextWeek}
                    disabled={!weekPagination.hasNext}
                    className="rounded-lg border border-[#c7c7c7] bg-white px-3 py-1 text-sm font-semibold text-[#333] transition hover:bg-[#f5f5f5] disabled:cursor-not-allowed disabled:opacity-40"
                    aria-label="Next week"
                  >
                    &rarr;
                  </button>
                </div>
              ) : null}

              {calendarDays.length > 0 ? (
                <div className="w-full rounded-xl border border-[#cfcfcf] bg-white p-3">
                  <div className="min-w-[720px] select-none">
                    <div
                      className="grid text-center font-bold text-[#222]"
                      style={{ gridTemplateColumns: `90px repeat(${weekPagination.visibleDayIndices.length}, minmax(120px, 1fr))` }}
                    >
                      <div />
                      {weekPagination.visibleDayIndices.map((di) => (
                        <div key={calendarDays[di].key} className="border-b border-[#777] pb-1 text-sm md:text-base">
                          {calendarDays[di].label}
                        </div>
                      ))}
                    </div>
                    <div
                      className="grid"
                      style={{ gridTemplateColumns: `90px repeat(${weekPagination.visibleDayIndices.length}, minmax(120px, 1fr))` }}
                    >
                      {Array.from({ length: geometry.slotsPerDay }, (_, slotIndex) => {
                        const minuteAtSlot = geometry.gridStartMinutes + slotIndex * geometry.slotMinutes;
                        const showHourLine = slotIsHourBoundary(geometry, slotIndex);
                        const labelText = showHourLine ? formatMinutesOfDay(minuteAtSlot) : "";
                        return (
                          <div key={slotIndex} className="contents">
                            <div className="h-6 overflow-hidden pr-2 text-right text-sm leading-6 font-semibold text-[#444]">
                              {labelText}
                            </div>
                            {weekPagination.visibleDayIndices.map((dayIndex) => {
                              const day = calendarDays[dayIndex];
                              const available = availability[dayIndex]?.[slotIndex] ?? false;
                              const editable = editableSlots[dayIndex]?.[slotIndex] ?? false;
                              return (
                                <button
                                  key={`${dayIndex}-${slotIndex}`}
                                  type="button"
                                  onMouseDown={() => handleCellMouseDown(dayIndex, slotIndex)}
                                  onMouseEnter={() => handleCellMouseEnter(dayIndex, slotIndex)}
                                  onDragStart={(event) => event.preventDefault()}
                                  disabled={!editable}
                                  className={`h-6 border-r border-l border-b border-[#333] ${
                                    showHourLine ? "border-t border-t-[#333]" : ""
                                  } ${
                                    !editable ? "cursor-not-allowed bg-[#d1d5db]" : available ? "bg-[#38a000]" : "bg-[#f0d7d9]"
                                  }`}
                                  aria-label={`${day.label} ${formatMinutesOfDay(minuteAtSlot)}`}
                                />
                              );
                            })}
                          </div>
                        );
                      })}
                    </div>
                  </div>
                </div>
              ) : null}
            </>
          )}

          {statusMessage ? <p className="text-sm font-semibold text-[#1f5132]">{statusMessage}</p> : null}
          {errorMessage ? <p className="text-sm font-semibold text-[#9a1f1f]">{errorMessage}</p> : null}
        </div>
        <div className="flex items-center justify-end gap-2 border-t border-[#e5e7eb] bg-[#fafbff] px-5 py-3">
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg border border-[#0f33a8] bg-white px-4 py-2 text-sm font-semibold text-[#0f33a8] transition hover:bg-[#eef3ff]"
          >
            Close
          </button>
          <button
            type="button"
            onClick={() => void handleSave()}
            disabled={isLoading || isSaving || calendarDays.length === 0}
            className="rounded-lg bg-[#0f33a8] px-4 py-2 text-sm font-semibold text-white shadow-[0_8px_18px_rgba(15,51,168,0.25)] transition hover:bg-[#0b2a8d] disabled:cursor-not-allowed disabled:opacity-60"
          >
            {isSaving ? "Saving..." : "Save"}
          </button>
        </div>
      </div>
    </div>
  );
}
