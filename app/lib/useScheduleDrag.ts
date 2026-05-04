"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { SchedulePresentation } from "../pages/types";
import { type ConflictContext, type ConflictResult, detectScheduleConflict } from "./utils";

const DRAG_THRESHOLD = 5; // px — movement before we treat pointerdown as a drag
const SLOT_HEIGHT = 24;
const TIME_COL_WIDTH = 72;

export type SnapTarget = {
  room: number;
  /** Total minutes from midnight — minute-level precision */
  minuteInDay: number;
  startTime: Date;
};

export type DragState = {
  presentation: SchedulePresentation;
  /** Offset from cursor to block top-left at drag start */
  offsetX: number;
  offsetY: number;
  /** Current cursor position (viewport) */
  currentX: number;
  currentY: number;
  /** Snapped grid target (null if cursor is outside the grid) */
  snapTarget: SnapTarget | null;
  /** Whether this drag started from the unscheduled panel */
  fromUnscheduled: boolean;
  /** Conflict result for the current snap target, or null */
  conflict: ConflictResult | null;
  /** Whether the cursor is currently over the unscheduled drop zone */
  overUnscheduled: boolean;
};

type PendingDrag = {
  presentation: SchedulePresentation;
  startX: number;
  startY: number;
  offsetX: number;
  offsetY: number;
  fromUnscheduled: boolean;
};

type UseScheduleDragConfig = {
  roomsAvailable: number;
  minSlot: number;
  maxSlot: number;
  selectedDay: string;
  conflictContext: ConflictContext;
  gridRef: React.RefObject<HTMLDivElement | null>;
  unscheduledPanelRef?: React.RefObject<HTMLDivElement | null>;
  onDrop: (presentationId: string, room: number, startTime: Date, endTime: Date) => void;
  onDropUnscheduled?: (presentationId: string) => void;
  onClickBlock: (pres: SchedulePresentation) => void;
  onDropBlocked?: (message: string) => void;
};

function viewportToGridPosition(
  clientX: number,
  clientY: number,
  gridElement: HTMLDivElement,
  roomsAvailable: number,
  minSlot: number,
  maxSlot: number,
): { room: number; minuteInDay: number } | null {
  const rect = gridElement.getBoundingClientRect();
  const scrollLeft = gridElement.parentElement?.scrollLeft ?? 0;
  const scrollTop = gridElement.parentElement?.scrollTop ?? 0;

  const x = clientX - rect.left + scrollLeft;
  const y = clientY - rect.top + scrollTop;

  // First row is the header — measure it dynamically
  const firstCell = gridElement.querySelector<HTMLElement>("[style*='grid-row']");
  // Fallback: header is roughly 36px
  const headerHeight = firstCell
    ? firstCell.getBoundingClientRect().top - rect.top + scrollTop
    : 36;

  if (x < TIME_COL_WIDTH || y < headerHeight) return null;

  const roomAreaWidth = rect.width + scrollLeft - TIME_COL_WIDTH;
  const roomWidth = roomAreaWidth / roomsAvailable;
  const room = Math.floor((x - TIME_COL_WIDTH) / roomWidth);
  if (room < 0 || room >= roomsAvailable) return null;

  const slotFloat = (y - headerHeight) / SLOT_HEIGHT;
  const minuteInDay = Math.round(9 * 60 + (slotFloat + minSlot) * 15);
  const minMinute = 9 * 60 + minSlot * 15;
  const maxMinute = 9 * 60 + maxSlot * 15;
  if (minuteInDay < minMinute || minuteInDay >= maxMinute) return null;

  return { room, minuteInDay };
}

function minuteToDate(selectedDay: string, minuteInDay: number): Date {
  const hours = Math.floor(minuteInDay / 60);
  const minutes = minuteInDay % 60;
  const d = new Date(`${selectedDay}T00:00:00Z`);
  d.setUTCHours(hours, minutes, 0, 0);
  return d;
}

export function formatMinuteTime(minuteInDay: number): string {
  const hour24 = Math.floor(minuteInDay / 60);
  const minutes = minuteInDay % 60;
  const suffix = hour24 >= 12 ? "PM" : "AM";
  const hour12 = hour24 % 12 === 0 ? 12 : hour24 % 12;
  return `${hour12}:${minutes.toString().padStart(2, "0")} ${suffix}`;
}

