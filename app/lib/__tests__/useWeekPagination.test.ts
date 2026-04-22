import { describe, it, expect } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useWeekPagination } from "../useWeekPagination";

// A week of dates guaranteed to fall in the same calendar week (Mon–Sun)
const SINGLE_WEEK = [
  "2024-01-15", // Mon
  "2024-01-16", // Tue
  "2024-01-17", // Wed
  "2024-01-18", // Thu
  "2024-01-19", // Fri
];

// Two distinct calendar weeks
const TWO_WEEKS = [
  "2024-01-15", // Mon week 1
  "2024-01-16",
  "2024-01-17",
  "2024-01-18",
  "2024-01-19",
  "2024-01-22", // Mon week 2
  "2024-01-23",
  "2024-01-24",
];

describe("useWeekPagination", () => {
  it("returns empty state for an empty array", () => {
    const { result } = renderHook(() => useWeekPagination([]));
    expect(result.current.hasMultipleWeeks).toBe(false);
    expect(result.current.visibleDayIndices).toEqual([]);
    expect(result.current.totalWeeks).toBe(0);
  });

  it("shows all indices for a single week", () => {
    const { result } = renderHook(() => useWeekPagination(SINGLE_WEEK));
    expect(result.current.hasMultipleWeeks).toBe(false);
    expect(result.current.visibleDayIndices).toEqual([0, 1, 2, 3, 4]);
    expect(result.current.totalWeeks).toBe(1);
  });

  it("starts on week 1 for multiple weeks", () => {
    const { result } = renderHook(() => useWeekPagination(TWO_WEEKS));
    expect(result.current.hasMultipleWeeks).toBe(true);
    expect(result.current.weekNumber).toBe(1);
    expect(result.current.totalWeeks).toBe(2);
    // First 5 days belong to week 1
    expect(result.current.visibleDayIndices).toEqual([0, 1, 2, 3, 4]);
  });

  it("navigates to the next week with nextWeek()", () => {
    const { result } = renderHook(() => useWeekPagination(TWO_WEEKS));
    act(() => result.current.nextWeek());
    expect(result.current.weekNumber).toBe(2);
    expect(result.current.visibleDayIndices).toEqual([5, 6, 7]);
  });

  it("navigates back with prevWeek()", () => {
    const { result } = renderHook(() => useWeekPagination(TWO_WEEKS));
    act(() => result.current.nextWeek());
    act(() => result.current.prevWeek());
    expect(result.current.weekNumber).toBe(1);
  });

  it("does not go below week 1 when calling prevWeek repeatedly", () => {
    const { result } = renderHook(() => useWeekPagination(TWO_WEEKS));
    act(() => result.current.prevWeek());
    act(() => result.current.prevWeek());
    expect(result.current.weekNumber).toBe(1);
  });

  it("does not go past the last week when calling nextWeek repeatedly", () => {
    const { result } = renderHook(() => useWeekPagination(TWO_WEEKS));
    act(() => result.current.nextWeek());
    act(() => result.current.nextWeek());
    act(() => result.current.nextWeek());
    expect(result.current.weekNumber).toBe(2);
  });

  it("hasPrev is false on first week", () => {
    const { result } = renderHook(() => useWeekPagination(TWO_WEEKS));
    expect(result.current.hasPrev).toBe(false);
  });

  it("hasPrev is true after advancing a week", () => {
    const { result } = renderHook(() => useWeekPagination(TWO_WEEKS));
    act(() => result.current.nextWeek());
    expect(result.current.hasPrev).toBe(true);
  });

  it("hasNext is false on the last week", () => {
    const { result } = renderHook(() => useWeekPagination(TWO_WEEKS));
    act(() => result.current.nextWeek());
    expect(result.current.hasNext).toBe(false);
  });

  it("hasNext is true on the first week when there are multiple weeks", () => {
    const { result } = renderHook(() => useWeekPagination(TWO_WEEKS));
    expect(result.current.hasNext).toBe(true);
  });
});
