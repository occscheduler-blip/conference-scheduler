"use client";

import type { RefObject } from "react";
import type { Timeframe } from "../pages/types";
import { parseBackendDateTime } from "./utils";
import {
  formatMinutesOfDay,
  slotIsHalfHourBoundary,
  slotIsHourBoundary,
  type GridGeometry,
} from "./useGridGeometry";

export const SLOT_HEIGHT = 24;

export function getRoomLabel(
  roomNames: Array<string | null> | null | undefined,
  roomIndex: number,
): string {
  const name = roomNames?.[roomIndex];
  return typeof name === "string" && name.trim() ? name.trim() : `Room ${roomIndex + 1}`;
}

export type GridBlock = {
  id: string;
  timeframe: Timeframe;
  roomIndex: number;
  title: string;
  presenterNames: string[];
  color: { bg: string; text: string };
  durationMinutes?: number;
};

export type GridSnapTarget = {
  room: number;
  minuteInDay: number;
  durationMinutes: number;
  conflict: { blocked: boolean; message: string } | null;
};

type Props = {
  roomsAvailable: number;
  roomNames: Array<string | null>;
  geometry: GridGeometry;
  blocks: GridBlock[];
  gridRef?: RefObject<HTMLDivElement | null>;
  onBlockClick?: (id: string) => void;
  onBlockPointerDown?: (e: React.PointerEvent<HTMLDivElement>, id: string) => void;
  draggingId?: string | null;
  isDragging?: boolean;
  snapTarget?: GridSnapTarget | null;
};

function pickLabelStride(geometry: GridGeometry): (slotIndex: number) => boolean {
  if (geometry.slotMinutes >= 60) return () => true;
  if (60 % geometry.slotMinutes === 0) {
    return (slotIndex) => slotIsHourBoundary(geometry, slotIndex);
  }
  if (30 % geometry.slotMinutes === 0) {
    return (slotIndex) => slotIsHalfHourBoundary(geometry, slotIndex);
  }
  return (slotIndex) => slotIndex % Math.max(1, Math.round(60 / geometry.slotMinutes)) === 0;
}

