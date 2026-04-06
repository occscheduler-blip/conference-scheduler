import { useCallback, useEffect, useState } from "react";

export function useCalendarGrid(numDays: number, editableSlots?: boolean[][]) {
  const [availability, setAvailability] = useState<boolean[][]>([]);
  const [isDragging, setIsDragging] = useState(false);
  const [dragValue, setDragValue] = useState<boolean | null>(null);

  useEffect(() => {
    const stopDragging = () => {
      setIsDragging(false);
      setDragValue(null);
    };
    window.addEventListener("mouseup", stopDragging);
    return () => window.removeEventListener("mouseup", stopDragging);
  }, []);

  const setCell = useCallback(
    (dayIndex: number, slotIndex: number, value: boolean) => {
      setAvailability((current) =>
        current.map((daySlots, dIdx) =>
          dIdx === dayIndex
            ? daySlots.map((slot, sIdx) => (sIdx === slotIndex ? value : slot))
            : daySlots
        )
      );
    },
    []
  );

  const handleCellMouseDown = useCallback(
    (dayIndex: number, slotIndex: number) => {
      if (editableSlots && !editableSlots[dayIndex]?.[slotIndex]) return;
      const nextValue = !(availability[dayIndex]?.[slotIndex] ?? false);
      setCell(dayIndex, slotIndex, nextValue);
      setDragValue(nextValue);
      setIsDragging(true);
    },
    [availability, editableSlots, setCell]
  );

  const handleCellMouseEnter = useCallback(
    (dayIndex: number, slotIndex: number) => {
      if (!isDragging || dragValue === null) return;
      if (editableSlots && !editableSlots[dayIndex]?.[slotIndex]) return;
      setCell(dayIndex, slotIndex, dragValue);
    },
    [isDragging, dragValue, editableSlots, setCell]
  );

  return {
    availability,
    setAvailability,
    handleCellMouseDown,
    handleCellMouseEnter,
  };
}
