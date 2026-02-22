"use client";

<<<<<<< HEAD
import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";

<<<<<<< HEAD
type AdminTab = "create" | "edit";
type SymposiumOption = { id: string; label: string; roomsAvailable?: number };
type DepartmentContact = { department: string; headName: string; email: string };
=======
type AdminTab = "create" | "edit" | "department";
>>>>>>> 0bb4476 (Added admin add-department page and aligned frontend with backend request wiring)
=======
import { useCallback, useEffect, useMemo, useState } from "react";

type AdminTab = "create" | "edit";
type DepartmentAction = "add" | "edit" | "delete";

type SymposiumOption = {
  id: string;
  name: string;
  created_at?: string;
};

type TimeframeRecord = {
  id: string;
  start_time: string;
  end_time: string;
  symposium_id: string;
};

type DepartmentRecord = {
  id: string;
  symposium: string;
  department_name: string;
  department_head_name: string;
  email: string;
};
>>>>>>> fb51a0f (pulled from main and now fixed and finished the edit symposium page)

const fieldClass =
  "w-full rounded-lg border-2 border-[#2f53c4] bg-white px-3 py-2.5 text-base text-black shadow-sm outline-none transition focus:border-[#1237af] focus:ring-2 focus:ring-[#c7d4ff] placeholder:text-[#6b6b6b]";

const totalSlots = 32; // 9:00 AM to 5:00 PM in 15-minute increments
const weekDays = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const departmentOptions = [
  "Africana Studies",
  "American Indian and Indigenous Studies",
  "American Studies",
  "Anthropology",
  "Arabic",
  "Archaeology",
  "Art",
  "Art History",
  "Asian Studies (China, India, Japan)",
  "Astronomy",
  "Biochemistry/Molecular Biology",
  "Biology",
  "Chemical Physics",
  "Chemistry",
  "Chinese",
  "Cinema and Media Studies",
  "Classics",
  "Computer Science",
  "Creative Writing",
  "Dance and Movement Studies",
  "Data Science",
  "Digital Arts",
  "East Asian Languages and Literatures",
  "Economics",
  "Education Studies",
  "English",
  "Environmental Studies",
  "French and Francophone Studies",
  "Geoarchaeology",
  "Geosciences",
  "German, Russian, Italian, Arabic",
  "German Studies",
  "Government",
  "Greek: See Classics",
  "Hebrew",
  "Hispanic Studies",
  "History",
  "Interdisciplinary Concentration",
  "Italian Studies",
  "Japanese",
  "Jewish Studies",
  "Jurisprudence, Law and Justice Studies",
  "Latin: See Classics",
  "Latin American and Latine Studies",
  "Linguistics",
  "Literature and Creative Writing",
  "Mathematics and Statistics",
  "Medieval and Renaissance Studies",
  "Middle East and Islamicate Worlds Studies",
  "Music",
  "Neuroscience",
  "Philosophy",
  "Physics",
  "Psychology",
  "Public Policy",
  "Religious Studies",
  "Russian Studies",
  "Sociology",
  "Spanish",
  "Statistics",
  "Theatre",
  "Women's and Gender Studies",
  "World Politics",
];

function formatTimeLabel(slotIndex: number) {
  const totalMinutes = 9 * 60 + slotIndex * 15;
  const hour24 = Math.floor(totalMinutes / 60);
  const minutes = totalMinutes % 60;
  const suffix = hour24 >= 12 ? "PM" : "AM";
  const hour12 = hour24 % 12 === 0 ? 12 : hour24 % 12;
  const minutePart = minutes.toString().padStart(2, "0");
  return `${hour12}:${minutePart} ${suffix}`;
}

