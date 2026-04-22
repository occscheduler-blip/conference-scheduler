import { describe, it, expect } from "vitest";
import {
  formatTimeLabel,
  dayKey,
  parseBackendDateTime,
  toBackendDateTime,
  toMessage,
  normalizeId,
  isUuid,
  parseCsvLine,
  buildCalendarDates,
  slotRange,
  buildTimeframesFromGrid,
  detectScheduleConflict,
  DEFAULT_CONSTRAINTS,
} from "../utils";
import type { SchedulePresentation, Timeframe } from "../../pages/types";
import type { ConflictContext } from "../utils";

// ---------------------------------------------------------------------------
// formatTimeLabel
// ---------------------------------------------------------------------------
describe("formatTimeLabel", () => {
  it("returns 9:00 AM for slot 0", () => {
    expect(formatTimeLabel(0)).toBe("9:00 AM");
  });

  it("returns 10:00 AM for slot 4", () => {
    expect(formatTimeLabel(4)).toBe("10:00 AM");
  });

  it("returns 12:00 PM for slot 12", () => {
    expect(formatTimeLabel(12)).toBe("12:00 PM");
  });

  it("returns 1:00 PM for slot 16", () => {
    expect(formatTimeLabel(16)).toBe("1:00 PM");
  });

  it("returns 8:45 PM for slot 47", () => {
    expect(formatTimeLabel(47)).toBe("8:45 PM");
  });
});

// ---------------------------------------------------------------------------
// dayKey
// ---------------------------------------------------------------------------
describe("dayKey", () => {
  it("formats a date as YYYY-MM-DD using UTC", () => {
    expect(dayKey(new Date("2024-01-15T00:00:00Z"))).toBe("2024-01-15");
  });

  it("pads single-digit month and day", () => {
    expect(dayKey(new Date("2024-03-05T00:00:00Z"))).toBe("2024-03-05");
  });

  it("handles December 31", () => {
    expect(dayKey(new Date("2024-12-31T00:00:00Z"))).toBe("2024-12-31");
  });
});

// ---------------------------------------------------------------------------
// parseBackendDateTime
// ---------------------------------------------------------------------------
describe("parseBackendDateTime", () => {
  it("treats naive datetime as UTC", () => {
    const result = parseBackendDateTime("2024-01-15T09:00:00");
    expect(result.toISOString()).toBe("2024-01-15T09:00:00.000Z");
  });

  it("strips trailing Z before re-adding it", () => {
    const result = parseBackendDateTime("2024-01-15T09:00:00Z");
    expect(result.toISOString()).toBe("2024-01-15T09:00:00.000Z");
  });

  it("strips positive timezone offset", () => {
    const result = parseBackendDateTime("2024-01-15T09:00:00+05:00");
    expect(result.toISOString()).toBe("2024-01-15T09:00:00.000Z");
  });

  it("strips negative timezone offset", () => {
    const result = parseBackendDateTime("2024-01-15T14:00:00-05:00");
    expect(result.toISOString()).toBe("2024-01-15T14:00:00.000Z");
  });
});

// ---------------------------------------------------------------------------
// toBackendDateTime
// ---------------------------------------------------------------------------
describe("toBackendDateTime", () => {
  it("formats a UTC date as YYYY-MM-DDTHH:MM:SS", () => {
    const date = new Date("2024-06-20T14:30:00Z");
    expect(toBackendDateTime(date)).toBe("2024-06-20T14:30:00");
  });

  it("pads hours and minutes", () => {
    const date = new Date("2024-01-01T09:05:00Z");
    expect(toBackendDateTime(date)).toBe("2024-01-01T09:05:00");
  });
});

