"use client";

import { formatTimeLabel, totalSlots } from "../lib/utils";
import {
  formatMinutesOfDay,
  slotIsHourBoundary,
  type GridGeometry,
} from "../lib/useGridGeometry";
import type { CalendarDay } from "../pages/types";

type WeekPagination = {
  visibleDayIndices: number[];
};

type AvailabilityGridProps = {
  calendarDays: CalendarDay[];
  availability: boolean[][];
  /** When omitted, every slot in every day is editable. */
  editableSlots?: boolean[][];
  /** When omitted, falls back to legacy 9 AM–9 PM 15-min slots from utils. */
  geometry?: GridGeometry;
  weekPagination: WeekPagination;
  handleCellMouseDown: (dayIndex: number, slotIndex: number) => void;
  handleCellMouseEnter: (dayIndex: number, slotIndex: number) => void;
  /** "md" (default) → 24px cells / 90px time column. "sm" → 16px cells / 64px time column. */
  cellSize?: "sm" | "md";
  /** Min width of the inner grid container — keeps the calendar legible at narrow viewports. */
  minWidthPx?: number;
  /** Extra classes for the day-header row (e.g., font sizing). */
  dayHeaderClassName?: string;
  /** Extra classes for the day-header cells. */
  dayHeaderCellClassName?: string;
};

export function AvailabilityGrid({
  calendarDays,
  availability,
  editableSlots,
  geometry,
  weekPagination,
  handleCellMouseDown,
  handleCellMouseEnter,
  cellSize = "md",
  minWidthPx = 720,
  dayHeaderClassName = "text-2xl",
  dayHeaderCellClassName = "text-sm md:text-lg",
}: AvailabilityGridProps) {
  const slotsPerDay = geometry ? geometry.slotsPerDay : totalSlots;
  const cellHeightClass = cellSize === "sm" ? "h-4" : "h-6";
  const labelLeadingClass = cellSize === "sm" ? "leading-4" : "leading-6";
  const labelFontClass = cellSize === "sm" ? "text-[11px]" : "text-sm";
  const timeColumnPx = cellSize === "sm" ? 64 : 90;
  const minColumnPx = cellSize === "sm" ? 80 : 120;
  const gridColumns = `${timeColumnPx}px repeat(${weekPagination.visibleDayIndices.length}, minmax(${minColumnPx}px, 1fr))`;

  return (
    <div className="select-none" style={{ minWidth: `${minWidthPx}px` }}>
      <div
        className={`grid text-center font-bold text-[#222] ${dayHeaderClassName}`}
        style={{ gridTemplateColumns: gridColumns }}
      >
        <div />
        {weekPagination.visibleDayIndices.map((di) => (
          <div key={calendarDays[di].key} className={`border-b border-[#777] pb-1 ${dayHeaderCellClassName}`}>
            {calendarDays[di].label}
          </div>
        ))}
      </div>
      <div className="grid" style={{ gridTemplateColumns: gridColumns }}>
        {Array.from({ length: slotsPerDay }, (_, slotIndex) => {
          const showHourLine = geometry
            ? slotIsHourBoundary(geometry, slotIndex)
            : slotIndex % 4 === 0;
          const labelText = geometry
            ? showHourLine
              ? formatMinutesOfDay(geometry.gridStartMinutes + slotIndex * geometry.slotMinutes)
              : ""
            : showHourLine
              ? formatTimeLabel(slotIndex)
              : "";
          return (
            <div key={slotIndex} className="contents">
              <div className={`${cellHeightClass} overflow-hidden pr-2 text-right ${labelFontClass} ${labelLeadingClass} font-semibold text-[#444]`}>
                {labelText}
              </div>
              {weekPagination.visibleDayIndices.map((dayIndex) => {
                const day = calendarDays[dayIndex];
                const available = availability[dayIndex]?.[slotIndex] ?? false;
                const editable = editableSlots ? (editableSlots[dayIndex]?.[slotIndex] ?? false) : true;
                const ariaTime = geometry
                  ? formatMinutesOfDay(geometry.gridStartMinutes + slotIndex * geometry.slotMinutes)
                  : formatTimeLabel(slotIndex);
                return (
                  <button
                    key={`${dayIndex}-${slotIndex}`}
                    type="button"
                    onMouseDown={() => handleCellMouseDown(dayIndex, slotIndex)}
                    onMouseEnter={() => handleCellMouseEnter(dayIndex, slotIndex)}
                    onDragStart={(event) => event.preventDefault()}
                    disabled={!editable}
                    className={`${cellHeightClass} border-r border-l border-b border-[#333] ${
                      showHourLine ? "border-t border-t-[#333]" : ""
                    } ${
                      !editable ? "cursor-not-allowed bg-[#d1d5db]" : available ? "bg-[#38a000]" : "bg-[#f0d7d9]"
                    }`}
                    aria-label={`${day.label} ${ariaTime}`}
                  />
                );
              })}
            </div>
          );
        })}
      </div>
    </div>
  );
}

export default AvailabilityGrid;