<<<<<<< HEAD
function toDateInputValue(date: Date) {
  const year = date.getFullYear();
  const month = `${date.getMonth() + 1}`.padStart(2, "0");
  const day = `${date.getDate()}`.padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function parseBackendDateTime(value: string) {
  const hasExplicitTimezone = /(?:Z|[+\-]\d{2}:\d{2})$/i.test(value);
  // Backend values without timezone should be treated as UTC to avoid local offset drift on reload.
  return new Date(hasExplicitTimezone ? value : `${value}Z`);
=======
function localDateString(date: Date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

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
    .map((tf) => localDateString(new Date(tf.start_time)))
    .sort((a, b) => (a < b ? -1 : a > b ? 1 : 0));
  const startDate = dayKeys[0];
  const endDate = dayKeys[dayKeys.length - 1];
  const dates = buildCalendarDates(startDate, endDate);

  const dayIndexByKey = new Map<string, number>();
  dates.forEach((date, index) => dayIndexByKey.set(localDateString(date), index));

  const availability = Array.from({ length: dates.length }, () => Array.from({ length: totalSlots }, () => false));

  for (const timeframe of timeframes) {
    const start = new Date(timeframe.start_time);
    const dayIndex = dayIndexByKey.get(localDateString(start));
    if (dayIndex === undefined) continue;

    const minutesFromStart = start.getHours() * 60 + start.getMinutes() - 9 * 60;
    if (minutesFromStart < 0) continue;
    const slotIndex = Math.floor(minutesFromStart / 15);
    if (slotIndex >= 0 && slotIndex < totalSlots) availability[dayIndex][slotIndex] = true;
  }

  return { startDate, endDate, availability };
>>>>>>> fb51a0f (pulled from main and now fixed and finished the edit symposium page)
}

export default function AdminPage() {
  const [activeTab, setActiveTab] = useState<AdminTab>("create");
<<<<<<< HEAD
  const [symposiumName, setSymposiumName] = useState("");
  const [rooms, setRooms] = useState("");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [availability, setAvailability] = useState<boolean[][]>([]);
  const [isDragging, setIsDragging] = useState(false);
  const [dragValue, setDragValue] = useState<boolean | null>(null);
  const [isSaving, setIsSaving] = useState(false);
  const [saveMessage, setSaveMessage] = useState<string | null>(null);
<<<<<<< HEAD
  const [deployMessage, setDeployMessage] = useState<string | null>(null);
  const [symposiumOptions, setSymposiumOptions] = useState<SymposiumOption[]>([]);
  const [selectedSymposiumId, setSelectedSymposiumId] = useState("");
  const [symposiumsLoading, setSymposiumsLoading] = useState(false);
  const [symposiumsError, setSymposiumsError] = useState<string | null>(null);
  const [hasLoadedEvent, setHasLoadedEvent] = useState(false);
  const [isEditingLoadedEvent, setIsEditingLoadedEvent] = useState(false);
  const [departmentToAdd, setDepartmentToAdd] = useState("");
  const [customDepartmentName, setCustomDepartmentName] = useState("");
  const [departmentContacts, setDepartmentContacts] = useState<DepartmentContact[]>([]);
=======
=======
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
  const [isLoadingSymposiums, setIsLoadingSymposiums] = useState(false);
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
>>>>>>> fb51a0f (pulled from main and now fixed and finished the edit symposium page)
  const [departmentName, setDepartmentName] = useState("");
  const [departmentHeadName, setDepartmentHeadName] = useState("");
  const [departmentHeadEmail, setDepartmentHeadEmail] = useState("");
  const [departmentToDeleteId, setDepartmentToDeleteId] = useState("");
  const [isSavingDepartment, setIsSavingDepartment] = useState(false);
<<<<<<< HEAD
  const [departmentSaveMessage, setDepartmentSaveMessage] = useState<string | null>(null);
  const [departmentMessageKind, setDepartmentMessageKind] = useState<"success" | "error" | "info" | null>(null);
  const [canAddDepartment, setCanAddDepartment] = useState(true);
>>>>>>> 0bb4476 (Added admin add-department page and aligned frontend with backend request wiring)

  const isCreateTab = activeTab === "create";
  const isEditTab = activeTab === "edit";
  const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:8000";
  const backendApiKey = process.env.NEXT_PUBLIC_BACKEND_API_KEY ?? "";
  const authHeaders = useMemo(
    () => (backendApiKey ? { "X-API-Key": backendApiKey } : undefined),
    [backendApiKey]
  );
=======
  const [departmentMessage, setDepartmentMessage] = useState<string | null>(null);
  const [departmentMessageKind, setDepartmentMessageKind] = useState<"success" | "error" | null>(null);

  const isCreateTab = activeTab === "create";
  const hasSelectedSymposium = Boolean(selectedSymposiumId.trim());
>>>>>>> fb51a0f (pulled from main and now fixed and finished the edit symposium page)

  const createCalendarDates = useMemo(
    () => buildCalendarDates(createStartDate, createEndDate),
    [createStartDate, createEndDate]
  );
  const editCalendarDates = useMemo(() => buildCalendarDates(editStartDate, editEndDate), [editStartDate, editEndDate]);

  const fetchSymposiums = useCallback(async () => {
    setIsLoadingSymposiums(true);
    setSymposiumLoadError(null);
    try {
      const response = await fetch(`${backendUrl}/api/events/symposiums`);
      const payload = (await response.json()) as { detail?: string; symposiums?: SymposiumOption[] };
      if (!response.ok) {
        setSymposiumLoadError(payload.detail ?? "Failed to load symposiums.");
        return;
      }
      setSymposiumOptions(payload.symposiums ?? []);
    } catch (error) {
      const message = error instanceof Error ? error.message : "Unknown error";
      setSymposiumLoadError(`Load failed: ${message}`);
    } finally {
      setIsLoadingSymposiums(false);
    }
  }, [backendUrl]);

  const fetchDepartments = useCallback(
    async (symposiumId: string) => {
      if (!symposiumId.trim()) {
        setDepartments([]);
        setDepartmentToEditId("");
        setDepartmentToDeleteId("");
        setDepartmentLoadError(null);
        return;
      }

      setIsLoadingDepartments(true);
      setDepartmentLoadError(null);
      try {
        const response = await fetch(`${backendUrl}/api/events/departments?symposium_id=${encodeURIComponent(symposiumId)}`);
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
        setDepartmentToDeleteId((current) =>
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
    [backendUrl]
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
        const response = await fetch(`${backendUrl}/api/events/symposiums/${symposiumId}`);
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
    [backendUrl]
  );

  useEffect(() => {
    void fetchSymposiums();
  }, [fetchSymposiums]);

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

<<<<<<< HEAD
  const refreshSymposiumOptions = useCallback(async () => {
    setSymposiumsLoading(true);
    setSymposiumsError(null);
    try {
      const response = await fetch(`${backendUrl}/api/events/symposiums`, {
        headers: authHeaders,
      });
      const payload = (await response.json()) as
        | {
            data?: Array<{
              id?: string;
              name?: string;
              symposium_name?: string;
              rooms_available?: number | string;
            }>;
          }
        | Array<{
            id?: string;
            name?: string;
            symposium_name?: string;
            rooms_available?: number | string;
          }>;

      if (!response.ok) {
        throw new Error("Failed to fetch symposiums.");
      }

      const rows = Array.isArray(payload) ? payload : (payload.data ?? []);
      const options = rows
        .filter((row) => row.id)
        .map((row) => ({
          id: row.id as string,
          label: row.name ?? row.symposium_name ?? (row.id as string),
          roomsAvailable:
            typeof row.rooms_available === "number"
              ? row.rooms_available
              : Number.isFinite(Number(row.rooms_available))
                ? Number(row.rooms_available)
                : undefined,
        }));

      setSymposiumOptions(options);
      setSelectedSymposiumId("");
    } catch (error) {
      const message = error instanceof Error ? error.message : "Unknown error";
      setSymposiumsError(message);
    } finally {
      setSymposiumsLoading(false);
    }
  }, [authHeaders, backendUrl]);

  useEffect(() => {
    void refreshSymposiumOptions();
  }, [refreshSymposiumOptions]);

  const setCell = (dayIndex: number, slotIndex: number, value: boolean) => {
    setAvailability((current) =>
=======
  useEffect(() => {
    setDepartmentMessage(null);
    setDepartmentMessageKind(null);
    setDepartmentName("");
    setDepartmentHeadName("");
    setDepartmentHeadEmail("");
    setDepartmentToEditId("");
    setDepartmentToDeleteId("");
    setDepartmentAction("add");
    void fetchDepartments(selectedSymposiumId);
    void fetchSymposiumDetails(selectedSymposiumId);
  }, [fetchDepartments, fetchSymposiumDetails, selectedSymposiumId]);

  useEffect(() => {
    if (departmentAction !== "add" && departmentAction !== "edit") return;

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
>>>>>>> fb51a0f (pulled from main and now fixed and finished the edit symposium page)
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
<<<<<<< HEAD
    if (!isCreateTab && !selectedSymposiumId) {
      setSaveMessage("Select and load an event before saving changes.");
      return;
    }
    setIsSaving(true);
=======

    setIsSavingCreate(true);
>>>>>>> fb51a0f (pulled from main and now fixed and finished the edit symposium page)
    try {
<<<<<<< HEAD
      const symposiumIdForSave = isCreateTab ? undefined : selectedSymposiumId;
=======
>>>>>>> 0bb4476 (Added admin add-department page and aligned frontend with backend request wiring)
      const response = await fetch(`${backendUrl}/api/events/add_symposium`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(authHeaders ?? {}),
        },
        body: JSON.stringify({
          symposium_id: symposiumIdForSave,
          symposium_name: trimmedName,
          rooms_available: parsedRooms,
          timeframes: timeframes.map(([start_time, end_time]) => ({ start_time, end_time })),
        }),
      });

<<<<<<< HEAD
      const payload = (await response.json()) as {
        detail?: string;
<<<<<<< HEAD
        symposium_id?: string;
        rows_written?: number;
=======
        status?: string;
        records_inserted?: {
          symposiums?: number;
          timeframes?: number;
        };
>>>>>>> 0bb4476 (Added admin add-department page and aligned frontend with backend request wiring)
      };

=======
      const payload = (await response.json()) as { detail?: string; status?: string; symposium_id?: string };
>>>>>>> fb51a0f (pulled from main and now fixed and finished the edit symposium page)
      if (!response.ok) {
        setCreateSaveMessage(payload.detail ?? "Failed to save symposium.");
        return;
      }

<<<<<<< HEAD
<<<<<<< HEAD
      setSaveMessage(`Saved symposium ${payload.symposium_id ?? "successfully"} with ${timeframes.length} timeframes.`);
      if (isCreateTab) {
        await refreshSymposiumOptions();
      }
=======
      setSaveMessage(
        payload.status
          ? `Saved symposium with ${timeframes.length} timeframes (${payload.status}).`
          : `Saved symposium with ${timeframes.length} timeframes.`
      );
      setCanAddDepartment(true);
      setActiveTab("department");
>>>>>>> 0bb4476 (Added admin add-department page and aligned frontend with backend request wiring)
=======
      setCreateSaveMessage("Event created successfully.");
      await fetchSymposiums();
      if (payload.symposium_id) setSelectedSymposiumId(payload.symposium_id);
      setActiveTab("edit");
>>>>>>> fb51a0f (pulled from main and now fixed and finished the edit symposium page)
    } catch (error) {
      const message = error instanceof Error ? error.message : "Unknown error";
      setCreateSaveMessage(`Save failed: ${message}`);
    } finally {
      setIsSavingCreate(false);
    }
  };

<<<<<<< HEAD
<<<<<<< HEAD
  const handleLoadEvent = async () => {
    if (!selectedSymposiumId) {
      setSymposiumsError("Select an event before loading.");
      return;
    }
    const selected = symposiumOptions.find((option) => option.id === selectedSymposiumId);
    if (selected) {
      setSymposiumName(selected.label);
      if (typeof selected.roomsAvailable === "number") {
        setRooms(String(selected.roomsAvailable));
      }
    }

    try {
      const response = await fetch(
        `${backendUrl}/api/events/timeframes?linked_id=${encodeURIComponent(selectedSymposiumId)}`,
        {
          headers: authHeaders,
        }
      );
      const payload = (await response.json()) as
        | { data?: Array<{ start_time?: string; end_time?: string }> }
        | Array<{ start_time?: string; end_time?: string }>;

      if (!response.ok) {
        throw new Error("Failed to fetch event timeframes.");
      }

      const timeframeRows = Array.isArray(payload) ? payload : (payload.data ?? []);
      const starts = timeframeRows
        .map((row) => row.start_time)
        .filter((value): value is string => Boolean(value))
        .map((value) => parseBackendDateTime(value))
        .filter((value) => !Number.isNaN(value.getTime()));

      if (starts.length > 0) {
        const minStart = new Date(Math.min(...starts.map((date) => date.getTime())));
        const maxStart = new Date(Math.max(...starts.map((date) => date.getTime())));
        const minDate = new Date(minStart.getFullYear(), minStart.getMonth(), minStart.getDate());
        const maxDate = new Date(maxStart.getFullYear(), maxStart.getMonth(), maxStart.getDate());
        const dayCount =
          Math.floor((maxDate.getTime() - minDate.getTime()) / (24 * 60 * 60 * 1000)) + 1;
        const nextAvailability = Array.from({ length: dayCount }, () =>
          Array.from({ length: totalSlots }, () => false)
        );

        for (const start of starts) {
          const startDay = new Date(start.getFullYear(), start.getMonth(), start.getDate());
          const dayIndex = Math.floor((startDay.getTime() - minDate.getTime()) / (24 * 60 * 60 * 1000));
          const minutes = start.getHours() * 60 + start.getMinutes();
          const slotIndex = (minutes - 9 * 60) / 15;
          if (dayIndex >= 0 && dayIndex < dayCount && slotIndex >= 0 && slotIndex < totalSlots) {
            nextAvailability[dayIndex][slotIndex] = true;
          }
        }

        setStartDate(toDateInputValue(minDate));
        setEndDate(toDateInputValue(maxDate));
        setAvailability(nextAvailability);
      } else {
        setStartDate("");
        setEndDate("");
        setAvailability([]);
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : "Unknown error";
      setSymposiumsError(message);
      return;
    }
    setSymposiumsError(null);
    setDepartmentContacts([]);
    setSaveMessage(null);
    setDeployMessage(null);
    setHasLoadedEvent(true);
    setIsEditingLoadedEvent(false);
  };

  const handleAddDepartment = () => {
    const nextDepartment =
      departmentToAdd === "__other__" ? customDepartmentName.trim() : departmentToAdd.trim();
    if (!nextDepartment) return;
    setDepartmentContacts((current) => {
      if (current.some((entry) => entry.department === nextDepartment)) return current;
      return [...current, { department: nextDepartment, headName: "", email: "" }];
    });
    setDepartmentToAdd("");
    setCustomDepartmentName("");
  };

  const handleDepartmentContactChange = (
    department: string,
    field: "headName" | "email",
    value: string
  ) => {
    setDepartmentContacts((current) =>
      current.map((entry) => (entry.department === department ? { ...entry, [field]: value } : entry))
    );
  };

  const handleRemoveDepartment = (department: string) => {
    setDepartmentContacts((current) => current.filter((entry) => entry.department !== department));
  };

  const resetPageToDefault = () => {
    setSymposiumName("");
    setRooms("");
    setStartDate("");
    setEndDate("");
    setAvailability([]);
    setIsDragging(false);
    setDragValue(null);
    setSaveMessage(null);
    setDeployMessage(null);
    setSelectedSymposiumId("");
    setSymposiumsError(null);
    setHasLoadedEvent(false);
    setIsEditingLoadedEvent(false);
    setDepartmentToAdd("");
    setCustomDepartmentName("");
    setDepartmentContacts([]);
  };

  const handleTabSwitch = (tab: AdminTab) => {
    setActiveTab(tab);
    resetPageToDefault();
    if (tab === "edit") {
      void refreshSymposiumOptions();
    }
  };

  const handleDeployEvent = async () => {
    setDeployMessage(null);
    if (!selectedSymposiumId) {
      setDeployMessage("Load an event before deploying.");
      return;
    }
    if (departmentContacts.length === 0) {
      setDeployMessage("Add at least one department before deploying.");
      return;
    }

    for (const department of departmentContacts) {
      if (!department.headName.trim()) {
        setDeployMessage(`Enter a department head for ${department.department} before deploying.`);
        return;
      }
      const email = department.email.trim().toLowerCase();
      if (!email) {
        setDeployMessage(`Enter an email for ${department.department} before deploying.`);
        return;
      }
      if (!email.endsWith("@hamilton.edu")) {
        setDeployMessage(`Email for ${department.department} must end in @hamilton.edu before deploying.`);
        return;
      }
    }
    setIsSaving(true);
    try {
      for (const department of departmentContacts) {
        const response = await fetch(`${backendUrl}/api/events/add_department`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            ...(authHeaders ?? {}),
          },
          body: JSON.stringify({
            symposium_id: selectedSymposiumId,
            department_name: department.department.trim(),
            department_head_name: department.headName.trim(),
            email: department.email.trim().toLowerCase(),
          }),
        });

        const payload = (await response.json().catch(() => ({}))) as { detail?: string };
        if (!response.ok) {
          throw new Error(payload.detail ?? `Failed to deploy department ${department.department}.`);
        }
      }
      setDeployMessage("Event deployed.");
    } catch (error) {
      const message = error instanceof Error ? error.message : "Unknown error";
      setDeployMessage(`Deploy failed: ${message}`);
    } finally {
      setIsSaving(false);
    }
  };

  const renderDepartmentsEditor = () => (
    <div className="rounded-xl border border-[#e6ecff] bg-[#fdfdff] p-4 md:p-5">
      <div className="hidden">
        <h3 className="text-sm font-bold uppercase tracking-wide text-[#2d3d7a] md:text-base">Departments</h3>
        <div className="mt-3 flex flex-col gap-2 md:flex-row md:items-end">
          <label className="flex-1">
            <span className="mb-1 block text-xs font-bold uppercase tracking-wide text-[#2d3d7a] md:text-sm">
              Select Department
            </span>
            <select
              className={fieldClass}
              value={departmentToAdd}
              onChange={(event) => {
                setDepartmentToAdd(event.target.value);
                if (event.target.value !== "__other__") {
                  setCustomDepartmentName("");
                }
              }}
            >
              <option value="">Choose a department</option>
              {departmentOptions.map((department) => (
                <option key={department} value={department}>
                  {department}
                </option>
              ))}
              <option value="__other__">Other</option>
            </select>
          </label>
          {departmentToAdd === "__other__" ? (
            <label className="flex-1">
              <span className="mb-1 block text-xs font-bold uppercase tracking-wide text-[#2d3d7a] md:text-sm">
                Custom Department Name
              </span>
              <input
                className={fieldClass}
                placeholder="Enter department name"
                value={customDepartmentName}
                onChange={(event) => setCustomDepartmentName(event.target.value)}
              />
            </label>
          ) : null}
          <button
            type="button"
            onClick={handleAddDepartment}
            disabled={!departmentToAdd || (departmentToAdd === "__other__" && !customDepartmentName.trim())}
            className="rounded-lg bg-[#0f33a8] px-4 py-2.5 text-sm font-semibold text-white shadow-[0_8px_18px_rgba(15,51,168,0.25)] transition hover:bg-[#0b2a8d] disabled:cursor-not-allowed disabled:opacity-60"
          >
            Add Department
          </button>
        </div>

        {departmentContacts.length > 0 ? (
          <div className="mt-4 space-y-3">
            {departmentContacts.map((entry) => (
              <div key={entry.department} className="rounded-lg border border-[#d7e0ff] bg-white p-3">
                <div className="mb-2 flex items-center justify-between gap-2">
                  <p className="text-sm font-semibold text-[#111]">{entry.department}</p>
                  <button
                    type="button"
                    onClick={() => handleRemoveDepartment(entry.department)}
                    className="rounded-md border border-[#b7b7b7] px-2 py-1 text-xs font-semibold text-[#333] transition hover:bg-[#f7f7f7]"
                  >
                    Remove
                  </button>
                </div>
                <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
                  <label className="flex flex-col gap-1">
                    <span className="text-xs font-bold uppercase tracking-wide text-[#2d3d7a] md:text-sm">
                      Department Head
                    </span>
                    <input
                      className={fieldClass}
                      placeholder="Full name"
                      value={entry.headName}
                      onChange={(event) =>
                        handleDepartmentContactChange(entry.department, "headName", event.target.value)
                      }
                    />
                  </label>
                  <label className="flex flex-col gap-1">
                    <span className="text-xs font-bold uppercase tracking-wide text-[#2d3d7a] md:text-sm">Email</span>
                    <input
                      type="email"
                      className={fieldClass}
                      placeholder="name@hamilton.edu"
                      pattern=".+@hamilton\.edu$"
                      value={entry.email}
                      onChange={(event) =>
                        handleDepartmentContactChange(entry.department, "email", event.target.value)
                      }
                    />
                  </label>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <p className="mt-3 text-xs font-semibold text-[#4b5d99]">
            Add one or more departments. Each selected department will require a department head and a
            @hamilton.edu email.
          </p>
        )}
      </div>
    </div>
  );

  const renderEventPreview = () => {
    const selectedSlots = availability.reduce(
      (total, daySlots) => total + daySlots.filter(Boolean).length,
      0
    );
    const selectedDays = calendarDates.length;

    return (
      <div className="space-y-4">
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          <div className="rounded-xl border border-[#e6ecff] bg-[#fdfdff] p-4">
            <p className="text-xs font-bold uppercase tracking-wide text-[#2d3d7a]">Symposium Name</p>
            <p className="mt-1 text-base font-semibold text-[#111]">{symposiumName || "Not set"}</p>
          </div>
          <div className="rounded-xl border border-[#e6ecff] bg-[#fdfdff] p-4">
            <p className="text-xs font-bold uppercase tracking-wide text-[#2d3d7a]">Rooms Available</p>
            <p className="mt-1 text-base font-semibold text-[#111]">{rooms || "Not set"}</p>
          </div>
          <div className="rounded-xl border border-[#e6ecff] bg-[#fdfdff] p-4">
            <p className="text-xs font-bold uppercase tracking-wide text-[#2d3d7a]">Start Date</p>
            <p className="mt-1 text-base font-semibold text-[#111]">{startDate || "Not set"}</p>
          </div>
          <div className="rounded-xl border border-[#e6ecff] bg-[#fdfdff] p-4">
            <p className="text-xs font-bold uppercase tracking-wide text-[#2d3d7a]">End Date</p>
            <p className="mt-1 text-base font-semibold text-[#111]">{endDate || "Not set"}</p>
          </div>
        </div>

        <div className="rounded-xl border border-[#e6ecff] bg-[#fdfdff] p-4">
          <p className="text-xs font-bold uppercase tracking-wide text-[#2d3d7a]">Availability Preview</p>
          <p className="mt-1 text-sm font-semibold text-[#111]">
            {selectedSlots} selected time slot{selectedSlots === 1 ? "" : "s"} across {selectedDays} day
            {selectedDays === 1 ? "" : "s"}.
          </p>
          <div className="mt-3 w-full overflow-x-auto rounded-xl border border-[#cfcfcf] bg-white p-2">
            {calendarDates.length === 0 ? (
              <div className="px-2 py-4 text-sm font-semibold text-[#555]">No calendar dates available.</div>
            ) : (
              <div className="min-w-[760px] select-none">
                <div
                  className="grid text-center text-base font-bold text-[#222]"
                  style={{ gridTemplateColumns: `64px repeat(${calendarDates.length}, minmax(80px, 1fr))` }}
                >
                  <div />
                  {calendarDates.map((date) => (
                    <div key={date.toISOString()} className="border-b border-[#777] pb-1">
                      {weekDays[date.getDay()]}
                    </div>
                  ))}
                </div>

                <div
                  className="grid"
                  style={{ gridTemplateColumns: `64px repeat(${calendarDates.length}, minmax(80px, 1fr))` }}
                >
                  {Array.from({ length: totalSlots }, (_, slotIndex) => (
                    <div key={slotIndex} className="contents">
                      <div className="pr-1 pt-0.5 text-right text-[11px] font-semibold text-[#444]">
                        {slotIndex % 4 === 0 ? formatTimeLabel(slotIndex) : ""}
                      </div>
                      {calendarDates.map((date, dayIndex) => {
                        const available = availability[dayIndex]?.[slotIndex] ?? false;
                        const showHourLine = slotIndex % 4 === 0;
                        return (
                          <div
                            key={`${date.toISOString()}-${slotIndex}`}
                            className={`h-4 border-r border-l border-b border-[#333] ${
                              showHourLine ? "border-t border-t-[#333]" : ""
                            } ${available ? "bg-[#38a000]" : "bg-[#f0d7d9]"}`}
                            aria-label={`${weekDays[date.getDay()]} ${formatTimeLabel(slotIndex)}`}
                          />
                        );
                      })}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>

      </div>
    );
  };

  const renderEventForm = ({
    showDepartments,
    submitLabel,
    stackDateFields = false,
  }: {
    showDepartments: boolean;
    submitLabel: string;
    stackDateFields?: boolean;
  }) => (
    <form onSubmit={handleCreateEventSubmit} className="grid grid-cols-1 gap-4 lg:grid-cols-[1.8fr_1fr]">
      <div className="rounded-xl border border-[#e6ecff] bg-[#fdfdff] p-4 md:p-5">
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          <label className="flex flex-col gap-1.5 md:col-span-2">
            <span className="text-xs font-bold uppercase tracking-wide text-[#2d3d7a] md:text-sm">
              Symposium Name
            </span>
            <input
              className={fieldClass}
              placeholder="Ex. OCC Thesis Symposium 2026"
              value={symposiumName}
              onChange={(event) => setSymposiumName(event.target.value)}
            />
          </label>
          <label className="flex flex-col gap-1.5">
            <span className="text-xs font-bold uppercase tracking-wide text-[#2d3d7a] md:text-sm">
              Rooms Available
            </span>
            <input
              type="number"
              min={1}
              className={fieldClass}
              placeholder="Ex. 5"
              value={rooms}
              onChange={(event) => setRooms(event.target.value)}
            />
          </label>
        </div>

        <div className={`mt-5 grid grid-cols-1 gap-4 ${stackDateFields ? "" : "md:grid-cols-2"}`}>
          <label className="flex flex-col gap-1.5">
            <span className="text-xs font-bold uppercase tracking-wide text-[#2d3d7a] md:text-sm">Start Date</span>
            <input
              type="date"
              className={fieldClass}
              value={startDate}
              onChange={(event) => setStartDate(event.target.value)}
            />
          </label>
          <label className="flex flex-col gap-1.5">
            <span className="text-xs font-bold uppercase tracking-wide text-[#2d3d7a] md:text-sm">End Date</span>
            <input
              type="date"
              className={fieldClass}
              value={endDate}
              onChange={(event) => setEndDate(event.target.value)}
            />
          </label>
        </div>

        <p className="mt-3 text-xs font-semibold text-[#4b5d99]">
          Calendar columns are generated from start date through end date. Selected slots are sent as date-time
          tuples.
        </p>
      </div>

      <aside className="rounded-xl border border-[#d7bf92] bg-[#fffdf8] p-4 md:p-5">
        <div className="mb-4 flex flex-wrap items-center gap-5 text-sm font-semibold text-[#333] md:text-base">
          <div className="flex items-center gap-2">
            <span>Unavailable</span>
            <span className="inline-block h-6 w-8 border border-[#777] bg-[#f0d7d9]" />
          </div>
          <div className="flex items-center gap-2">
            <span>Available</span>
            <span className="inline-block h-6 w-8 border border-[#777] bg-[#38a000]" />
          </div>
        </div>

        <p className="mb-3 text-sm font-semibold text-[#444] md:text-base">Click and drag to toggle availability.</p>

        <div className="w-full overflow-x-auto rounded-xl border border-[#cfcfcf] bg-white p-2">
          {calendarDates.length === 0 ? (
            <div className="px-2 py-4 text-sm font-semibold text-[#555]">
              Select start and end dates to build the availability calendar.
            </div>
          ) : (
            <div className="min-w-[760px] select-none">
              <div
                className="grid text-center text-base font-bold text-[#222]"
                style={{ gridTemplateColumns: `64px repeat(${calendarDates.length}, minmax(80px, 1fr))` }}
              >
                <div />
                {calendarDates.map((date) => (
                  <div key={date.toISOString()} className="border-b border-[#777] pb-1">
                    {weekDays[date.getDay()]}
                  </div>
                ))}
              </div>

              <div
                className="grid"
                style={{ gridTemplateColumns: `64px repeat(${calendarDates.length}, minmax(80px, 1fr))` }}
              >
                {Array.from({ length: totalSlots }, (_, slotIndex) => (
                  <div key={slotIndex} className="contents">
                    <div className="pr-1 pt-0.5 text-right text-[11px] font-semibold text-[#444]">
                      {slotIndex % 4 === 0 ? formatTimeLabel(slotIndex) : ""}
                    </div>

                    {calendarDates.map((date, dayIndex) => {
                      const available = availability[dayIndex]?.[slotIndex] ?? false;
                      const showHourLine = slotIndex % 4 === 0;
                      return (
                        <button
                          key={`${date.toISOString()}-${slotIndex}`}
                          type="button"
                          onMouseDown={() => handleCellMouseDown(dayIndex, slotIndex)}
                          onMouseEnter={() => handleCellMouseEnter(dayIndex, slotIndex)}
                          onDragStart={(event) => event.preventDefault()}
                          className={`h-4 border-r border-l border-b border-[#333] ${
                            showHourLine ? "border-t border-t-[#333]" : ""
                          } ${available ? "bg-[#38a000]" : "bg-[#f0d7d9]"}`}
                          aria-label={`${weekDays[date.getDay()]} ${formatTimeLabel(slotIndex)}`}
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

      {showDepartments ? (
        <div className="md:col-span-2">{renderDepartmentsEditor()}</div>
      ) : null}

      <div className="lg:col-span-2">
        <button
          type="submit"
          disabled={isSaving}
          className="rounded-lg bg-[#0f33a8] px-5 py-2.5 text-sm font-semibold text-white shadow-[0_8px_18px_rgba(15,51,168,0.25)] transition hover:bg-[#0b2a8d] disabled:cursor-not-allowed disabled:opacity-60 md:text-base"
        >
          {isSaving ? "Saving..." : submitLabel}
        </button>
        {saveMessage ? <p className="mt-2 text-sm font-semibold text-[#222]">{saveMessage}</p> : null}
      </div>
    </form>
  );

=======
  const departmentPayloadPreview = useMemo(
    () => ({
      department_head_name: departmentHeadName.trim(),
      department_name: departmentName.trim(),
      email: departmentHeadEmail.trim().toLowerCase(),
      symposium: symposiumId.trim() || TEST_SYMPOSIUM_UUID,
    }),
    [departmentHeadEmail, departmentHeadName, departmentName, symposiumId]
  );
=======
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
        headers: { "Content-Type": "application/json" },
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
      await fetchSymposiums();
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
      const response = await fetch(`${backendUrl}/api/events/symposiums/${selectedSymposiumId}`, { method: "DELETE" });
      const payload = (await response.json()) as { detail?: string; status?: string };
      if (!response.ok) {
        setSymposiumEditMessage(payload.detail ?? "Failed to delete event.");
        return;
      }

      setSymposiumEditMessage("Event deleted.");
      setSelectedSymposiumId("");
      await fetchSymposiums();
    } catch (error) {
      const message = error instanceof Error ? error.message : "Unknown error";
      setSymposiumEditMessage(`Delete failed: ${message}`);
    } finally {
      setIsDeletingSymposium(false);
    }
  };
>>>>>>> fb51a0f (pulled from main and now fixed and finished the edit symposium page)

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
    } else {
      if (!departmentToDeleteId) {
        setDepartmentMessage("Select a department to delete.");
        setDepartmentMessageKind("error");
        return;
      }
    }

    setIsSavingDepartment(true);
    try {
      if (departmentAction === "add") {
        const response = await fetch(`${backendUrl}/api/events/add_department`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            symposium: selectedSymposiumId,
            department_name: departmentName.trim(),
            department_head_name: departmentHeadName.trim(),
            email: departmentHeadEmail.trim().toLowerCase(),
          }),
        });

        const payload = (await response.json()) as { detail?: string; status?: string };
        if (!response.ok) {
          setDepartmentMessage(payload.detail ?? "Failed to add department.");
          setDepartmentMessageKind("error");
          return;
        }

        setDepartmentName("");
        setDepartmentHeadName("");
        setDepartmentHeadEmail("");
        setDepartmentMessage("Department added.");
        setDepartmentMessageKind("success");
      } else if (departmentAction === "edit") {
        const response = await fetch(`${backendUrl}/api/events/departments/${departmentToEditId}`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            department_name: departmentName.trim(),
            department_head_name: departmentHeadName.trim(),
            email: departmentHeadEmail.trim().toLowerCase(),
          }),
        });

        const payload = (await response.json()) as { detail?: string; status?: string };
        if (!response.ok) {
          setDepartmentMessage(payload.detail ?? "Failed to update department.");
          setDepartmentMessageKind("error");
          return;
        }

        setDepartmentMessage("Department updated.");
        setDepartmentMessageKind("success");
      } else {
        const response = await fetch(`${backendUrl}/api/events/departments/${departmentToDeleteId}`, {
          method: "DELETE",
        });

        const payload = (await response.json()) as { detail?: string; status?: string };
        if (!response.ok) {
          setDepartmentMessage(payload.detail ?? "Failed to delete department.");
          setDepartmentMessageKind("error");
          return;
        }

        setDepartmentMessage("Department deleted.");
        setDepartmentMessageKind("success");
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

>>>>>>> 0bb4476 (Added admin add-department page and aligned frontend with backend request wiring)
  return (
    <main className="min-h-screen bg-[linear-gradient(180deg,#f7f9ff_0%,#f4f4f4_55%,#f1f1f1_100%)] px-4 py-8">
      <div className="mx-auto w-full max-w-6xl">
        <div className="mb-3 flex justify-end">
          <Link
            href="/"
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
<<<<<<< HEAD
            {renderEventForm({ showDepartments: false, submitLabel: "Save Event", stackDateFields: true })}
          </section>
        ) : isEditTab ? (
          <section className="rounded-2xl border border-[#d7bf92] bg-white p-4 shadow-[0_16px_30px_rgba(80,60,20,0.08)] md:p-6">
            <h2 className="mb-4 text-xl font-bold text-[#111] md:text-2xl">Edit Existing Event</h2>
            <div className="w-full space-y-3 rounded-xl border border-[#e6ecff] bg-[#fdfdff] p-4 md:p-5">
              <label className="flex flex-col gap-1.5">
                  <span className="text-xs font-bold uppercase tracking-wide text-[#2d3d7a] md:text-sm">Select Event</span>
                  <select
                    value={selectedSymposiumId}
                    onChange={(event) => {
                      setSelectedSymposiumId(event.target.value);
                      setHasLoadedEvent(false);
                      setIsEditingLoadedEvent(false);
                      setSaveMessage(null);
                      setDeployMessage(null);
                    }}
                    disabled={symposiumsLoading || symposiumOptions.length === 0}
                    className="w-full rounded-lg border border-[#c7c7c7] bg-white px-3 py-2.5 text-black shadow-sm outline-none transition focus:border-[#1237af] focus:ring-2 focus:ring-[#c7d4ff] disabled:cursor-not-allowed disabled:opacity-60"
                  >
                  {!symposiumsLoading ? <option value="">Select an event</option> : null}
                  {symposiumsLoading ? <option>Loading symposiums...</option> : null}
                  {!symposiumsLoading && symposiumOptions.length === 0 ? (
                    <option>No symposiums found</option>
                  ) : null}
                  {symposiumOptions.map((symposium) => (
                    <option key={symposium.id} value={symposium.id}>
                      {symposium.label}
                    </option>
                  ))}
                </select>
              </label>
              <div className="rounded-lg border border-[#e0e0e0] bg-[#f9f9f9] p-3 text-sm text-[#333]">
                Choose an event to load and edit its details.
              </div>
              {symposiumsError ? (
                <p className="text-sm font-semibold text-[#9a1f1f]">Failed to load symposiums: {symposiumsError}</p>
              ) : null}
              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={handleLoadEvent}
                  className="rounded-lg bg-[#0f33a8] px-4 py-2 text-sm font-semibold text-white shadow-[0_8px_18px_rgba(15,51,168,0.25)] transition hover:bg-[#0b2a8d] md:text-base"
                >
                  Load Event
                </button>
              </div>
              {hasLoadedEvent ? (
                <div className="mt-4 border-t border-[#d7e0ff] pt-4">
                  <h3 className="mb-3 text-lg font-bold text-[#111] md:text-xl">
                    {isEditingLoadedEvent ? "Edit Event" : "Event Preview"}
                  </h3>
                  {isEditingLoadedEvent ? (
                    <>
                      {renderEventForm({
                        showDepartments: false,
                        submitLabel: "Save Changes",
                        stackDateFields: true,
                      })}
                      <button
                        type="button"
                        onClick={() => setIsEditingLoadedEvent(false)}
                        className="mt-3 rounded-lg border border-[#b7b7b7] bg-white px-4 py-2 text-sm font-semibold text-[#222] transition hover:bg-[#f7f7f7] md:text-base"
                      >
                        Back to Preview
                      </button>
                      <div className="mt-3">{renderDepartmentsEditor()}</div>
                    </>
                  ) : (
                    <div className="space-y-3">
                      <div className="rounded-xl border border-[#e6ecff] bg-[#fdfdff] p-4 md:p-5">
                        {renderEventPreview()}
                      </div>
                      <div className="flex flex-wrap gap-2">
                        <button
                          type="button"
                          onClick={() => setIsEditingLoadedEvent(true)}
                          className="rounded-lg bg-[#0f33a8] px-4 py-2 text-sm font-semibold text-white shadow-[0_8px_18px_rgba(15,51,168,0.25)] transition hover:bg-[#0b2a8d] md:text-base"
                        >
                          Edit Event
                        </button>
                        <button
                          type="button"
                          className="rounded-lg border border-[#b7b7b7] bg-white px-4 py-2 text-sm font-semibold text-[#222] transition hover:bg-[#f7f7f7] md:text-base"
                        >
                          Delete Event
                        </button>
                      </div>
                      {renderDepartmentsEditor()}
                    </div>
                  )}
                  <div className="mt-4 border-t border-[#d7e0ff] pt-4">
                    <button
                      type="button"
                      onClick={handleDeployEvent}
                      disabled={isSaving}
                      className="rounded-lg bg-[#1b6e2b] px-4 py-2 text-sm font-semibold text-white shadow-[0_8px_18px_rgba(27,110,43,0.25)] transition hover:bg-[#155622] disabled:cursor-not-allowed disabled:opacity-60 md:text-base"
                    >
                      {isSaving ? "Deploying..." : "Deploy Event"}
                    </button>
                    {deployMessage ? <p className="mt-2 text-sm font-semibold text-[#222]">{deployMessage}</p> : null}
                  </div>
                </div>
              ) : null}
            </div>
          </section>
=======

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

                <div className="mt-5 grid grid-cols-1 gap-4 md:grid-cols-2">
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
                            {weekDays[date.getDay()]}
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
                                  aria-label={`${weekDays[date.getDay()]} ${formatTimeLabel(slotIndex)}`}
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
>>>>>>> fb51a0f (pulled from main and now fixed and finished the edit symposium page)
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
                  disabled={isLoadingSymposiums}
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
                  onClick={() => void fetchSymposiums()}
                  disabled={isLoadingSymposiums}
                  className="rounded-lg bg-[#0f33a8] px-4 py-2 text-sm font-semibold text-white transition hover:bg-[#0b2a8d] disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {isLoadingSymposiums ? "Loading..." : "Refresh Symposium List"}
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

                    <div className="mt-5 grid grid-cols-1 gap-4 md:grid-cols-2">
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
                                {weekDays[date.getDay()]}
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
                                      aria-label={`${weekDays[date.getDay()]} ${formatTimeLabel(slotIndex)}`}
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

                  <form onSubmit={handleDepartmentSubmit} className="space-y-4">
                    <label className="flex flex-col gap-1.5 max-w-sm">
                      <span className="text-xs font-bold uppercase tracking-wide text-[#2d3d7a] md:text-sm">Action</span>
                      <select
                        className={fieldClass}
                        value={departmentAction}
                        onChange={(event) => {
                          const nextAction = event.target.value as DepartmentAction;
                          setDepartmentAction(nextAction);
                          if (nextAction === "add") {
                            setDepartmentToEditId("");
                            setDepartmentName("");
                            setDepartmentHeadName("");
                            setDepartmentHeadEmail("");
                          }
                        }}
                      >
                        <option value="add">Add Department</option>
                        <option value="edit">Edit Department</option>
                        <option value="delete">Delete Department</option>
                      </select>
                    </label>

                    {departmentAction === "add" || departmentAction === "edit" ? (
                      <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
                        <label className="flex flex-col gap-1.5 md:col-span-3">
                          <span className="text-xs font-bold uppercase tracking-wide text-[#2d3d7a] md:text-sm">
                            {departmentAction === "add"
                              ? "Select Existing Department (Optional Prefill)"
                              : "Select Department To Edit"}
                          </span>
                          <select
                            className={fieldClass}
                            value={departmentToEditId}
                            onChange={(event) => setDepartmentToEditId(event.target.value)}
                            disabled={departmentAction === "add" || isLoadingDepartments || departments.length === 0}
                          >
                            {departmentAction === "add" ? (
                              <option value="">Create new department</option>
                            ) : (
                              <>
                                {departments.length === 0 ? <option value="">No departments found</option> : null}
                                {departments.map((department) => (
                                  <option key={department.id} value={department.id}>
                                    {department.department_name} - {department.department_head_name}
                                  </option>
                                ))}
                              </>
                            )}
                          </select>
                        </label>
                        <label className="flex flex-col gap-1.5">
                          <span className="text-xs font-bold uppercase tracking-wide text-[#2d3d7a] md:text-sm">Department Name</span>
                          <input
                            className={fieldClass}
                            value={departmentName}
                            onChange={(event) => setDepartmentName(event.target.value)}
                            placeholder="Ex. Biology"
                          />
                        </label>
                        <label className="flex flex-col gap-1.5">
                          <span className="text-xs font-bold uppercase tracking-wide text-[#2d3d7a] md:text-sm">Department Head Name</span>
                          <input
                            className={fieldClass}
                            value={departmentHeadName}
                            onChange={(event) => setDepartmentHeadName(event.target.value)}
                            placeholder="Ex. John Smith"
                          />
                        </label>
                        <label className="flex flex-col gap-1.5">
                          <span className="text-xs font-bold uppercase tracking-wide text-[#2d3d7a] md:text-sm">Hamilton Email</span>
                          <input
                            type="email"
                            className={fieldClass}
                            value={departmentHeadEmail}
                            onChange={(event) => setDepartmentHeadEmail(event.target.value)}
                            placeholder="jsmith@hamilton.edu"
                          />
                        </label>
                      </div>
                    ) : (
                      <label className="flex flex-col gap-1.5 max-w-xl">
                        <span className="text-xs font-bold uppercase tracking-wide text-[#2d3d7a] md:text-sm">
                          Select Department To Delete
                        </span>
                        <select
                          className={fieldClass}
                          value={departmentToDeleteId}
                          onChange={(event) => setDepartmentToDeleteId(event.target.value)}
                          disabled={isLoadingDepartments || departments.length === 0}
                        >
                          {departments.length === 0 ? <option value="">No departments found</option> : null}
                          {departments.map((department) => (
                            <option key={department.id} value={department.id}>
                              {department.department_name} - {department.department_head_name}
                            </option>
                          ))}
                        </select>
                      </label>
                    )}

                    <div className="flex flex-wrap gap-2">
                      <button
                        type="submit"
                        disabled={isSavingDepartment || !hasSelectedSymposium}
                        className="rounded-lg bg-[#0f33a8] px-5 py-2.5 text-sm font-semibold text-white transition hover:bg-[#0b2a8d] disabled:cursor-not-allowed disabled:opacity-60"
                      >
                        {isSavingDepartment
                          ? "Saving..."
                          : departmentAction === "add"
                            ? "Add Department"
                            : departmentAction === "edit"
                              ? "Update Department"
                              : "Delete Department"}
                      </button>
                      <button
                        type="button"
                        onClick={() => void fetchDepartments(selectedSymposiumId)}
                        disabled={isLoadingDepartments || !hasSelectedSymposium}
                        className="rounded-lg border border-[#b7b7b7] bg-white px-4 py-2 text-sm font-semibold text-[#222] transition hover:bg-[#f7f7f7] disabled:cursor-not-allowed disabled:opacity-60"
                      >
                        {isLoadingDepartments ? "Loading..." : "Refresh Departments"}
                      </button>
                    </div>

                    {departmentLoadError ? <p className="text-sm font-semibold text-[#b00020]">{departmentLoadError}</p> : null}
                    {departmentMessage ? (
                      <p className={`text-sm font-semibold ${departmentMessageKind === "error" ? "text-[#b00020]" : "text-[#167a2f]"}`}>
                        {departmentMessage}
                      </p>
                    ) : null}
                  </form>
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
