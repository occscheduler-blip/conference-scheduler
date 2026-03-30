"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import type {
  AdminTab,
  DepartmentAction,
  DepartmentRecord,
  SymposiumOption,
  TimeframeRecord,
} from "./types";

const fieldClass =
  "w-full rounded-lg border-2 border-[#2f53c4] bg-white px-3 py-2.5 text-base text-black shadow-sm outline-none transition focus:border-[#1237af] focus:ring-2 focus:ring-[#c7d4ff] placeholder:text-[#6b6b6b]";

const totalSlots = 32; // 9:00 AM to 5:00 PM in 15-minute increments
const weekDays = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

function formatTimeLabel(slotIndex: number) {
  const totalMinutes = 9 * 60 + slotIndex * 15;
  const hour24 = Math.floor(totalMinutes / 60);
  const minutes = totalMinutes % 60;
  const suffix = hour24 >= 12 ? "PM" : "AM";
  const hour12 = hour24 % 12 === 0 ? 12 : hour24 % 12;
  const minutePart = minutes.toString().padStart(2, "0");
  return `${hour12}:${minutePart} ${suffix}`;
}

function localDateString(date: Date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function formatCalendarDate(date: Date) {
  return date.toLocaleDateString(undefined, {
    weekday: "short",
    month: "short",
    day: "numeric",
  });
}

function parseBackendDateTime(value: string) {
  const hasExplicitTimezone = /(?:Z|[+\-]\d{2}:\d{2})$/i.test(value);
  // Treat timezone-less backend timestamps as UTC to prevent local timezone drift when reloading/editing.
  return new Date(hasExplicitTimezone ? value : `${value}Z`);
}

function toMessage(detail: unknown, fallback: string): string {
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

// AI template: converts between the availability calendar grid and backend timeframe records.
function buildCalendarDates(startDate: string, endDate: string) {
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

function buildTimeframesFromGrid(dates: Date[], availability: boolean[][]) {
  if (dates.length === 0) return null;
  const tuples: [string, string][] = [];

  for (let dayIndex = 0; dayIndex < dates.length; dayIndex += 1) {
    for (let slotIndex = 0; slotIndex < totalSlots; slotIndex += 1) {
      if (!availability[dayIndex]?.[slotIndex]) continue;

      const start = new Date(dates[dayIndex]);
      const startMinutes = 9 * 60 + slotIndex * 15;
      start.setHours(Math.floor(startMinutes / 60), startMinutes % 60, 0, 0);

      const end = new Date(start);
      end.setMinutes(end.getMinutes() + 15);
      tuples.push([start.toISOString(), end.toISOString()]);
    }
  }

  return tuples;
}

function gridFromTimeframes(timeframes: TimeframeRecord[]) {
  if (timeframes.length === 0) return { startDate: "", endDate: "", availability: [] as boolean[][] };

  const dayKeys = timeframes
    .map((tf) => localDateString(parseBackendDateTime(tf.start_time)))
    .sort((a, b) => (a < b ? -1 : a > b ? 1 : 0));
  const startDate = dayKeys[0];
  const endDate = dayKeys[dayKeys.length - 1];
  const dates = buildCalendarDates(startDate, endDate);

  const dayIndexByKey = new Map<string, number>();
  dates.forEach((date, index) => dayIndexByKey.set(localDateString(date), index));

  const availability = Array.from({ length: dates.length }, () => Array.from({ length: totalSlots }, () => false));

  for (const timeframe of timeframes) {
    const start = parseBackendDateTime(timeframe.start_time);
    const dayIndex = dayIndexByKey.get(localDateString(start));
    if (dayIndex === undefined) continue;

    const minutesFromStart = start.getHours() * 60 + start.getMinutes() - 9 * 60;
    if (minutesFromStart < 0) continue;
    const slotIndex = Math.floor(minutesFromStart / 15);
    if (slotIndex >= 0 && slotIndex < totalSlots) availability[dayIndex][slotIndex] = true;
  }

  return { startDate, endDate, availability };
}

export default function AdminPage() {
  const [activeTab, setActiveTab] = useState<AdminTab>("create");
  const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:8000";

  // Create event state
  const [createSymposiumName, setCreateSymposiumName] = useState("");
  const [createRooms, setCreateRooms] = useState("");
  const [createStartDate, setCreateStartDate] = useState("");
  const [createEndDate, setCreateEndDate] = useState("");
  const [createAvailability, setCreateAvailability] = useState<boolean[][]>([]);
  const [isCreateDragging, setIsCreateDragging] = useState(false);
  const [createDragValue, setCreateDragValue] = useState<boolean | null>(null);
  const [isSavingCreate, setIsSavingCreate] = useState(false);
  const [createSaveMessage, setCreateSaveMessage] = useState<string | null>(null);

  // Edit event selection + details
  const [selectedSymposiumId, setSelectedSymposiumId] = useState("");
  const [symposiumOptions, setSymposiumOptions] = useState<SymposiumOption[]>([]);
  const [isLoadingSymposia, setIsLoadingSymposia] = useState(false);
  const [symposiumLoadError, setSymposiumLoadError] = useState<string | null>(null);

  const [editSymposiumName, setEditSymposiumName] = useState("");
  const [editRooms, setEditRooms] = useState("");
  const [editStartDate, setEditStartDate] = useState("");
  const [editEndDate, setEditEndDate] = useState("");
  const [editAvailability, setEditAvailability] = useState<boolean[][]>([]);
  const [isEditDragging, setIsEditDragging] = useState(false);
  const [editDragValue, setEditDragValue] = useState<boolean | null>(null);
  const [isLoadingSymposiumDetails, setIsLoadingSymposiumDetails] = useState(false);
  const [isSavingSymposiumEdit, setIsSavingSymposiumEdit] = useState(false);
  const [isDeletingSymposium, setIsDeletingSymposium] = useState(false);
  const [symposiumEditMessage, setSymposiumEditMessage] = useState<string | null>(null);

  // Departments in edit tab
  const [departments, setDepartments] = useState<DepartmentRecord[]>([]);
  const [isLoadingDepartments, setIsLoadingDepartments] = useState(false);
  const [departmentLoadError, setDepartmentLoadError] = useState<string | null>(null);

  const [departmentAction, setDepartmentAction] = useState<DepartmentAction>("add");
  const [departmentToEditId, setDepartmentToEditId] = useState("");
  const [departmentName, setDepartmentName] = useState("");
  const [departmentHeadName, setDepartmentHeadName] = useState("");
  const [departmentHeadEmail, setDepartmentHeadEmail] = useState("");
  const [isSavingDepartment, setIsSavingDepartment] = useState(false);
  const [deletingDepartmentId, setDeletingDepartmentId] = useState("");
  const [departmentMessage, setDepartmentMessage] = useState<string | null>(null);
  const [departmentMessageKind, setDepartmentMessageKind] = useState<"success" | "error" | null>(null);
  const [deployEventMessage, setDeployEventMessage] = useState<string | null>(null);

  const isCreateTab = activeTab === "create";
  const hasSelectedSymposium = Boolean(selectedSymposiumId.trim());
  const backendApiKey = process.env.NEXT_PUBLIC_BACKEND_API_KEY ?? "";
  const authHeaders = useMemo(
    () => (backendApiKey ? { "X-API-Key": backendApiKey } : undefined),
    [backendApiKey]
  );

  const createCalendarDates = useMemo(
    () => buildCalendarDates(createStartDate, createEndDate),
    [createStartDate, createEndDate]
  );
  const editCalendarDates = useMemo(() => buildCalendarDates(editStartDate, editEndDate), [editStartDate, editEndDate]);

  const fetchSymposia = useCallback(async () => {
    setIsLoadingSymposia(true);
    setSymposiumLoadError(null);
    try {
      const response = await fetch(`${backendUrl}/api/events/symposiums`, { headers: authHeaders });
      const payload = (await response.json().catch(() => ({}))) as {
        detail?: string;
        symposia?: SymposiumOption[];
        symposiums?: SymposiumOption[];
        data?: SymposiumOption[];
      };
      if (!response.ok) {
        setSymposiumLoadError(payload.detail ?? "Failed to load symposia.");
        return;
      }
      setSymposiumOptions(payload.symposiums ?? []);
    } catch (error) {
      const message = error instanceof Error ? error.message : "Unknown error";
      setSymposiumLoadError(`Load failed: ${message}`);
    } finally {
      setIsLoadingSymposia(false);
    }
  }, [authHeaders, backendUrl]);

  const fetchDepartments = useCallback(
    async (symposiumId: string) => {
      if (!symposiumId.trim()) {
        setDepartments([]);
        setDepartmentToEditId("");
        setDepartmentLoadError(null);
        return;
      }

      setIsLoadingDepartments(true);
      setDepartmentLoadError(null);
      try {
        const response = await fetch(`${backendUrl}/api/events/departments?symposium_id=${encodeURIComponent(symposiumId)}`, {
          headers: authHeaders,
        });
        const payload = (await response.json()) as { detail?: string; departments?: DepartmentRecord[] };
        if (!response.ok) {
          setDepartmentLoadError(payload.detail ?? "Failed to load departments.");
          setDepartments([]);
          return;
        }
        const loaded = payload.departments ?? [];
        setDepartments(loaded);
        setDepartmentToEditId((current) =>
          loaded.some((department) => department.id === current) ? current : loaded[0]?.id ?? ""
        );
      } catch (error) {
        const message = error instanceof Error ? error.message : "Unknown error";
        setDepartmentLoadError(`Load failed: ${message}`);
        setDepartments([]);
      } finally {
        setIsLoadingDepartments(false);
      }
    },
    [authHeaders, backendUrl]
  );

  const fetchSymposiumDetails = useCallback(
    async (symposiumId: string) => {
      if (!symposiumId.trim()) {
        setEditSymposiumName("");
        setEditRooms("");
        setEditStartDate("");
        setEditEndDate("");
        setEditAvailability([]);
        return;
      }

      setIsLoadingSymposiumDetails(true);
      setSymposiumEditMessage(null);
      try {
        const response = await fetch(`${backendUrl}/api/events/symposiums/${symposiumId}`, { headers: authHeaders });
        const payload = (await response.json()) as {
          detail?: string;
          symposium?: { id: string; name: string; rooms_available: number };
          timeframes?: TimeframeRecord[];
        };
        if (!response.ok || !payload.symposium) {
          setSymposiumEditMessage(payload.detail ?? "Failed to load selected symposium.");
          return;
        }

        setEditSymposiumName(payload.symposium.name ?? "");
        setEditRooms(String(payload.symposium.rooms_available ?? ""));

        const grid = gridFromTimeframes(payload.timeframes ?? []);
        setEditStartDate(grid.startDate);
        setEditEndDate(grid.endDate);
        setEditAvailability(grid.availability);
      } catch (error) {
        const message = error instanceof Error ? error.message : "Unknown error";
        setSymposiumEditMessage(`Load failed: ${message}`);
      } finally {
        setIsLoadingSymposiumDetails(false);
      }
    },
    [authHeaders, backendUrl]
  );

  useEffect(() => {
    void fetchSymposia();
  }, [fetchSymposia]);

  useEffect(() => {
    if (createCalendarDates.length === 0) {
      setCreateAvailability([]);
      return;
    }
    setCreateAvailability((current) =>
      Array.from({ length: createCalendarDates.length }, (_, dayIndex) =>
        Array.from({ length: totalSlots }, (_, slotIndex) => current[dayIndex]?.[slotIndex] ?? false)
      )
    );
  }, [createCalendarDates]);

  useEffect(() => {
    if (editCalendarDates.length === 0) {
      setEditAvailability([]);
      return;
    }
    setEditAvailability((current) =>
      Array.from({ length: editCalendarDates.length }, (_, dayIndex) =>
        Array.from({ length: totalSlots }, (_, slotIndex) => current[dayIndex]?.[slotIndex] ?? false)
      )
    );
  }, [editCalendarDates]);

  useEffect(() => {
    const stopDragging = () => {
      setIsCreateDragging(false);
      setCreateDragValue(null);
      setIsEditDragging(false);
      setEditDragValue(null);
    };

    window.addEventListener("mouseup", stopDragging);
    return () => window.removeEventListener("mouseup", stopDragging);
  }, []);

  useEffect(() => {
    setDepartmentMessage(null);
    setDepartmentMessageKind(null);
    setDepartmentName("");
    setDepartmentHeadName("");
    setDepartmentHeadEmail("");
    setDepartmentToEditId("");
    setDepartmentAction("add");
    void fetchDepartments(selectedSymposiumId);
    void fetchSymposiumDetails(selectedSymposiumId);
  }, [fetchDepartments, fetchSymposiumDetails, selectedSymposiumId]);

  useEffect(() => {
    if (departmentAction !== "edit") return;

    if (!departmentToEditId) {
      setDepartmentName("");
      setDepartmentHeadName("");
      setDepartmentHeadEmail("");
      return;
    }

    const selectedDepartment = departments.find((department) => department.id === departmentToEditId);
    if (!selectedDepartment) return;

    setDepartmentName(selectedDepartment.department_name);
    setDepartmentHeadName(selectedDepartment.department_head_name);
    setDepartmentHeadEmail(selectedDepartment.email);
  }, [departmentAction, departmentToEditId, departments]);

  const setCreateCell = (dayIndex: number, slotIndex: number, value: boolean) => {
    setCreateAvailability((current) =>
      current.map((daySlots, dIdx) =>
        dIdx === dayIndex ? daySlots.map((slot, sIdx) => (sIdx === slotIndex ? value : slot)) : daySlots
      )
    );
  };

  const setEditCell = (dayIndex: number, slotIndex: number, value: boolean) => {
    setEditAvailability((current) =>
      current.map((daySlots, dIdx) =>
        dIdx === dayIndex ? daySlots.map((slot, sIdx) => (sIdx === slotIndex ? value : slot)) : daySlots
      )
    );
  };

  // AI template: creates or updates a symposium with a full set of timeframes derived from the grid.
  const handleCreateEventSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setCreateSaveMessage(null);

    const trimmedName = createSymposiumName.trim();
    if (!trimmedName) {
      setCreateSaveMessage("Enter a symposium name.");
      return;
    }

    const parsedRooms = Number.parseInt(createRooms, 10);
    if (!Number.isFinite(parsedRooms) || parsedRooms <= 0) {
      setCreateSaveMessage("Enter a valid number of rooms.");
      return;
    }

    const timeframes = buildTimeframesFromGrid(createCalendarDates, createAvailability);
    if (!timeframes || timeframes.length === 0) {
      setCreateSaveMessage("Select at least one available time slot.");
      return;
    }

    setIsSavingCreate(true);
    try {
      const response = await fetch(`${backendUrl}/api/events/add_symposium`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...(authHeaders ?? {}) },
        body: JSON.stringify({
          symposium_name: trimmedName,
          rooms_available: parsedRooms,
          timeframes: timeframes.map(([start_time, end_time]) => ({ start_time, end_time })),
        }),
      });

      const payload = (await response.json()) as { detail?: string; status?: string; symposium_id?: string };
      if (!response.ok) {
        setCreateSaveMessage(payload.detail ?? "Failed to save symposium.");
        return;
      }

      setCreateSaveMessage("Event created successfully.");
      await fetchSymposia();
      if (payload.symposium_id) setSelectedSymposiumId(payload.symposium_id);
      setActiveTab("edit");
    } catch (error) {
      const message = error instanceof Error ? error.message : "Unknown error";
      setCreateSaveMessage(`Save failed: ${message}`);
    } finally {
      setIsSavingCreate(false);
    }
  };

  const handleSaveEditedEvent = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setSymposiumEditMessage(null);

    if (!selectedSymposiumId) {
      setSymposiumEditMessage("Select an event first.");
      return;
    }

    const trimmedName = editSymposiumName.trim();
    if (!trimmedName) {
      setSymposiumEditMessage("Enter a symposium name.");
      return;
    }

    const parsedRooms = Number.parseInt(editRooms, 10);
    if (!Number.isFinite(parsedRooms) || parsedRooms <= 0) {
      setSymposiumEditMessage("Enter a valid number of rooms.");
      return;
    }

    const timeframes = buildTimeframesFromGrid(editCalendarDates, editAvailability);
    if (!timeframes || timeframes.length === 0) {
      setSymposiumEditMessage("Select at least one available time slot.");
      return;
    }

    setIsSavingSymposiumEdit(true);
    try {
      const response = await fetch(`${backendUrl}/api/events/symposiums/${selectedSymposiumId}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json", ...(authHeaders ?? {}) },
        body: JSON.stringify({
          symposium_name: trimmedName,
          rooms_available: parsedRooms,
          timeframes: timeframes.map(([start_time, end_time]) => ({ start_time, end_time })),
        }),
      });

      const payload = (await response.json()) as { detail?: string; status?: string };
      if (!response.ok) {
        setSymposiumEditMessage(payload.detail ?? "Failed to update event.");
        return;
      }

      setSymposiumEditMessage("Event updated successfully.");
      await fetchSymposia();
    } catch (error) {
      const message = error instanceof Error ? error.message : "Unknown error";
      setSymposiumEditMessage(`Update failed: ${message}`);
    } finally {
      setIsSavingSymposiumEdit(false);
    }
  };

  const handleDeleteEvent = async () => {
    if (!selectedSymposiumId) return;
    const selectedEvent = symposiumOptions.find((option) => option.id === selectedSymposiumId);
    if (!window.confirm(`Delete event "${selectedEvent?.name ?? selectedSymposiumId}"?`)) return;

    setIsDeletingSymposium(true);
    setSymposiumEditMessage(null);
    try {
      const response = await fetch(
        `${backendUrl}/api/events/delete_symposium?symposium_id=${encodeURIComponent(selectedSymposiumId)}`,
        {
        method: "DELETE",
        headers: authHeaders,
        }
      );
      const payload = (await response.json()) as { detail?: string; status?: string };
      if (!response.ok) {
        setSymposiumEditMessage(payload.detail ?? "Failed to delete event.");
        return;
      }

      setSymposiumEditMessage("Event deleted.");
      setSelectedSymposiumId("");
      await fetchSymposia();
    } catch (error) {
      const message = error instanceof Error ? error.message : "Unknown error";
      setSymposiumEditMessage(`Delete failed: ${message}`);
    } finally {
      setIsDeletingSymposium(false);
    }
  };

  const isHamiltonEmail = (value: string) => /^[^\s@]+@hamilton\.edu$/i.test(value.trim());

  const handleDepartmentSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setDepartmentMessage(null);
    setDepartmentMessageKind(null);

    if (!selectedSymposiumId) {
      setDepartmentMessage("Select an event first.");
      setDepartmentMessageKind("error");
      return;
    }

    if (departmentAction === "add" || departmentAction === "edit") {
      if (departmentAction === "edit" && !departmentToEditId) {
        setDepartmentMessage("Select a department to edit.");
        setDepartmentMessageKind("error");
        return;
      }
      if (!departmentName.trim()) {
        setDepartmentMessage("Enter a department name.");
        setDepartmentMessageKind("error");
        return;
      }
      if (!departmentHeadName.trim()) {
        setDepartmentMessage("Enter a department head name.");
        setDepartmentMessageKind("error");
        return;
      }
      if (!departmentHeadEmail.trim() || !isHamiltonEmail(departmentHeadEmail)) {
        setDepartmentMessage("Use a valid @hamilton.edu email.");
        setDepartmentMessageKind("error");
        return;
      }
    }

    setIsSavingDepartment(true);
    try {
      if (departmentAction === "add") {
        const response = await fetch(`${backendUrl}/api/events/add_department`, {
          method: "POST",
          headers: { "Content-Type": "application/json", ...(authHeaders ?? {}) },
          body: JSON.stringify({
            symposium_id: selectedSymposiumId,
            department_name: departmentName.trim(),
            department_head_name: departmentHeadName.trim(),
            email: departmentHeadEmail.trim().toLowerCase(),
          }),
        });

        const payload = (await response.json()) as { detail?: unknown; status?: string };
        if (!response.ok) {
          setDepartmentMessage(toMessage(payload.detail, "Failed to add department."));
          setDepartmentMessageKind("error");
          return;
        }

        setDepartmentName("");
        setDepartmentHeadName("");
        setDepartmentHeadEmail("");
        setDepartmentMessage("Department added.");
        setDepartmentMessageKind("success");
      } else if (departmentAction === "edit") {
        const response = await fetch(`${backendUrl}/api/events/update_department`, {
          method: "PUT",
          headers: { "Content-Type": "application/json", ...(authHeaders ?? {}) },
          body: JSON.stringify({
            department_id: departmentToEditId,
            department_name: departmentName.trim(),
            department_head_name: departmentHeadName.trim(),
            email: departmentHeadEmail.trim().toLowerCase(),
          }),
        });

        const payload = (await response.json()) as { detail?: unknown; status?: string };
        if (!response.ok) {
          setDepartmentMessage(toMessage(payload.detail, "Failed to update department."));
          setDepartmentMessageKind("error");
          return;
        }

        setDepartmentMessage("Department updated.");
        setDepartmentMessageKind("success");
        setDepartmentAction("add");
        setDepartmentToEditId("");
        setDepartmentName("");
        setDepartmentHeadName("");
        setDepartmentHeadEmail("");
      }

      await fetchDepartments(selectedSymposiumId);
    } catch (error) {
      const message = error instanceof Error ? error.message : "Unknown error";
      setDepartmentMessage(`Request failed: ${message}`);
      setDepartmentMessageKind("error");
    } finally {
      setIsSavingDepartment(false);
    }
  };

  const handleDeleteDepartment = async (department: DepartmentRecord) => {
    const confirmed = window.confirm(`Delete department "${department.department_name}"?`);
    if (!confirmed) return;

    setDeletingDepartmentId(department.id);
    setDepartmentMessage(null);
    setDepartmentMessageKind(null);
    try {
      const response = await fetch(
        `${backendUrl}/api/events/delete_department?department_id=${encodeURIComponent(department.id)}`,
        {
          method: "DELETE",
          headers: authHeaders,
        }
      );
      const payload = (await response.json()) as { detail?: unknown; status?: string };
      if (!response.ok) {
        setDepartmentMessage(toMessage(payload.detail, "Failed to delete department."));
        setDepartmentMessageKind("error");
        return;
      }

      setDepartmentMessage("Department deleted.");
      setDepartmentMessageKind("success");
      await fetchDepartments(selectedSymposiumId);
    } catch (error) {
      const message = error instanceof Error ? error.message : "Unknown error";
      setDepartmentMessage(`Request failed: ${message}`);
      setDepartmentMessageKind("error");
    } finally {
      setDeletingDepartmentId("");
    }
  };

  const handleStartEditDepartment = (department: DepartmentRecord) => {
    setDepartmentAction("edit");
    setDepartmentToEditId(department.id);
    setDepartmentName(department.department_name);
    setDepartmentHeadName(department.department_head_name);
    setDepartmentHeadEmail(department.email);
    setDepartmentMessage(null);
    setDepartmentMessageKind(null);
  };

  const handleDeployEvent = () => {
    setDeployEventMessage(null);
    if (!selectedSymposiumId) {
      setDeployEventMessage("Select an event first.");
      return;
    }
    if (departments.length === 0) {
      setDeployEventMessage("Add at least one department before deploying.");
      return;
    }
    setDeployEventMessage("Deploy Event is not connected yet.");
  };

  const resetCreateTabState = () => {
    setCreateSymposiumName("");
    setCreateRooms("");
    setCreateStartDate("");
    setCreateEndDate("");
    setCreateAvailability([]);
    setIsCreateDragging(false);
    setCreateDragValue(null);
    setIsSavingCreate(false);
    setCreateSaveMessage(null);
  };

  const resetEditTabState = () => {
    setSelectedSymposiumId("");
    setEditSymposiumName("");
    setEditRooms("");
    setEditStartDate("");
    setEditEndDate("");
    setEditAvailability([]);
    setIsEditDragging(false);
    setEditDragValue(null);
    setIsLoadingSymposiumDetails(false);
    setIsSavingSymposiumEdit(false);
    setIsDeletingSymposium(false);
    setSymposiumEditMessage(null);
    setDepartments([]);
    setDepartmentLoadError(null);
    setDepartmentAction("add");
    setDepartmentToEditId("");
    setDepartmentName("");
    setDepartmentHeadName("");
    setDepartmentHeadEmail("");
    setIsSavingDepartment(false);
    setDeletingDepartmentId("");
    setDepartmentMessage(null);
    setDepartmentMessageKind(null);
    setDeployEventMessage(null);
  };

  const handleTabSwitch = (tab: AdminTab) => {
    setActiveTab(tab);
    if (tab === "create") {
      resetCreateTabState();
      return;
    }
    resetEditTabState();
    void fetchSymposia();
  };

  return (
    <main className="min-h-screen bg-[linear-gradient(180deg,#f7f9ff_0%,#f4f4f4_55%,#f1f1f1_100%)] px-4 py-8">
      <div className="mx-auto w-full max-w-6xl">
        <div className="mb-3 flex justify-end">
          <Link
            href="/pages?view=home"
            className="rounded-md border border-[#9ca3af] bg-[#e5e7eb] px-4 py-1.5 text-sm font-semibold text-[#1f2937] transition hover:border-[#0f33a8] hover:bg-[#0f33a8] hover:text-white"
          >
            Home
          </Link>
        </div>
        <header className="mb-5 rounded-2xl border border-[#d8e2ff] bg-white/90 px-5 py-5 shadow-[0_10px_30px_rgba(20,44,120,0.08)] backdrop-blur">
          <h1 className="text-center text-2xl font-extrabold tracking-wide text-black md:text-4xl">
            OCC THESIS SYMPOSIUM - ADMIN
          </h1>
        </header>

        <nav className="mb-4 grid grid-cols-1 gap-3 md:grid-cols-2">
          <button
            type="button"
            onClick={() => handleTabSwitch("create")}
            className={`rounded-xl border-2 px-4 py-3 text-lg font-semibold transition md:text-xl ${
              isCreateTab
                ? "border-[#0f33a8] bg-[#0f33a8] text-white shadow-[0_8px_20px_rgba(15,51,168,0.25)]"
                : "border-[#c6d2f6] bg-white text-[#111] hover:border-[#0f33a8]"
            }`}
          >
            Create New Event
          </button>
          <button
            type="button"
            onClick={() => handleTabSwitch("edit")}
            className={`rounded-xl border-2 px-4 py-3 text-lg font-semibold transition md:text-xl ${
              isCreateTab
                ? "border-[#c6d2f6] bg-white text-[#111] hover:border-[#0f33a8]"
                : "border-[#0f33a8] bg-[#0f33a8] text-white shadow-[0_8px_20px_rgba(15,51,168,0.25)]"
            }`}
          >
            Edit Existing Event
          </button>
        </nav>

        {isCreateTab ? (
          <section className="rounded-2xl border border-[#d7bf92] bg-white p-4 shadow-[0_16px_30px_rgba(80,60,20,0.08)] md:p-6">
            <h2 className="mb-5 text-xl font-bold text-[#111] md:text-2xl">Create New Event</h2>

            <form onSubmit={handleCreateEventSubmit} className="grid grid-cols-1 gap-4 lg:grid-cols-[1.8fr_1fr]">
              <div className="rounded-xl border border-[#e6ecff] bg-[#fdfdff] p-4 md:p-5">
                <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                  <label className="flex flex-col gap-1.5 md:col-span-2">
                    <span className="text-xs font-bold uppercase tracking-wide text-[#2d3d7a] md:text-sm">Symposium Name</span>
                    <input
                      className={fieldClass}
                      placeholder="Ex. OCC Thesis Symposium 2026"
                      value={createSymposiumName}
                      onChange={(event) => setCreateSymposiumName(event.target.value)}
                    />
                  </label>
                  <label className="flex flex-col gap-1.5">
                    <span className="text-xs font-bold uppercase tracking-wide text-[#2d3d7a] md:text-sm">Rooms Available</span>
                    <input
                      type="number"
                      min={1}
                      className={fieldClass}
                      placeholder="Ex. 5"
                      value={createRooms}
                      onChange={(event) => setCreateRooms(event.target.value)}
                    />
                  </label>
                </div>

                <div className="mt-5 grid grid-cols-1 gap-4">
                  <label className="flex flex-col gap-1.5">
                    <span className="text-xs font-bold uppercase tracking-wide text-[#2d3d7a] md:text-sm">Start Date</span>
                    <input
                      type="date"
                      className={fieldClass}
                      value={createStartDate}
                      onChange={(event) => setCreateStartDate(event.target.value)}
                    />
                  </label>
                  <label className="flex flex-col gap-1.5">
                    <span className="text-xs font-bold uppercase tracking-wide text-[#2d3d7a] md:text-sm">End Date</span>
                    <input
                      type="date"
                      className={fieldClass}
                      value={createEndDate}
                      onChange={(event) => setCreateEndDate(event.target.value)}
                    />
                  </label>
                </div>
              </div>

              <aside className="rounded-xl border border-[#d7bf92] bg-[#fffdf8] p-4 md:p-5">
                <p className="mb-3 text-sm font-semibold text-[#444] md:text-base">Click and drag to toggle availability.</p>
                <div className="w-full overflow-x-auto rounded-xl border border-[#cfcfcf] bg-white p-2">
                  {createCalendarDates.length === 0 ? (
                    <div className="px-2 py-4 text-sm font-semibold text-[#555]">Select start and end dates first.</div>
                  ) : (
                    <div className="min-w-[760px] select-none">
                      <div
                        className="grid text-center text-base font-bold text-[#222]"
                        style={{ gridTemplateColumns: `64px repeat(${createCalendarDates.length}, minmax(80px, 1fr))` }}
                      >
                        <div />
                        {createCalendarDates.map((date) => (
                          <div key={date.toISOString()} className="border-b border-[#777] pb-1">
                            {formatCalendarDate(date)}
                          </div>
                        ))}
                      </div>
                      <div
                        className="grid"
                        style={{ gridTemplateColumns: `64px repeat(${createCalendarDates.length}, minmax(80px, 1fr))` }}
                      >
                        {Array.from({ length: totalSlots }, (_, slotIndex) => (
                          <div key={slotIndex} className="contents">
                            <div className="pr-1 pt-0.5 text-right text-[11px] font-semibold text-[#444]">
                              {slotIndex % 4 === 0 ? formatTimeLabel(slotIndex) : ""}
                            </div>
                            {createCalendarDates.map((date, dayIndex) => {
                              const available = createAvailability[dayIndex]?.[slotIndex] ?? false;
                              const showHourLine = slotIndex % 4 === 0;
                              return (
                                <button
                                  key={`${date.toISOString()}-${slotIndex}`}
                                  type="button"
                                  onMouseDown={() => {
                                    const nextValue = !available;
                                    setCreateCell(dayIndex, slotIndex, nextValue);
                                    setCreateDragValue(nextValue);
                                    setIsCreateDragging(true);
                                  }}
                                  onMouseEnter={() => {
                                    if (!isCreateDragging || createDragValue === null) return;
                                    setCreateCell(dayIndex, slotIndex, createDragValue);
                                  }}
                                  onDragStart={(event) => event.preventDefault()}
                                  className={`h-4 border-r border-l border-b border-[#333] ${
                                    showHourLine ? "border-t border-t-[#333]" : ""
                                  } ${available ? "bg-[#38a000]" : "bg-[#f0d7d9]"}`}
                                  aria-label={`${formatCalendarDate(date)} ${formatTimeLabel(slotIndex)}`}
                                />
                              );
                            })}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              </aside>

              <div className="lg:col-span-2">
                <button
                  type="submit"
                  disabled={isSavingCreate}
                  className="rounded-lg bg-[#0f33a8] px-5 py-2.5 text-sm font-semibold text-white shadow-[0_8px_18px_rgba(15,51,168,0.25)] transition hover:bg-[#0b2a8d] disabled:cursor-not-allowed disabled:opacity-60 md:text-base"
                >
                  {isSavingCreate ? "Saving..." : "Save Event"}
                </button>
                {createSaveMessage ? <p className="mt-2 text-sm font-semibold text-[#222]">{createSaveMessage}</p> : null}
              </div>
            </form>
          </section>
        ) : (
          <section className="rounded-2xl border border-[#d7bf92] bg-white p-4 shadow-[0_16px_30px_rgba(80,60,20,0.08)] md:p-6">
            <h2 className="mb-4 text-xl font-bold text-[#111] md:text-2xl">Edit Existing Event</h2>

            <div className="max-w-3xl space-y-3 rounded-xl border border-[#e6ecff] bg-[#fdfdff] p-4 md:p-5">
              <label className="flex flex-col gap-1.5">
                <span className="text-xs font-bold uppercase tracking-wide text-[#2d3d7a] md:text-sm">Select Symposium</span>
                <select
                  className={fieldClass}
                  value={selectedSymposiumId}
                  onChange={(event) => setSelectedSymposiumId(event.target.value)}
                  disabled={isLoadingSymposia}
                >
                  <option value="">Select an event...</option>
                  {symposiumOptions.map((option) => (
                    <option key={option.id} value={option.id}>
                      {option.name}
                    </option>
                  ))}
                </select>
              </label>

              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={() => void fetchSymposia()}
                  disabled={isLoadingSymposia}
                  className="rounded-lg bg-[#0f33a8] px-4 py-2 text-sm font-semibold text-white transition hover:bg-[#0b2a8d] disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {isLoadingSymposia ? "Loading..." : "Refresh Symposium List"}
                </button>
                <button
                  type="button"
                  onClick={() => void handleDeleteEvent()}
                  disabled={!hasSelectedSymposium || isDeletingSymposium}
                  className="rounded-lg border border-[#b00020] bg-white px-4 py-2 text-sm font-semibold text-[#b00020] transition hover:bg-[#fff5f6] disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {isDeletingSymposium ? "Deleting..." : "Delete This Event"}
                </button>
              </div>

              <div className="rounded-lg border border-[#e0e0e0] bg-[#f9f9f9] p-3 text-sm text-[#333]">
                {symposiumLoadError
                  ? symposiumLoadError
                  : hasSelectedSymposium
                    ? "Selected event loaded below."
                    : `Loaded ${symposiumOptions.length} event${symposiumOptions.length === 1 ? "" : "s"} from the database.`}
              </div>
            </div>

            {hasSelectedSymposium ? (
              <>
                <form onSubmit={handleSaveEditedEvent} className="mt-5 grid grid-cols-1 gap-4 lg:grid-cols-[1.8fr_1fr]">
                  <div className="rounded-xl border border-[#e6ecff] bg-[#fdfdff] p-4 md:p-5">
                    <h3 className="mb-3 text-lg font-bold text-[#111]">Edit Event Details</h3>
                    <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                      <label className="flex flex-col gap-1.5 md:col-span-2">
                        <span className="text-xs font-bold uppercase tracking-wide text-[#2d3d7a] md:text-sm">Symposium Name</span>
                        <input
                          className={fieldClass}
                          value={editSymposiumName}
                          onChange={(event) => setEditSymposiumName(event.target.value)}
                          disabled={isLoadingSymposiumDetails}
                        />
                      </label>
                      <label className="flex flex-col gap-1.5">
                        <span className="text-xs font-bold uppercase tracking-wide text-[#2d3d7a] md:text-sm">Rooms Available</span>
                        <input
                          type="number"
                          min={1}
                          className={fieldClass}
                          value={editRooms}
                          onChange={(event) => setEditRooms(event.target.value)}
                          disabled={isLoadingSymposiumDetails}
                        />
                      </label>
                    </div>

                    <div className="mt-5 grid grid-cols-1 gap-4">
                      <label className="flex flex-col gap-1.5">
                        <span className="text-xs font-bold uppercase tracking-wide text-[#2d3d7a] md:text-sm">Start Date</span>
                        <input
                          type="date"
                          className={fieldClass}
                          value={editStartDate}
                          onChange={(event) => setEditStartDate(event.target.value)}
                        />
                      </label>
                      <label className="flex flex-col gap-1.5">
                        <span className="text-xs font-bold uppercase tracking-wide text-[#2d3d7a] md:text-sm">End Date</span>
                        <input
                          type="date"
                          className={fieldClass}
                          value={editEndDate}
                          onChange={(event) => setEditEndDate(event.target.value)}
                        />
                      </label>
                    </div>
                  </div>

                  <aside className="rounded-xl border border-[#d7bf92] bg-[#fffdf8] p-4 md:p-5">
                    <p className="mb-3 text-sm font-semibold text-[#444]">Click and drag to edit event availability.</p>
                    <div className="w-full overflow-x-auto rounded-xl border border-[#cfcfcf] bg-white p-2">
                      {editCalendarDates.length === 0 ? (
                        <div className="px-2 py-4 text-sm font-semibold text-[#555]">Select start and end dates first.</div>
                      ) : (
                        <div className="min-w-[760px] select-none">
                          <div
                            className="grid text-center text-base font-bold text-[#222]"
                            style={{ gridTemplateColumns: `64px repeat(${editCalendarDates.length}, minmax(80px, 1fr))` }}
                          >
                            <div />
                            {editCalendarDates.map((date) => (
                              <div key={date.toISOString()} className="border-b border-[#777] pb-1">
                                {formatCalendarDate(date)}
                              </div>
                            ))}
                          </div>
                          <div
                            className="grid"
                            style={{ gridTemplateColumns: `64px repeat(${editCalendarDates.length}, minmax(80px, 1fr))` }}
                          >
                            {Array.from({ length: totalSlots }, (_, slotIndex) => (
                              <div key={slotIndex} className="contents">
                                <div className="pr-1 pt-0.5 text-right text-[11px] font-semibold text-[#444]">
                                  {slotIndex % 4 === 0 ? formatTimeLabel(slotIndex) : ""}
                                </div>
                                {editCalendarDates.map((date, dayIndex) => {
                                  const available = editAvailability[dayIndex]?.[slotIndex] ?? false;
                                  const showHourLine = slotIndex % 4 === 0;
                                  return (
                                    <button
                                      key={`${date.toISOString()}-${slotIndex}`}
                                      type="button"
                                      onMouseDown={() => {
                                        const nextValue = !available;
                                        setEditCell(dayIndex, slotIndex, nextValue);
                                        setEditDragValue(nextValue);
                                        setIsEditDragging(true);
                                      }}
                                      onMouseEnter={() => {
                                        if (!isEditDragging || editDragValue === null) return;
                                        setEditCell(dayIndex, slotIndex, editDragValue);
                                      }}
                                      onDragStart={(event) => event.preventDefault()}
                                      className={`h-4 border-r border-l border-b border-[#333] ${
                                        showHourLine ? "border-t border-t-[#333]" : ""
                                      } ${available ? "bg-[#38a000]" : "bg-[#f0d7d9]"}`}
                                      aria-label={`${formatCalendarDate(date)} ${formatTimeLabel(slotIndex)}`}
                                    />
                                  );
                                })}
                              </div>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  </aside>

                  <div className="lg:col-span-2">
                    <button
                      type="submit"
                      disabled={isSavingSymposiumEdit || isLoadingSymposiumDetails}
                      className="rounded-lg bg-[#0f33a8] px-5 py-2.5 text-sm font-semibold text-white transition hover:bg-[#0b2a8d] disabled:cursor-not-allowed disabled:opacity-60"
                    >
                      {isSavingSymposiumEdit ? "Saving..." : "Save Event Changes"}
                    </button>
                    {symposiumEditMessage ? <p className="mt-2 text-sm font-semibold text-[#222]">{symposiumEditMessage}</p> : null}
                  </div>
                </form>

                <div className="mt-6 rounded-xl border border-[#e6ecff] bg-[#fdfdff] p-4 md:p-5">
                  <h3 className="mb-3 text-lg font-bold text-[#111]">Departments</h3>
                  <form onSubmit={handleDepartmentSubmit} className="space-y-3">
                    <div className="flex items-center justify-between">
                      <div />
                      {departmentAction === "edit" ? (
                        <button
                          type="button"
                          onClick={() => {
                            setDepartmentAction("add");
                            setDepartmentToEditId("");
                            setDepartmentName("");
                            setDepartmentHeadName("");
                            setDepartmentHeadEmail("");
                          }}
                          className="rounded border border-[#bdbdbd] bg-white px-2 py-0.5 text-xs font-bold text-[#444] transition hover:bg-[#f5f5f5]"
                        >
                          Cancel Edit
                        </button>
                      ) : null}
                    </div>

                    <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
                      <label className="flex flex-col gap-1.5">
                        <span className="text-xs font-bold uppercase tracking-wide text-[#2d3d7a] md:text-sm">
                          Department Name
                        </span>
                        <input
                          className={fieldClass}
                          value={departmentName}
                          onChange={(event) => setDepartmentName(event.target.value)}
                          disabled={isSavingDepartment}
                        />
                      </label>
                      <label className="flex flex-col gap-1.5">
                        <span className="text-xs font-bold uppercase tracking-wide text-[#2d3d7a] md:text-sm">
                          Department Head
                        </span>
                        <input
                          className={fieldClass}
                          value={departmentHeadName}
                          onChange={(event) => setDepartmentHeadName(event.target.value)}
                          disabled={isSavingDepartment}
                        />
                      </label>
                      <label className="flex flex-col gap-1.5">
                        <span className="text-xs font-bold uppercase tracking-wide text-[#2d3d7a] md:text-sm">Email</span>
                        <input
                          type="email"
                          className={fieldClass}
                          value={departmentHeadEmail}
                          onChange={(event) => setDepartmentHeadEmail(event.target.value)}
                          disabled={isSavingDepartment}
                          placeholder="name@hamilton.edu"
                        />
                      </label>
                    </div>

                    <button
                      type="submit"
                      disabled={isSavingDepartment || isLoadingDepartments}
                      className="rounded-lg bg-[#0f33a8] px-4 py-2 text-sm font-semibold text-white transition hover:bg-[#0b2a8d] disabled:cursor-not-allowed disabled:opacity-60"
                    >
                      {isSavingDepartment
                        ? "Saving..."
                        : departmentAction === "add"
                          ? "Add Department"
                          : "Save Department Changes"}
                    </button>
                  </form>

                  {departmentLoadError ? (
                    <p className="mt-3 text-sm font-semibold text-[#9a1f1f]">{departmentLoadError}</p>
                  ) : null}
                  {departmentMessage ? (
                    <p
                      className={`mt-2 text-sm font-semibold ${
                        departmentMessageKind === "error" ? "text-[#9a1f1f]" : "text-[#1f5132]"
                      }`}
                    >
                      {departmentMessage}
                    </p>
                  ) : null}

                  <div className="mt-4 rounded-lg border border-[#d7e0ff] bg-white p-3">
                    <p className="text-sm font-bold uppercase tracking-wide text-[#2d3d7a]">Saved Departments</p>
                    {isLoadingDepartments ? (
                      <p className="mt-2 text-sm text-[#555]">Loading departments...</p>
                    ) : departments.length === 0 ? (
                      <p className="mt-2 text-sm text-[#555]">No departments saved yet.</p>
                    ) : (
                      <ul className="mt-2 space-y-2 text-sm text-[#222]">
                        {departments.map((department) => (
                          <li key={department.id} className="rounded border border-[#e5e7eb] bg-[#fafafa] p-2">
                            <div className="flex items-start justify-between gap-2">
                              <div>
                                <p className="font-semibold">{department.department_name}</p>
                                <p className="text-xs text-[#555]">
                                  {department.department_head_name} ({department.email})
                                </p>
                              </div>
                              <div className="flex items-center gap-2">
                                <button
                                  type="button"
                                  onClick={() => handleStartEditDepartment(department)}
                                  className="rounded border border-[#bdbdbd] bg-white px-2 py-0.5 text-xs font-bold text-[#444] transition hover:border-[#0f33a8] hover:text-[#0f33a8]"
                                >
                                  Edit
                                </button>
                                <button
                                  type="button"
                                  onClick={() => void handleDeleteDepartment(department)}
                                  disabled={deletingDepartmentId === department.id}
                                  className="rounded border border-[#bdbdbd] bg-white px-2 py-0.5 text-xs font-bold text-[#444] transition hover:border-[#9a1f1f] hover:text-[#9a1f1f] disabled:cursor-not-allowed disabled:opacity-60"
                                >
                                  {deletingDepartmentId === department.id ? "Deleting..." : "Delete"}
                                </button>
                              </div>
                            </div>
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>

                  <div className="mt-3">
                    <button
                      type="button"
                      onClick={handleDeployEvent}
                      className="rounded-lg bg-[#1b6e2b] px-4 py-2 text-sm font-semibold text-white transition hover:bg-[#155622]"
                    >
                      Deploy Event
                    </button>
                    {deployEventMessage ? <p className="mt-2 text-sm font-semibold text-[#222]">{deployEventMessage}</p> : null}
                  </div>
                </div>

              </>
            ) : (
              <div className="mt-5 rounded-xl border border-[#e0e0e0] bg-[#f9f9f9] p-4 text-sm font-semibold text-[#333]">
                Select an existing symposium to edit its event details and manage departments.
              </div>
            )}
          </section>
        )}
      </div>
    </main>
  );
}
