"use client";

import type { RefObject } from "react";
import type { Timeframe } from "../pages/types";
import { formatTimeLabel, parseBackendDateTime } from "./utils";

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
  minSlot: number;
  maxSlot: number;
  blocks: GridBlock[];
  gridRef?: RefObject<HTMLDivElement | null>;
  onBlockClick?: (id: string) => void;
  onBlockPointerDown?: (e: React.PointerEvent<HTMLDivElement>, id: string) => void;
  draggingId?: string | null;
  isDragging?: boolean;
  snapTarget?: GridSnapTarget | null;
};

export function ScheduleGrid({
  roomsAvailable,
  roomNames,
  minSlot,
  maxSlot,
  blocks,
  gridRef,
  onBlockClick,
  onBlockPointerDown,
  draggingId,
  isDragging,
  snapTarget,
}: Props) {
  const visibleSlotCount = maxSlot - minSlot;

  return (
    <div
      ref={gridRef}
      className="grid"
      style={{
        gridTemplateColumns: `72px repeat(${roomsAvailable}, minmax(140px, 1fr))`,
        gridTemplateRows: `auto repeat(${visibleSlotCount}, ${SLOT_HEIGHT}px)`,
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

      {/* Time slot background cells */}
      {Array.from({ length: visibleSlotCount }, (_, i) => {
        const slotIndex = minSlot + i;
        const showLabel = slotIndex % 2 === 0;
        const gridRow = i + 2;
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

      {/* Presentation blocks */}
      {blocks.map((block) => {
        const start = parseBackendDateTime(block.timeframe.start_time);
        const end = parseBackendDateTime(block.timeframe.end_time);
        const startMinutes = start.getUTCHours() * 60 + start.getUTCMinutes();
        const endMinutes = end.getUTCHours() * 60 + end.getUTCMinutes();
        const startSlotRaw = (startMinutes - 9 * 60) / 15;
        const endSlotRaw = (endMinutes - 9 * 60) / 15;

        const gridRowStart = Math.floor(startSlotRaw - minSlot) + 2;
        const gridRowEnd = Math.ceil(endSlotRaw - minSlot) + 2;
        const gridCol = block.roomIndex + 2;

        const fracStart = startSlotRaw - minSlot - Math.floor(startSlotRaw - minSlot);
        const verticalInset = 1;
        const topOffset = fracStart * SLOT_HEIGHT + verticalInset;
        const blockHeight = Math.max(8, (endSlotRaw - startSlotRaw) * SLOT_HEIGHT - verticalInset * 2);
        const durationSlots = endSlotRaw - startSlotRaw;
        const isBeingDragged = draggingId === block.id;

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
            {durationSlots > 1 ? (
              <div className="truncate text-[10px] leading-tight opacity-80">
                {block.presenterNames.join(", ") || "No presenters"}
              </div>
            ) : null}
            {durationSlots > 2 && block.durationMinutes !== undefined ? (
              <div className="truncate text-[10px] leading-tight opacity-60">
                {block.durationMinutes} min
              </div>
            ) : null}
          </div>
        );
      })}

      {/* Snap-target highlight during drag (schedule editor only) */}
      {snapTarget ? (() => {
        const { room, minuteInDay, durationMinutes, conflict } = snapTarget;
        const relativeSlot = (minuteInDay - 9 * 60) / 15 - minSlot;
        const durationSlots = durationMinutes / 15;
        const gridRowStart = Math.floor(relativeSlot) + 2;
        const gridRowEnd = Math.ceil(relativeSlot + durationSlots) + 2;
        const gridCol = room + 2;
        const topOffset = (relativeSlot - Math.floor(relativeSlot)) * SLOT_HEIGHT;
        const blockHeight = durationSlots * SLOT_HEIGHT;
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