// ---------------------------------------------------------------------------
// toMessage
// ---------------------------------------------------------------------------
describe("toMessage", () => {
  it("returns a string detail directly", () => {
    expect(toMessage("Bad request", "fallback")).toBe("Bad request");
  });

  it("returns fallback for empty string detail", () => {
    expect(toMessage("", "fallback")).toBe("fallback");
  });

  it("returns fallback for whitespace-only string", () => {
    expect(toMessage("   ", "fallback")).toBe("fallback");
  });

  it("joins array of string messages", () => {
    expect(toMessage(["err1", "err2"], "fallback")).toBe("err1; err2");
  });

  it("extracts msg from array of objects", () => {
    expect(toMessage([{ msg: "field error" }], "fallback")).toBe("field error");
  });

  it("filters empty items from array", () => {
    expect(toMessage(["err1", "", "err2"], "fallback")).toBe("err1; err2");
  });

  it("extracts msg from a plain object", () => {
    expect(toMessage({ msg: "object error" }, "fallback")).toBe("object error");
  });

  it("returns fallback for null", () => {
    expect(toMessage(null, "fallback")).toBe("fallback");
  });

  it("returns fallback for a number", () => {
    expect(toMessage(42, "fallback")).toBe("fallback");
  });
});

// ---------------------------------------------------------------------------
// normalizeId
// ---------------------------------------------------------------------------
describe("normalizeId", () => {
  it("trims and lowercases", () => {
    expect(normalizeId("  Hello  ")).toBe("hello");
  });

  it("lowercases all caps", () => {
    expect(normalizeId("ABC")).toBe("abc");
  });

  it("handles already lowercase", () => {
    expect(normalizeId("test")).toBe("test");
  });
});

