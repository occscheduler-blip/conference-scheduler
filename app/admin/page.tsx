"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

type AdminTab = "create" | "edit";
type SymposiumOption = { id: string; label: string; roomsAvailable?: number };
type DepartmentContact = { department: string; headName: string; email: string };

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

function toDateInputValue(date: Date) {
  const year = date.getFullYear();
  const month = `${date.getMonth() + 1}`.padStart(2, "0");
  const day = `${date.getDate()}`.padStart(2, "0");
  return `${year}-${month}-${day}`;
}

export default function AdminPage() {
  const [activeTab, setActiveTab] = useState<AdminTab>("create");
  const [symposiumName, setSymposiumName] = useState("");
  const [rooms, setRooms] = useState("");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [availability, setAvailability] = useState<boolean[][]>([]);
  const [isDragging, setIsDragging] = useState(false);
  const [dragValue, setDragValue] = useState<boolean | null>(null);
  const [isSaving, setIsSaving] = useState(false);
  const [saveMessage, setSaveMessage] = useState<string | null>(null);
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

  const isCreateTab = activeTab === "create";
  const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:8000";

  const calendarDates = useMemo(() => {
    if (!startDate || !endDate) return [];
    const start = new Date(`${startDate}T00:00:00`);
    const end = new Date(`${endDate}T00:00:00`);
    if (Number.isNaN(start.getTime()) || Number.isNaN(end.getTime()) || end < start) return [];

    const dates: Date[] = [];
    const cursor = new Date(start);
    while (cursor <= end) {
      dates.push(new Date(cursor));
      cursor.setDate(cursor.getDate() + 1);
    }
    return dates;
  }, [startDate, endDate]);

  useEffect(() => {
    if (calendarDates.length === 0) {
      setAvailability([]);
      return;
    }

    setAvailability((current) => {
      const next = Array.from({ length: calendarDates.length }, (_, dayIndex) =>
        Array.from({ length: totalSlots }, (_, slotIndex) => current[dayIndex]?.[slotIndex] ?? false)
      );
      return next;
    });
  }, [calendarDates]);

  useEffect(() => {
    const stopDragging = () => {
      setIsDragging(false);
      setDragValue(null);
    };

    window.addEventListener("mouseup", stopDragging);
    return () => window.removeEventListener("mouseup", stopDragging);
  }, []);

  const refreshSymposiumOptions = useCallback(async () => {
    setSymposiumsLoading(true);
    setSymposiumsError(null);
    try {
      const response = await fetch(`${backendUrl}/api/events/symposiums`);
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
  }, [backendUrl]);

  useEffect(() => {
    void refreshSymposiumOptions();
  }, [refreshSymposiumOptions]);

  const setCell = (dayIndex: number, slotIndex: number, value: boolean) => {
    setAvailability((current) =>
      current.map((daySlots, dIdx) =>
        dIdx === dayIndex ? daySlots.map((slot, sIdx) => (sIdx === slotIndex ? value : slot)) : daySlots
      )
    );
  };

  const handleCellMouseDown = (dayIndex: number, slotIndex: number) => {
    const nextValue = !availability[dayIndex][slotIndex];
    setCell(dayIndex, slotIndex, nextValue);
    setDragValue(nextValue);
    setIsDragging(true);
  };

  const handleCellMouseEnter = (dayIndex: number, slotIndex: number) => {
    if (!isDragging || dragValue === null) return;
    setCell(dayIndex, slotIndex, dragValue);
  };

  const buildTimeframes = (dates: Date[]) => {
    if (dates.length === 0) {
      return null;
    }

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
  };

  const handleCreateEventSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setSaveMessage(null);

    const trimmedName = symposiumName.trim();
    if (!trimmedName) {
      setSaveMessage("Enter a symposium name.");
      return;
    }
    const parsedRooms = Number.parseInt(rooms, 10);
    if (!Number.isFinite(parsedRooms) || parsedRooms <= 0) {
      setSaveMessage("Enter a valid number of rooms.");
      return;
    }
    if (!startDate) {
      setSaveMessage("Select a start date.");
      return;
    }
    if (!endDate) {
      setSaveMessage("Select an end date.");
      return;
    }
    if (calendarDates.length === 0) {
      setSaveMessage("End date must be on or after start date.");
      return;
    }

    const timeframes = buildTimeframes(calendarDates);
    if (!timeframes) {
      setSaveMessage("Invalid dates.");
      return;
    }
    if (timeframes.length === 0) {
      setSaveMessage("Select at least one available time slot.");
      return;
    }
    if (!isCreateTab && !selectedSymposiumId) {
      setSaveMessage("Select and load an event before saving changes.");
      return;
    }
    setIsSaving(true);
    try {
      const symposiumIdForSave = isCreateTab ? undefined : selectedSymposiumId;
      const response = await fetch(`${backendUrl}/api/events/add_symposium`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          symposium_id: symposiumIdForSave,
          symposium_name: trimmedName,
          rooms_available: parsedRooms,
          timeframes: timeframes.map(([start_time, end_time]) => ({ start_time, end_time })),
        }),
      });

      const payload = (await response.json()) as {
        detail?: string;
        symposium_id?: string;
        rows_written?: number;
      };

      if (!response.ok) {
        setSaveMessage(payload.detail ?? "Failed to save symposium.");
        return;
      }

      setSaveMessage(`Saved symposium ${payload.symposium_id ?? "successfully"} with ${timeframes.length} timeframes.`);
      if (isCreateTab) {
        await refreshSymposiumOptions();
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : "Unknown error";
      if (message.toLowerCase().includes("load failed") || message.toLowerCase().includes("failed to fetch")) {
        setSaveMessage("Save failed: backend is unreachable at http://localhost:8000.");
      } else {
        setSaveMessage(`Save failed: ${message}`);
      }
    } finally {
      setIsSaving(false);
    }
  };

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
        `${backendUrl}/api/events/timeframes?linked_id=${encodeURIComponent(selectedSymposiumId)}`
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
        .map((value) => new Date(value))
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
          headers: { "Content-Type": "application/json" },
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

  return (
    <main className="min-h-screen bg-[linear-gradient(180deg,#f7f9ff_0%,#f4f4f4_55%,#f1f1f1_100%)] px-4 py-8">
      <div className="mx-auto w-full max-w-6xl">
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
            {renderEventForm({ showDepartments: false, submitLabel: "Save Event", stackDateFields: true })}
          </section>
        ) : (
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
        )}
      </div>
    </main>
  );
}
