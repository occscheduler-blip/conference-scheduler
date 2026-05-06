"use client";

import { useMemo } from "react";
import { dayKey, formatCalendarDate, parseBackendDateTime } from "./utils";
import type { CalendarDay } from "../pages/types";

export type TimeframeLite = { start_time: string; end_time?: string | null };

export type GridGeometry = {
  /** Minute-of-day (0..1440) of the first slot. */
  gridStartMinutes: number;
  /** Minute-of-day of the row past the last slot (gridStart + slotsPerDay * slotMinutes). */
  gridEndMinutes: number;
  /** Minutes per row in the grid. */
  slotMinutes: number;
  /** Number of rows between gridStart and gridEnd. */
  slotsPerDay: number;
  /** Pixel scale: how many pixels represent one minute. Constant across views. */
  pxPerMinute: number;
  /** Pixel height of one slot row (slotMinutes * pxPerMinute). */
  slotPx: number;
  /** Total pixel height for one day's column. */
  totalPx: number;
};

/** Legacy ratio: 24 px per 15-minute slot — preserves the pre-refactor scale. */
const DEFAULT_PX_PER_MINUTE = 24 / 15;
const DEFAULT_FALLBACK_SLOT_MINUTES = 15;
const FALLBACK_GRID_START = 9 * 60;
const FALLBACK_GRID_END = 21 * 60;

function gcdPair(a: number, b: number): number {
  let x = Math.abs(Math.round(a));
  let y = Math.abs(Math.round(b));
  while (y > 0) {
    [x, y] = [y, x % y];
  }
  return x;
}

function gcdAll(values: number[], fallback: number): number {
  const filtered = values.filter((v) => Number.isFinite(v) && v > 0);
  if (filtered.length === 0) return fallback;
  return filtered.reduce((acc, v) => gcdPair(acc, v), filtered[0]);
}

function minutesOfDay(date: Date): number {
  return date.getUTCHours() * 60 + date.getUTCMinutes();
}

function parseTimeframeRange(tf: TimeframeLite): { start: number; end: number } | null {
  if (!tf.start_time) return null;
  const start = parseBackendDateTime(tf.start_time);
  if (Number.isNaN(start.getTime())) return null;
  const startMin = minutesOfDay(start);

  if (!tf.end_time) return { start: startMin, end: startMin };
  const end = parseBackendDateTime(tf.end_time);
  if (Number.isNaN(end.getTime())) return { start: startMin, end: startMin };
  let endMin = minutesOfDay(end);
  // If end falls on the following calendar day, treat it as 24:00.
  if (
    end.getUTCFullYear() !== start.getUTCFullYear() ||
    end.getUTCMonth() !== start.getUTCMonth() ||
    end.getUTCDate() !== start.getUTCDate()
  ) {
    endMin = 24 * 60;
  } else if (endMin < startMin) {
    endMin = startMin;
  }
  return { start: startMin, end: endMin };
}

export type ComputeGridGeometryOptions = {
  /** Symposium / availability windows that bound the grid. */
  timeframes: TimeframeLite[];
  /** Optional presentation timeframes to ensure visible. */
  presentationTimeframes?: TimeframeLite[];
  /** Presentation durations (minutes) — fed into slot-minutes GCD. */
  presentationDurations?: number[];
  /** Per-presentation buffers — fed into slot-minutes GCD. */
  presentationBuffers?: number[];
  /** Default symposium buffer — fed into GCD. */
  defaultBuffer?: number;
  /** Pixels per minute; default 24/15 — matches the legacy SLOT_HEIGHT/15 ratio. */
  pxPerMinute?: number;
  /** Floor for slot granularity in minutes (default 5). */
  minSlotMinutes?: number;
  /** Fallback slot granularity when no GCD candidates are available (default 15). */
  fallbackSlotMinutes?: number;
};