// ---------------------------------------------------------------------------
// isUuid
// ---------------------------------------------------------------------------
describe("isUuid", () => {
  it("accepts a valid v4 UUID", () => {
    expect(isUuid("123e4567-e89b-42d3-a456-426614174000")).toBe(true);
  });

  it("accepts UUID with leading/trailing whitespace", () => {
    expect(isUuid("  123e4567-e89b-42d3-a456-426614174000  ")).toBe(true);
  });

  it("rejects a plain string", () => {
    expect(isUuid("not-a-uuid")).toBe(false);
  });

  it("rejects an empty string", () => {
    expect(isUuid("")).toBe(false);
  });

  it("rejects a UUID with invalid version (6)", () => {
    expect(isUuid("123e4567-e89b-62d3-a456-426614174000")).toBe(false);
  });

  it("is case-insensitive", () => {
    expect(isUuid("123E4567-E89B-42D3-A456-426614174000")).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// parseCsvLine
// ---------------------------------------------------------------------------
describe("parseCsvLine", () => {
  it("splits a simple comma-separated line", () => {
    expect(parseCsvLine("a,b,c")).toEqual(["a", "b", "c"]);
  });

  it("handles quoted field containing a comma", () => {
    expect(parseCsvLine('"hello, world",test')).toEqual(["hello, world", "test"]);
  });

  it("handles escaped double-quotes inside a quoted field", () => {
    expect(parseCsvLine('"say ""hi""",name')).toEqual(['say "hi"', "name"]);
  });

  it("returns single-element array for no commas", () => {
    expect(parseCsvLine("hello")).toEqual(["hello"]);
  });

  it("trims whitespace around unquoted fields", () => {
    expect(parseCsvLine(" a , b ")).toEqual(["a", "b"]);
  });
});

// ---------------------------------------------------------------------------
// buildCalendarDates
// ---------------------------------------------------------------------------
describe("buildCalendarDates", () => {
  it("returns dates for a valid range", () => {
    const dates = buildCalendarDates("2024-01-15", "2024-01-17");
    expect(dates).toHaveLength(3);
    expect(dayKey(dates[0])).toBe("2024-01-15");
    expect(dayKey(dates[2])).toBe("2024-01-17");
  });

  it("returns a single date when start equals end", () => {
    const dates = buildCalendarDates("2024-01-15", "2024-01-15");
    expect(dates).toHaveLength(1);
  });

  it("returns empty array when end is before start", () => {
    expect(buildCalendarDates("2024-01-17", "2024-01-15")).toEqual([]);
  });

  it("returns empty array for empty strings", () => {
    expect(buildCalendarDates("", "")).toEqual([]);
  });

  it("returns empty array for invalid dates", () => {
    expect(buildCalendarDates("invalid", "2024-01-15")).toEqual([]);
  });
});

// ---------------------------------------------------------------------------
// slotRange
// ---------------------------------------------------------------------------
describe("slotRange", () => {
  it("returns slot 0 with span 1 for 9:00 and no end", () => {
    const start = new Date("2024-01-15T09:00:00Z");
    expect(slotRange(start, null)).toEqual({ startSlot: 0, slotSpan: 1 });
  });

  it("returns correct slot for 9:15", () => {
    const start = new Date("2024-01-15T09:15:00Z");
    expect(slotRange(start, null)).toEqual({ startSlot: 1, slotSpan: 1 });
  });

  it("returns span of 4 for a one-hour slot", () => {
    const start = new Date("2024-01-15T09:00:00Z");
    const end = new Date("2024-01-15T10:00:00Z");
    expect(slotRange(start, end)).toEqual({ startSlot: 0, slotSpan: 4 });
  });

  it("returns span of 1 for a 15-minute slot", () => {
    const start = new Date("2024-01-15T09:15:00Z");
    const end = new Date("2024-01-15T09:30:00Z");
    expect(slotRange(start, end)).toEqual({ startSlot: 1, slotSpan: 1 });
  });
});

// ---------------------------------------------------------------------------
// buildTimeframesFromGrid
// ---------------------------------------------------------------------------
describe("buildTimeframesFromGrid", () => {
  it("returns null for empty dates", () => {
    expect(buildTimeframesFromGrid([], [])).toBeNull();
  });

  it("converts a single selected slot to a timeframe tuple", () => {
    const date = new Date("2024-01-15T00:00:00Z");
    // slot 0 = 9:00–9:15
    const availability = [[true, false, false]];
    const result = buildTimeframesFromGrid([date], availability);
    expect(result).toEqual([["2024-01-15T09:00:00", "2024-01-15T09:15:00"]]);
  });

  it("merges consecutive slots into one timeframe", () => {
    const date = new Date("2024-01-15T00:00:00Z");
    // slots 0,1,2 = 9:00–9:45
    const availability = [[true, true, true, false]];
    const result = buildTimeframesFromGrid([date], availability);
    expect(result).toEqual([["2024-01-15T09:00:00", "2024-01-15T09:45:00"]]);
  });

  it("creates separate timeframes for non-consecutive slots", () => {
    const date = new Date("2024-01-15T00:00:00Z");
    // slots 0 and 2, gap at 1
    const availability = [[true, false, true, false]];
    const result = buildTimeframesFromGrid([date], availability);
    expect(result).toHaveLength(2);
  });
});

// ---------------------------------------------------------------------------
// detectScheduleConflict
// ---------------------------------------------------------------------------

function makePresentation(overrides: Partial<SchedulePresentation> = {}): SchedulePresentation {
  return {
    id: "p1",
    title: "Test Presentation",
    class_id: "c1",
    minutes: 30,
    buffer: 0,
    room: null,
    timeframe: null,
    presenterNames: [],
    departmentName: "CS",
    resourceIds: [],
    ...overrides,
  };
}

function makeCtx(overrides: Partial<ConflictContext> = {}): ConflictContext {
  return {
    allPresentations: [],
    personNames: new Map(),
    constraints: { ...DEFAULT_CONSTRAINTS, slotAlignment: 1 },
    symposiumTimeframes: [],
    resourceAvailability: new Map(),
    professorIds: new Set(),
    slotMinutes: 15,
    ...overrides,
  };
}

describe("detectScheduleConflict", () => {
  it("returns null when there are no conflicts", () => {
    const target = makePresentation();
    const ctx = makeCtx();
    const start = new Date("2024-01-15T09:00:00Z");
    expect(detectScheduleConflict(target, 0, start, ctx)).toBeNull();
  });

  it("blocks on room conflict (hard)", () => {
    const other: SchedulePresentation = makePresentation({
      id: "p2",
      title: "Other",
      room: 0,
      timeframe: {
        id: "tf1",
        start_time: "2024-01-15T09:00:00",
        end_time: "2024-01-15T09:30:00",
      } as Timeframe,
    });
    const target = makePresentation();
    const ctx = makeCtx({ allPresentations: [other] });
    const start = new Date("2024-01-15T09:00:00Z");
    const result = detectScheduleConflict(target, 0, start, ctx);
    expect(result).not.toBeNull();
    expect(result!.blocked).toBe(true);
    expect(result!.message).toMatch(/Room conflict/);
  });

  it("blocks on person conflict when same resource is double-booked", () => {
    const other: SchedulePresentation = makePresentation({
      id: "p2",
      title: "Other",
      class_id: "c2",
      room: 1,
      resourceIds: ["person-1"],
      timeframe: {
        id: "tf1",
        start_time: "2024-01-15T09:00:00",
        end_time: "2024-01-15T09:30:00",
      } as Timeframe,
    });
    const target = makePresentation({ resourceIds: ["person-1"] });
    const ctx = makeCtx({
      allPresentations: [other],
      personNames: new Map([["person-1", "Alice"]]),
    });
    const start = new Date("2024-01-15T09:00:00Z");
    const result = detectScheduleConflict(target, 0, start, ctx);
    expect(result).not.toBeNull();
    expect(result!.blocked).toBe(true);
    expect(result!.message).toMatch(/Alice/);
  });

  it("warns (soft) when outside symposium window with soft constraint", () => {
    const target = makePresentation();
    const ctx = makeCtx({
      constraints: {
        ...DEFAULT_CONSTRAINTS,
        slotAlignment: 1,
        symposiumWindows: "soft",
      },
      symposiumTimeframes: [
        { start_time: "2024-01-15T10:00:00", end_time: "2024-01-15T12:00:00" },
      ],
    });
    const start = new Date("2024-01-15T09:00:00Z");
    const result = detectScheduleConflict(target, 0, start, ctx);
    expect(result).not.toBeNull();
    expect(result!.blocked).toBe(false);
    expect(result!.message).toMatch(/symposium/i);
  });

  it("blocks when outside symposium window with hard constraint", () => {
    const target = makePresentation();
    const ctx = makeCtx({
      constraints: {
        ...DEFAULT_CONSTRAINTS,
        slotAlignment: 1,
        symposiumWindows: "hard",
      },
      symposiumTimeframes: [
        { start_time: "2024-01-15T10:00:00", end_time: "2024-01-15T12:00:00" },
      ],
    });
    const start = new Date("2024-01-15T09:00:00Z");
    const result = detectScheduleConflict(target, 0, start, ctx);
    expect(result).not.toBeNull();
    expect(result!.blocked).toBe(true);
  });

  it("blocks on slot alignment violation", () => {
    const target = makePresentation();
    const ctx = makeCtx({
      constraints: { ...DEFAULT_CONSTRAINTS, slotAlignment: 15 },
    });
    const start = new Date("2024-01-15T09:07:00Z");
    const result = detectScheduleConflict(target, 0, start, ctx);
    expect(result).not.toBeNull();
    expect(result!.blocked).toBe(true);
    expect(result!.message).toMatch(/align/);
  });

  it("returns null when presentation is within symposium window", () => {
    const target = makePresentation();
    const ctx = makeCtx({
      constraints: { ...DEFAULT_CONSTRAINTS, slotAlignment: 1 },
      symposiumTimeframes: [
        { start_time: "2024-01-15T09:00:00", end_time: "2024-01-15T12:00:00" },
      ],
    });
    const start = new Date("2024-01-15T09:00:00Z");
    expect(detectScheduleConflict(target, 0, start, ctx)).toBeNull();
  });

  it("warns about professor availability when outside available window", () => {
    const profId = "prof-1";
    const target = makePresentation({ resourceIds: [profId] });
    const ctx = makeCtx({
      professorIds: new Set([profId]),
      personNames: new Map([[profId, "Dr. Smith"]]),
      resourceAvailability: new Map([
        [profId, [{ start_time: "2024-01-15T10:00:00", end_time: "2024-01-15T12:00:00" }]],
      ]),
    });
    const start = new Date("2024-01-15T09:00:00Z");
    const result = detectScheduleConflict(target, 0, start, ctx);
    expect(result).not.toBeNull();
    expect(result!.message).toMatch(/Dr. Smith/);
  });
});