export function ScheduleGrid({
  roomsAvailable,
  roomNames,
  geometry,
  blocks,
  gridRef,
  onBlockClick,
  onBlockPointerDown,
  draggingId,
  isDragging,
  snapTarget,
}: Props) {
  const { slotsPerDay, slotMinutes, slotPx, gridStartMinutes } = geometry;
  const showLabel = pickLabelStride(geometry);

  return (
    <div
      ref={gridRef}
      className="grid"
      style={{
        gridTemplateColumns: `72px repeat(${roomsAvailable}, minmax(140px, 1fr))`,
        gridTemplateRows: `auto repeat(${slotsPerDay}, ${slotPx}px)`,
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

      {/* Time slot background cells.
       * The lattice has `slotsPerDay` rows so cards can sit at slot-aligned
       * positions, but borders only render on 15-minute boundaries (and
       * hour-boundary rows pick up the legacy gray background) — this keeps
       * the grid visually identical to the old 15-min look regardless of the
       * underlying granularity. */}
      {Array.from({ length: slotsPerDay }, (_, i) => {
        const minuteAtSlot = gridStartMinutes + i * slotMinutes;
        const nextMinute = minuteAtSlot + slotMinutes;
        const onHour = minuteAtSlot % 60 === 0;
        const showBorder = nextMinute % 15 === 0 || i === slotsPerDay - 1;
        const gridRow = i + 2;
        const borderClass = showBorder ? "border-b border-[#e5e7eb]" : "";
        const bgClass = onHour ? "bg-[#f9fafb]" : "bg-white";
        return (
          <div key={`time-${i}`} className="contents">
            <div
              className={`flex items-center justify-end border-r border-[#e5e7eb] px-1 text-[11px] leading-none text-[#888] ${borderClass} ${bgClass}`}
              style={{ gridRow, gridColumn: 1 }}
            >
              {showLabel(i) ? formatMinutesOfDay(minuteAtSlot) : ""}
            </div>
            {Array.from({ length: roomsAvailable }, (_, roomIdx) => (
              <div
                key={roomIdx}
                className={`border-r border-[#e5e7eb] last:border-r-0 ${borderClass} ${bgClass}`}
                style={{ gridRow, gridColumn: roomIdx + 2 }}
              />
            ))}
          </div>
        );
      })}

      {/* Presentation blocks — positioned by minute offset, not slot index */}
      {blocks.map((block) => {
        const start = parseBackendDateTime(block.timeframe.start_time);
        const end = parseBackendDateTime(block.timeframe.end_time);
        const startMinutes = start.getUTCHours() * 60 + start.getUTCMinutes();
        const endMinutes = end.getUTCHours() * 60 + end.getUTCMinutes();
        const durationMinutes = Math.max(0, endMinutes - startMinutes);
        const offsetFromGrid = startMinutes - gridStartMinutes;

        const startRowFloat = offsetFromGrid / slotMinutes;
        const endRowFloat = (offsetFromGrid + durationMinutes) / slotMinutes;
        const gridRowStart = Math.floor(startRowFloat) + 2;
        const gridRowEnd = Math.max(gridRowStart + 1, Math.ceil(endRowFloat) + 2);
        const gridCol = block.roomIndex + 2;

        const verticalInset = 1;
        const topOffset = (offsetFromGrid / slotMinutes - Math.floor(startRowFloat)) * slotPx + verticalInset;
        const blockHeight = Math.max(8, (durationMinutes / slotMinutes) * slotPx - verticalInset * 2);
        const isBeingDragged = draggingId === block.id;
        const isShortBlock = durationMinutes < slotMinutes * 2;

        return (
          <div
            key={block.id}
            onClick={onBlockClick ? () => onBlockClick(block.id) : undefined}
            onPointerDown={onBlockPointerDown ? (e) => onBlockPointerDown(e, block.id) : undefined}
            className={`z-10 mx-[1px] overflow-hidden rounded-md px-1.5 py-0.5 text-left shadow-sm transition hover:brightness-110 hover:shadow-md ${isBeingDragged ? "opacity-30" : ""}`}
            style={{
              gridRow: `${gridRowStart} / ${gridRowEnd}`,
              gridColumn: gridCol,
              backgroundColor: block.color.bg,
              color: block.color.text,
              position: "relative",
              top: `${topOffset}px`,
              height: `${blockHeight}px`,
              alignSelf: "start",
              touchAction: "none",
              cursor: isDragging ? "grabbing" : onBlockPointerDown ? "grab" : "pointer",
            }}
            title={`${block.title}\n${block.presenterNames.join(", ")}`}
          >
            <div className="truncate text-xs font-semibold leading-tight">{block.title}</div>
            {!isShortBlock ? (
              <div className="truncate text-[10px] leading-tight opacity-80">
                {block.presenterNames.join(", ") || "No presenters"}
              </div>
            ) : null}
            {durationMinutes >= slotMinutes * 3 && block.durationMinutes !== undefined ? (
              <div className="truncate text-[10px] leading-tight opacity-60">
                {block.durationMinutes} min
              </div>
            ) : null}
          </div>
        );
      })}

      {/* Snap-target highlight during drag */}
      {snapTarget ? (() => {
        const { room, minuteInDay, durationMinutes, conflict } = snapTarget;
        const offsetFromGrid = minuteInDay - gridStartMinutes;
        const startRowFloat = offsetFromGrid / slotMinutes;
        const endRowFloat = (offsetFromGrid + durationMinutes) / slotMinutes;
        const gridRowStart = Math.floor(startRowFloat) + 2;
        const gridRowEnd = Math.max(gridRowStart + 1, Math.ceil(endRowFloat) + 2);
        const gridCol = room + 2;
        const topOffset = (startRowFloat - Math.floor(startRowFloat)) * slotPx;
        const blockHeight = (durationMinutes / slotMinutes) * slotPx;
        const isBlocked = conflict?.blocked === true;
        const isWarning = conflict !== null && conflict !== undefined && !conflict.blocked;

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
              <div
                className={`truncate px-1.5 py-0.5 text-[10px] font-semibold ${
                  isBlocked ? "text-[#c62828]" : "text-[#b36b00]"
                }`}
              >
                {isWarning ? "Warning: " : ""}
                {conflict.message}
              </div>
            ) : null}
          </div>
        );
      })() : null}
    </div>
  );
}