export function computeGridGeometry(options: ComputeGridGeometryOptions): GridGeometry {
  const {
    timeframes,
    presentationTimeframes = [],
    presentationDurations = [],
    presentationBuffers = [],
    defaultBuffer,
    pxPerMinute = DEFAULT_PX_PER_MINUTE,
    minSlotMinutes = 5,
    fallbackSlotMinutes = DEFAULT_FALLBACK_SLOT_MINUTES,
  } = options;

  let earliestStart = Number.POSITIVE_INFINITY;
  let latestEnd = Number.NEGATIVE_INFINITY;
  const gcdCandidates: number[] = [];

  // Symposium timeframe lengths bound the grid extent but should NOT feed the
  // slot-minutes GCD: a single 9-hour timeframe would collapse the lattice to
  // its own length, blowing up slot height for views with no presentation data.
  for (const tf of timeframes) {
    const range = parseTimeframeRange(tf);
    if (!range) continue;
    if (range.start < earliestStart) earliestStart = range.start;
    if (range.end > latestEnd) latestEnd = range.end;
  }

  for (const tf of presentationTimeframes) {
    const range = parseTimeframeRange(tf);
    if (!range) continue;
    if (range.start < earliestStart) earliestStart = range.start;
    if (range.end > latestEnd) latestEnd = range.end;
  }

  for (const minutes of presentationDurations) {
    if (Number.isFinite(minutes) && minutes > 0) gcdCandidates.push(minutes);
  }
  for (const buffer of presentationBuffers) {
    if (Number.isFinite(buffer) && buffer > 0) gcdCandidates.push(buffer);
  }
  if (typeof defaultBuffer === "number" && Number.isFinite(defaultBuffer) && defaultBuffer > 0) {
    gcdCandidates.push(defaultBuffer);
  }

  if (!Number.isFinite(earliestStart) || !Number.isFinite(latestEnd)) {
    earliestStart = FALLBACK_GRID_START;
    latestEnd = FALLBACK_GRID_END;
  }

  earliestStart = Math.max(0, earliestStart);
  latestEnd = Math.min(24 * 60, latestEnd);
  if (latestEnd <= earliestStart) latestEnd = Math.min(24 * 60, earliestStart + 60);

  let slotMinutes = gcdAll(gcdCandidates, fallbackSlotMinutes);
  if (slotMinutes < minSlotMinutes) slotMinutes = minSlotMinutes;
  if (slotMinutes > 60) slotMinutes = 60;

  // Snap grid bounds onto the slot lattice so slot count is integral.
  earliestStart = Math.floor(earliestStart / slotMinutes) * slotMinutes;
  latestEnd = Math.ceil(latestEnd / slotMinutes) * slotMinutes;
  if (latestEnd <= earliestStart) latestEnd = earliestStart + slotMinutes;

  const slotsPerDay = Math.max(1, Math.round((latestEnd - earliestStart) / slotMinutes));
  const slotPx = slotMinutes * pxPerMinute;

  return {
    gridStartMinutes: earliestStart,
    gridEndMinutes: latestEnd,
    slotMinutes,
    slotsPerDay,
    pxPerMinute,
    slotPx,
    totalPx: slotsPerDay * slotPx,
  };
}

export function useGridGeometry(options: ComputeGridGeometryOptions): GridGeometry {
  const {
    timeframes,
    presentationTimeframes,
    presentationDurations,
    presentationBuffers,
    defaultBuffer,
    pxPerMinute,
    minSlotMinutes,
    fallbackSlotMinutes,
  } = options;
  return useMemo(
    () =>
      computeGridGeometry({
        timeframes,
        presentationTimeframes,
        presentationDurations,
        presentationBuffers,
        defaultBuffer,
        pxPerMinute,
        minSlotMinutes,
        fallbackSlotMinutes,
      }),
    [
      timeframes,
      presentationTimeframes,
      presentationDurations,
      presentationBuffers,
      defaultBuffer,
      pxPerMinute,
      minSlotMinutes,
      fallbackSlotMinutes,
    ],
  );
}

/** Format a minute-of-day value as "9:05 AM". */
export function formatMinutesOfDay(minutes: number): string {
  const total = ((Math.round(minutes) % (24 * 60)) + 24 * 60) % (24 * 60);
  const hour24 = Math.floor(total / 60);
  const mins = total % 60;
  const suffix = hour24 >= 12 ? "PM" : "AM";
  const hour12 = hour24 % 12 === 0 ? 12 : hour24 % 12;
  return `${hour12}:${mins.toString().padStart(2, "0")} ${suffix}`;
}

/** True when a slot index lands on a whole-hour boundary. */
export function slotIsHourBoundary(geometry: GridGeometry, slotIndex: number): boolean {
  return (geometry.gridStartMinutes + slotIndex * geometry.slotMinutes) % 60 === 0;
}

