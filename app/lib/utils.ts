import type { TimeframeRecord } from "../pages/types";

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
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

export function formatCalendarDate(date: Date) {
  return date.toLocaleDateString(undefined, {
    weekday: "short",
    month: "short",
    day: "numeric",
  });
}

export function parseBackendDateTime(value: string) {
  const hasExplicitTimezone = /(?:Z|[+\-]\d{2}:\d{2})$/i.test(value);
  return new Date(hasExplicitTimezone ? value : `${value}Z`);
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
  const start = new Date(`${startDate}T00:00:00`);
  const end = new Date(`${endDate}T00:00:00`);
  if (Number.isNaN(start.getTime()) || Number.isNaN(end.getTime()) || end < start) return [] as Date[];

  const dates: Date[] = [];
  const cursor = new Date(start);
  while (cursor <= end) {
    dates.push(new Date(cursor));
    cursor.setDate(cursor.getDate() + 1);
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
        slotStart.setHours(Math.floor(startMinutes / 60), startMinutes % 60, 0, 0);

        const slotEnd = new Date(slotStart);
        slotEnd.setMinutes(slotEnd.getMinutes() + 15);

        if (!rangeStart) {
          rangeStart = slotStart;
          rangeEnd = slotEnd;
        } else {
          rangeEnd = slotEnd;
        }
      } else if (rangeStart && rangeEnd) {
        tuples.push([rangeStart.toISOString(), rangeEnd.toISOString()]);
        rangeStart = null;
        rangeEnd = null;
      }
    }

    if (rangeStart && rangeEnd) {
      tuples.push([rangeStart.toISOString(), rangeEnd.toISOString()]);
    }
  }

  return tuples;
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

    const startMinutes = start.getHours() * 60 + start.getMinutes();
    const end = timeframe.end_time ? parseBackendDateTime(timeframe.end_time) : null;
    const endMinutes = end && !Number.isNaN(end.getTime()) ? end.getHours() * 60 + end.getMinutes() : startMinutes + 15;
    const startSlot = Math.floor((startMinutes - 9 * 60) / 15);
    const slotSpan = Math.max(1, Math.ceil((endMinutes - startMinutes) / 15));

    for (let offset = 0; offset < slotSpan; offset += 1) {
      const slotIndex = startSlot + offset;
      if (slotIndex >= 0 && slotIndex < totalSlots) availability[di][slotIndex] = true;
    }
  }

  return { startDate, endDate, availability };
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
