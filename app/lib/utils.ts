import type { CalendarDay, SchedulePresentation, TimeframeRecord } from "../pages/types";

export const totalSlots = 48; // 9:00 AM to 9:00 PM in 15-minute increments

export function formatTimeLabel(slotIndex: number) {
  const totalMinutes = 9 * 60 + slotIndex * 15;
  const hour24 = Math.floor(totalMinutes / 60);
  const minutes = totalMinutes % 60;
  const suffix = hour24 >= 12 ? "PM" : "AM";
  const hour12 = hour24 % 12 === 0 ? 12 : hour24 % 12;
  const minutePart = minutes.toString().padStart(2, "0");
  return `${hour12}:${minutePart} ${suffix}`;
}

export function dayKey(date: Date) {
  const year = date.getUTCFullYear();
  const month = String(date.getUTCMonth() + 1).padStart(2, "0");
  const day = String(date.getUTCDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

export function formatCalendarDate(date: Date) {
  return date.toLocaleDateString(undefined, {
    weekday: "short",
    month: "short",
    day: "numeric",
    timeZone: "UTC",
  });
}

export function dayLabel(key: string) {
  return new Date(`${key}T00:00:00`).toLocaleDateString(undefined, {
    weekday: "long",
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

export function parseBackendDateTime(value: string) {
  const stripped = value.replace(/(?:Z|[+\-]\d{2}:?\d{2})$/i, "");
  return new Date(`${stripped}Z`);
}

export function timeLabel(start: string, end: string) {
  const s = parseBackendDateTime(start);
  const e = parseBackendDateTime(end);
  const opts = { hour: "numeric", minute: "2-digit", timeZone: "UTC" } as const;
  return `${s.toLocaleTimeString([], opts)} - ${e.toLocaleTimeString([], opts)}`;
}

export function toBackendDateTime(value: Date) {
  const pad = (n: number) => String(n).padStart(2, "0");
  const year = value.getUTCFullYear();
  const month = pad(value.getUTCMonth() + 1);
  const day = pad(value.getUTCDate());
  const hours = pad(value.getUTCHours());
  const minutes = pad(value.getUTCMinutes());
  const seconds = pad(value.getUTCSeconds());
  return `${year}-${month}-${day}T${hours}:${minutes}:${seconds}`;
}

export function toMessage(detail: unknown, fallback: string): string {
  if (typeof detail === "string" && detail.trim()) return detail;
  if (Array.isArray(detail)) {
    const joined = detail
      .map((item) => (typeof item === "string" ? item : (item as { msg?: unknown })?.msg))
      .filter((item): item is string => typeof item === "string" && item.trim().length > 0)
      .join("; ");
    if (joined) return joined;
  }
  if (detail && typeof detail === "object") {
    const msg = (detail as { msg?: unknown }).msg;
    if (typeof msg === "string" && msg.trim()) return msg;
  }
  return fallback;
}

export function normalizeId(value: string) {
  return value.trim().toLowerCase();
}

export function buildCalendarDates(startDate: string, endDate: string) {
  if (!startDate || !endDate) return [] as Date[];
  const start = new Date(`${startDate}T00:00:00Z`);
  const end = new Date(`${endDate}T00:00:00Z`);
  if (Number.isNaN(start.getTime()) || Number.isNaN(end.getTime()) || end < start) return [] as Date[];

  const dates: Date[] = [];
  const cursor = new Date(start);
  while (cursor <= end) {
    dates.push(new Date(cursor));
    cursor.setUTCDate(cursor.getUTCDate() + 1);
  }
  return dates;
}

export function buildTimeframesFromGrid(dates: Date[], availability: boolean[][]) {
  if (dates.length === 0) return null;
  const tuples: [string, string][] = [];

  for (let dayIndex = 0; dayIndex < dates.length; dayIndex += 1) {
    let rangeStart: Date | null = null;
    let rangeEnd: Date | null = null;

    for (let slotIndex = 0; slotIndex < totalSlots; slotIndex += 1) {
      if (availability[dayIndex]?.[slotIndex]) {
        const slotStart = new Date(dates[dayIndex]);
        const startMinutes = 9 * 60 + slotIndex * 15;
        slotStart.setUTCHours(Math.floor(startMinutes / 60), startMinutes % 60, 0, 0);

        const slotEnd = new Date(slotStart);
        slotEnd.setUTCMinutes(slotEnd.getUTCMinutes() + 15);

        if (!rangeStart) {
          rangeStart = slotStart;
          rangeEnd = slotEnd;
        } else {
          rangeEnd = slotEnd;
        }
      } else if (rangeStart && rangeEnd) {
        tuples.push([toBackendDateTime(rangeStart), toBackendDateTime(rangeEnd)]);
        rangeStart = null;
        rangeEnd = null;
      }
    }

    if (rangeStart && rangeEnd) {
      tuples.push([toBackendDateTime(rangeStart), toBackendDateTime(rangeEnd)]);
    }
  }

  return tuples;
}

export function slotRange(start: Date, end: Date | null): { startSlot: number; slotSpan: number } {
  const startMinutes = start.getUTCHours() * 60 + start.getUTCMinutes();
  const endMinutes = end ? end.getUTCHours() * 60 + end.getUTCMinutes() : startMinutes + 15;
  return {
    startSlot: Math.floor((startMinutes - 9 * 60) / 15),
    slotSpan: Math.max(1, Math.ceil((endMinutes - startMinutes) / 15)),
  };
}

export function gridFromTimeframes(timeframes: TimeframeRecord[]) {
  if (timeframes.length === 0) return { startDate: "", endDate: "", availability: [] as boolean[][] };

  const dayKeys = timeframes
    .map((tf) => dayKey(parseBackendDateTime(tf.start_time)))
    .sort((a, b) => (a < b ? -1 : a > b ? 1 : 0));
  const startDate = dayKeys[0];
  const endDate = dayKeys[dayKeys.length - 1];
  const dates = buildCalendarDates(startDate, endDate);

  const dayIndexByKey = new Map<string, number>();
  dates.forEach((date, index) => dayIndexByKey.set(dayKey(date), index));

  const availability = Array.from({ length: dates.length }, () => Array.from({ length: totalSlots }, () => false));

  for (const timeframe of timeframes) {
    const start = parseBackendDateTime(timeframe.start_time);
    const di = dayIndexByKey.get(dayKey(start));
    if (di === undefined) continue;

    const end = timeframe.end_time ? parseBackendDateTime(timeframe.end_time) : null;
    const validEnd = end && !Number.isNaN(end.getTime()) ? end : null;
    const { startSlot, slotSpan } = slotRange(start, validEnd);

    for (let offset = 0; offset < slotSpan; offset += 1) {
      const slotIndex = startSlot + offset;
      if (slotIndex >= 0 && slotIndex < totalSlots) availability[di][slotIndex] = true;
    }
  }

  return { startDate, endDate, availability };
}

export type ConstraintMode = "off" | "soft" | "hard";

export type ScheduleConstraints = {
  roomConflicts: ConstraintMode;
  personConflicts: ConstraintMode;
  symposiumWindows: ConstraintMode;
  professorAvailability: ConstraintMode;
  studentAvailability: ConstraintMode;
  sameClassSameRoom: ConstraintMode;
  slotAlignment: 1 | 5 | 10 | 15 | 20;
  minimizeMakespan: ConstraintMode;
  minimizeClassSpan: ConstraintMode;
  minimizeProfessorSpan: ConstraintMode;
  balanceRooms: ConstraintMode;
};

export const DEFAULT_CONSTRAINTS: ScheduleConstraints = {
  roomConflicts: "hard",
  personConflicts: "hard",
  symposiumWindows: "hard",
  professorAvailability: "hard",
  studentAvailability: "hard",
  sameClassSameRoom: "hard",
  slotAlignment: 1,
  minimizeMakespan: "soft",
  minimizeClassSpan: "soft",
  minimizeProfessorSpan: "soft",
  balanceRooms: "soft",
};

export type ConflictContext = {
  allPresentations: SchedulePresentation[];
  personNames: Map<string, string>;
  roomNames?: Array<string | null>;
  constraints: ScheduleConstraints;
  symposiumTimeframes: Array<{ start_time: string; end_time: string }>;
  resourceAvailability: Map<string, Array<{ start_time: string; end_time: string }>>;
  professorIds: Set<string>;
  slotMinutes: number;
};

export type ConflictResult = {
  message: string;
  /** true = hard violation (blocks drop), false = soft warning (allows drop) */
  blocked: boolean;
};

/**
 * Detect scheduling constraint violations when placing a presentation at a given room/time.
 * Checks are controlled by `ctx.constraints` modes (off / soft / hard).
 * Returns the most severe conflict, or null if no violations.
 */
export function detectScheduleConflict(
  target: SchedulePresentation,
  room: number,
  startTime: Date,
  ctx: ConflictContext,
): ConflictResult | null {
  const { allPresentations, personNames, constraints } = ctx;
  const endTime = new Date(startTime.getTime() + target.minutes * 60 * 1000);
  const bufferMs = target.buffer * 60 * 1000;
  const newStart = startTime.getTime();
  const newEnd = endTime.getTime();
  const newBufferedEnd = newEnd + bufferMs;

  const hardViolations: string[] = [];
  const softViolations: string[] = [];

  function addViolation(mode: ConstraintMode, message: string) {
    if (mode === "hard") hardViolations.push(message);
    else if (mode === "soft") softViolations.push(message);
  }

  function roomLabel(roomIndex: number): string {
    const roomName = ctx.roomNames?.[roomIndex];
    return typeof roomName === "string" && roomName.trim() ? roomName.trim() : `Room ${roomIndex + 1}`;
  }

  // Slot alignment
  {
    const m = startTime.getUTCHours() * 60 + startTime.getUTCMinutes();
    if (m % constraints.slotAlignment !== 0) {
      addViolation("hard", `Start time must align to ${constraints.slotAlignment}-minute intervals.`);
    }
  }

  // Symposium window
  if (constraints.symposiumWindows !== "off" && ctx.symposiumTimeframes.length > 0) {
    const day = dayKey(startTime);
    const dayTfs = ctx.symposiumTimeframes.filter(
      (tf) => dayKey(parseBackendDateTime(tf.start_time)) === day,
    );
    const within = dayTfs.some((tf) => {
      const s = parseBackendDateTime(tf.start_time).getTime();
      const e = parseBackendDateTime(tf.end_time).getTime();
      return newStart >= s && newEnd <= e;
    });
    if (!within) {
      addViolation(constraints.symposiumWindows, "Presentation falls outside symposium hours.");
    }
  }

  // Professor availability
  if (constraints.professorAvailability !== "off") {
    for (const rid of target.resourceIds) {
      if (!ctx.professorIds.has(rid)) continue;
      const avail = ctx.resourceAvailability.get(rid);
      if (!avail || avail.length === 0) continue;
      const within = avail.some((tf) => {
        const s = parseBackendDateTime(tf.start_time).getTime();
        const e = parseBackendDateTime(tf.end_time).getTime();
        return newStart >= s && newEnd <= e;
      });
      if (!within) {
        const name = personNames.get(rid) ?? "A professor";
        addViolation(constraints.professorAvailability, `${name} is not available at this time.`);
      }
    }
  }

  // Student availability
  if (constraints.studentAvailability !== "off") {
    for (const rid of target.resourceIds) {
      if (ctx.professorIds.has(rid)) continue;
      const avail = ctx.resourceAvailability.get(rid);
      if (!avail || avail.length === 0) continue;
      const within = avail.some((tf) => {
        const s = parseBackendDateTime(tf.start_time).getTime();
        const e = parseBackendDateTime(tf.end_time).getTime();
        return newStart >= s && newEnd <= e;
      });
      if (!within) {
        const name = personNames.get(rid) ?? "A student";
        addViolation(constraints.studentAvailability, `${name} is not available at this time.`);
      }
    }
  }

  // Same class → same room
  if (constraints.sameClassSameRoom !== "off") {
    for (const other of allPresentations) {
      if (other.id === target.id) continue;
      if (other.class_id !== target.class_id) continue;
      if (other.room === null) continue;
      if (other.room !== room) {
        addViolation(constraints.sameClassSameRoom, `Class conflict: "${other.title}" from the same class is in ${roomLabel(other.room)}.`);
        break;
      }
    }
  }

  // Room and person overlap checks
  const targetResources = new Set(target.resourceIds);
  for (const other of allPresentations) {
    if (other.id === target.id) continue;
    if (other.room === null || !other.timeframe) continue;

    const otherStart = parseBackendDateTime(other.timeframe.start_time).getTime();
    const otherEnd = parseBackendDateTime(other.timeframe.end_time).getTime();
    const otherBufferedEnd = otherEnd + other.buffer * 60 * 1000;

    const overlap = newStart < otherBufferedEnd && newBufferedEnd > otherStart;
    if (!overlap) continue;

    if (constraints.roomConflicts !== "off" && other.room === room) {
      addViolation(constraints.roomConflicts, `Room conflict: ${roomLabel(room)} is already occupied by "${other.title}" (including buffer).`);
    }

    if (constraints.personConflicts !== "off") {
      const otherResources = new Set(other.resourceIds);
      for (const rid of targetResources) {
        if (otherResources.has(rid)) {
          const name = personNames.get(rid) ?? "Someone";
          addViolation(constraints.personConflicts, `Scheduling conflict: "${name}" is in both this and "${other.title}" (including buffer).`);
        }
      }
    }
  }

  if (hardViolations.length > 0) {
    return { message: hardViolations[0], blocked: true };
  }
  if (softViolations.length > 0) {
    return { message: softViolations[0], blocked: false };
  }
  return null;
}

export function parseCsvLine(line: string): string[] {
  const cells: string[] = [];
  let current = "";
  let inQuotes = false;

  for (let i = 0; i < line.length; i += 1) {
    const char = line[i];
    if (char === '"') {
      if (inQuotes && line[i + 1] === '"') {
        current += '"';
        i += 1;
      } else {
        inQuotes = !inQuotes;
      }
      continue;
    }
    if (char === "," && !inQuotes) {
      cells.push(current.trim());
      current = "";
      continue;
    }
    current += char;
  }
  cells.push(current.trim());
  return cells;
}

export function isUuid(value: string) {
  return /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(
    value.trim()
  );
}

export function buildCalendarFromTimeframes(
  symposiumTimeframes: Array<{ start_time?: string; end_time?: string }>,
  entityTimeframes: Array<{ start_time?: string; end_time?: string }>
): {
  calendarDays: CalendarDay[];
  editableSlots: boolean[][];
  availability: boolean[][];
} {
  const uniqueDayKeys = new Set<string>();
  const parsedRows: Array<{ start: Date; end: Date | null }> = [];
  for (const row of symposiumTimeframes) {
    if (!row.start_time) continue;
    const start = parseBackendDateTime(row.start_time);
    if (Number.isNaN(start.getTime())) continue;
    const end = row.end_time && row.end_time.trim().length > 0 ? parseBackendDateTime(row.end_time) : null;
    uniqueDayKeys.add(dayKey(start));
    parsedRows.push({ start, end: end && !Number.isNaN(end.getTime()) ? end : null });
  }

  const calendarDays = Array.from(uniqueDayKeys)
    .sort()
    .map((key) => ({
      key,
      label: formatCalendarDate(new Date(`${key}T00:00:00Z`)),
    }));

  const dayIndexByKey = new Map(calendarDays.map((day, index) => [day.key, index]));
  const editableSlots = Array.from({ length: calendarDays.length }, () =>
    Array.from({ length: totalSlots }, () => false)
  );
  const availability = Array.from({ length: calendarDays.length }, () =>
    Array.from({ length: totalSlots }, () => false)
  );

  for (const row of parsedRows) {
    const di = dayIndexByKey.get(dayKey(row.start));
    if (di === undefined) continue;
    const { startSlot, slotSpan } = slotRange(row.start, row.end);
    for (let offset = 0; offset < slotSpan; offset += 1) {
      const slotIndex = startSlot + offset;
      if (slotIndex >= 0 && slotIndex < totalSlots) {
        editableSlots[di][slotIndex] = true;
      }
    }
  }

  for (const row of entityTimeframes) {
    if (!row.start_time) continue;
    const start = parseBackendDateTime(row.start_time);
    if (Number.isNaN(start.getTime())) continue;
    const end = row.end_time && row.end_time.trim().length > 0 ? parseBackendDateTime(row.end_time) : null;
    const di = dayIndexByKey.get(dayKey(start));
    if (di === undefined) continue;
    const validEnd = end && !Number.isNaN(end.getTime()) ? end : null;
    const { startSlot, slotSpan } = slotRange(start, validEnd);
    for (let offset = 0; offset < slotSpan; offset += 1) {
      const slotIndex = startSlot + offset;
      if (slotIndex < 0 || slotIndex >= totalSlots) continue;
      if (!editableSlots[di]?.[slotIndex]) continue;
      availability[di][slotIndex] = true;
    }
  }

  return { calendarDays, editableSlots, availability };
}