/** True when a slot index lands on a half-hour boundary. */
export function slotIsHalfHourBoundary(geometry: GridGeometry, slotIndex: number): boolean {
  return (geometry.gridStartMinutes + slotIndex * geometry.slotMinutes) % 30 === 0;
}

/**
 * Build a per-symposium availability grid where row dimensions follow the
 * supplied {@link GridGeometry} rather than the legacy 9 AM / 15-minute
 * constants.
 *
 * `editableSlots[d][s]` is true when slot `s` on day `d` falls within any
 * symposium timeframe; `availability[d][s]` is true when the slot is editable
 * AND falls within an entity (professor/student) timeframe.
 */
export function buildCalendarWithGeometry(
  symposiumTimeframes: TimeframeLite[],
  entityTimeframes: TimeframeLite[],
  geometry: GridGeometry,
): {
  calendarDays: CalendarDay[];
  editableSlots: boolean[][];
  availability: boolean[][];
} {
  const dayKeysSet = new Set<string>();
  type ParsedRow = { dayKey: string; startMinute: number; endMinute: number };
  const symRows: ParsedRow[] = [];
  const entRows: ParsedRow[] = [];

  const ingest = (rows: TimeframeLite[], target: ParsedRow[]) => {
    for (const tf of rows) {
      if (!tf.start_time) continue;
      const start = parseBackendDateTime(tf.start_time);
      if (Number.isNaN(start.getTime())) continue;
      const dk = dayKey(start);
      const startMin = start.getUTCHours() * 60 + start.getUTCMinutes();
      let endMin: number;
      if (tf.end_time) {
        const end = parseBackendDateTime(tf.end_time);
        if (Number.isNaN(end.getTime())) {
          endMin = startMin + geometry.slotMinutes;
        } else {
          endMin = end.getUTCHours() * 60 + end.getUTCMinutes();
          const sameDay =
            end.getUTCFullYear() === start.getUTCFullYear() &&
            end.getUTCMonth() === start.getUTCMonth() &&
            end.getUTCDate() === start.getUTCDate();
          if (!sameDay) endMin = 24 * 60;
          if (endMin <= startMin) endMin = startMin + geometry.slotMinutes;
        }
      } else {
        endMin = startMin + geometry.slotMinutes;
      }
      target.push({ dayKey: dk, startMinute: startMin, endMinute: endMin });
      dayKeysSet.add(dk);
    }
  };
  ingest(symposiumTimeframes, symRows);
  ingest(entityTimeframes, entRows);

  const calendarDays: CalendarDay[] = Array.from(dayKeysSet)
    .sort()
    .map((key) => ({
      key,
      label: formatCalendarDate(new Date(`${key}T00:00:00Z`)),
    }));

  const dayIndexByKey = new Map(calendarDays.map((day, idx) => [day.key, idx]));
  const editableSlots = Array.from({ length: calendarDays.length }, () =>
    Array.from({ length: geometry.slotsPerDay }, () => false),
  );
  const availability = Array.from({ length: calendarDays.length }, () =>
    Array.from({ length: geometry.slotsPerDay }, () => false),
  );

  const minuteToSlotRange = (startMin: number, endMin: number) => {
    const startSlot = Math.floor((startMin - geometry.gridStartMinutes) / geometry.slotMinutes);
    const endSlot = Math.ceil((endMin - geometry.gridStartMinutes) / geometry.slotMinutes);
    return {
      startSlot: Math.max(0, startSlot),
      endSlot: Math.min(geometry.slotsPerDay, endSlot),
    };
  };

  for (const row of symRows) {
    const di = dayIndexByKey.get(row.dayKey);
    if (di === undefined) continue;
    const { startSlot, endSlot } = minuteToSlotRange(row.startMinute, row.endMinute);
    for (let s = startSlot; s < endSlot; s += 1) editableSlots[di][s] = true;
  }
  for (const row of entRows) {
    const di = dayIndexByKey.get(row.dayKey);
    if (di === undefined) continue;
    const { startSlot, endSlot } = minuteToSlotRange(row.startMinute, row.endMinute);
    for (let s = startSlot; s < endSlot; s += 1) {
      if (editableSlots[di][s]) availability[di][s] = true;
    }
  }

  return { calendarDays, editableSlots, availability };
}