export function useScheduleDrag(config: UseScheduleDragConfig) {
  const [dragState, setDragState] = useState<DragState | null>(null);
  const pendingRef = useRef<PendingDrag | null>(null);
  const dragStateRef = useRef<DragState | null>(null);
  const isDragging = dragState !== null;

  useEffect(() => {
    dragStateRef.current = dragState;
  }, [dragState]);

  // Stable refs for latest values (avoids re-attaching listeners)
  const configRef = useRef(config);
  useEffect(() => {
    configRef.current = config;
  });

  const cancel = useCallback(() => {
    setDragState(null);
    pendingRef.current = null;
    document.body.style.userSelect = "";
  }, []);

  // Pointer move handler — activate drag or update snap target
  useEffect(() => {
    function onPointerMove(e: PointerEvent) {
      const pending = pendingRef.current;

      // Phase 1: pending drag — check threshold
      if (pending && !isDragging) {
        const dx = Math.abs(e.clientX - pending.startX);
        const dy = Math.abs(e.clientY - pending.startY);
        if (dx + dy < DRAG_THRESHOLD) return;

        // Transition to active drag
        document.body.style.userSelect = "none";
        setDragState({
          presentation: pending.presentation,
          offsetX: pending.offsetX,
          offsetY: pending.offsetY,
          currentX: e.clientX,
          currentY: e.clientY,
          snapTarget: null,
          fromUnscheduled: pending.fromUnscheduled,
          conflict: null,
          overUnscheduled: false,
        });
        return;
      }

      // Phase 2: active drag — update position + snap target
      if (!isDragging) return;

      setDragState((prev) => {
        if (!prev) return prev;
        const { roomsAvailable: rooms, minSlot: min, maxSlot: max, selectedDay: day, conflictContext, gridRef: gRef, unscheduledPanelRef: uRef } = configRef.current;
        const grid = gRef.current;
        let snapTarget: SnapTarget | null = null;
        let conflict: ConflictResult | null = null;

        const panel = uRef?.current ?? null;
        let overUnscheduled = false;
        if (panel) {
          const r = panel.getBoundingClientRect();
          overUnscheduled =
            e.clientX >= r.left && e.clientX <= r.right && e.clientY >= r.top && e.clientY <= r.bottom;
        }

        if (grid && !overUnscheduled) {
          const pos = viewportToGridPosition(e.clientX, e.clientY, grid, rooms, min, max);
          if (pos) {
            const startTime = minuteToDate(day, pos.minuteInDay);
            snapTarget = { room: pos.room, minuteInDay: pos.minuteInDay, startTime };
            conflict = detectScheduleConflict(prev.presentation, pos.room, startTime, conflictContext);
          }
        }

        return { ...prev, currentX: e.clientX, currentY: e.clientY, snapTarget, conflict, overUnscheduled };
      });
    }

    function onPointerUp() {
      const pending = pendingRef.current;

      // If we never entered drag mode, treat as click
      if (pending && !isDragging) {
        pendingRef.current = null;
        configRef.current.onClickBlock(pending.presentation);
        return;
      }

      // Active drag — attempt drop. Read state via flushSync-free pattern:
      // capture current dragState before clearing, then run side-effects.
      const prev = dragStateRef.current;
      setDragState(null);
      if (prev?.overUnscheduled) {
        if (!prev.fromUnscheduled) {
          configRef.current.onDropUnscheduled?.(prev.presentation.id);
        }
      } else if (prev?.snapTarget) {
        if (!prev.conflict?.blocked) {
          const endTime = new Date(prev.snapTarget.startTime.getTime() + prev.presentation.minutes * 60 * 1000);
          configRef.current.onDrop(prev.presentation.id, prev.snapTarget.room, prev.snapTarget.startTime, endTime);
        } else if (prev.conflict?.blocked) {
          configRef.current.onDropBlocked?.(prev.conflict.message);
        }
      }

      pendingRef.current = null;
      document.body.style.userSelect = "";
    }

    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") cancel();
    }

    window.addEventListener("pointermove", onPointerMove);
    window.addEventListener("pointerup", onPointerUp);
    window.addEventListener("keydown", onKeyDown);
    return () => {
      window.removeEventListener("pointermove", onPointerMove);
      window.removeEventListener("pointerup", onPointerUp);
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [isDragging, cancel]);

  const handleBlockPointerDown = useCallback(
    (e: React.PointerEvent, pres: SchedulePresentation) => {
      if (e.button !== 0) return; // left click only
      const rect = (e.currentTarget as HTMLElement).getBoundingClientRect();
      pendingRef.current = {
        presentation: pres,
        startX: e.clientX,
        startY: e.clientY,
        offsetX: e.clientX - rect.left,
        offsetY: e.clientY - rect.top,
        fromUnscheduled: false,
      };
    },
    [],
  );

  const handleUnscheduledPointerDown = useCallback(
    (e: React.PointerEvent, pres: SchedulePresentation) => {
      if (e.button !== 0) return;
      const rect = (e.currentTarget as HTMLElement).getBoundingClientRect();
      pendingRef.current = {
        presentation: pres,
        startX: e.clientX,
        startY: e.clientY,
        offsetX: e.clientX - rect.left,
        offsetY: e.clientY - rect.top,
        fromUnscheduled: true,
      };
    },
    [],
  );

  return {
    dragState,
    isDragging,
    handleBlockPointerDown,
    handleUnscheduledPointerDown,
  };
}
