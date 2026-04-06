"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import type {
  AdminTab,
  DepartmentAction,
  DepartmentRecord,
  SymposiumOption,
  TimeframeRecord,
} from "./types";
import {
  totalSlots,
  formatTimeLabel,
  formatCalendarDate,
  buildCalendarDates,
  buildTimeframesFromGrid,
  gridFromTimeframes,
} from "../lib/utils";
import { apiFetch, apiPost, apiPut, apiDelete } from "../lib/api";
import { useCalendarGrid } from "../lib/useCalendarGrid";
import ScheduleTab from "./schedule-tab";

const fieldClass =
  "w-full rounded-lg border-2 border-[#2f53c4] bg-white px-3 py-2.5 text-base text-black shadow-sm outline-none transition focus:border-[#1237af] focus:ring-2 focus:ring-[#c7d4ff] placeholder:text-[#6b6b6b]";

export default function AdminPage({ token, onSignOut }: { token: string; onSignOut: () => void }) {
  const [activeTab, setActiveTab] = useState<AdminTab>("create");
  const authHeaders = useMemo(() => ({ Authorization: `Bearer ${token}` }), [token]);

  // Create event state
  const [createSymposiumName, setCreateSymposiumName] = useState("");
  const [createRooms, setCreateRooms] = useState("");
  const [createStartDate, setCreateStartDate] = useState("");
  const [createEndDate, setCreateEndDate] = useState("");
  const [createDefaultBuffer, setCreateDefaultBuffer] = useState("");
  const {
    availability: createAvailability,
    setAvailability: setCreateAvailability,
    handleCellMouseDown: handleCreateCellMouseDown,
    handleCellMouseEnter: handleCreateCellMouseEnter,
  } = useCalendarGrid(buildCalendarDates(createStartDate, createEndDate).length);
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
  const [editDefaultBuffer, setEditDefaultBuffer] = useState("");
  const {
    availability: editAvailability,
    setAvailability: setEditAvailability,
    handleCellMouseDown: handleEditCellMouseDown,
    handleCellMouseEnter: handleEditCellMouseEnter,
  } = useCalendarGrid(buildCalendarDates(editStartDate, editEndDate).length);
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

  // Manage Admins tab state
  const [newAdminEmail, setNewAdminEmail] = useState("");
  const [newAdminPassword, setNewAdminPassword] = useState("");
  const [newAdminConfirmPassword, setNewAdminConfirmPassword] = useState("");
  const [showAdminPassword, setShowAdminPassword] = useState(false);
  const [showAdminConfirmPassword, setShowAdminConfirmPassword] = useState(false);
  const [isCreatingAdmin, setIsCreatingAdmin] = useState(false);
  const [adminMessage, setAdminMessage] = useState<string | null>(null);
  const [adminMessageKind, setAdminMessageKind] = useState<"success" | "error" | null>(null);

  const isCreateTab = activeTab === "create";
  const isEditTab = activeTab === "edit";
  const hasSelectedSymposium = Boolean(selectedSymposiumId.trim());

  const createCalendarDates = useMemo(
    () => buildCalendarDates(createStartDate, createEndDate),
    [createStartDate, createEndDate]
  );
  const editCalendarDates = useMemo(() => buildCalendarDates(editStartDate, editEndDate), [editStartDate, editEndDate]);

  const fetchSymposia = useCallback(async () => {
    setIsLoadingSymposia(true);
    setSymposiumLoadError(null);
    try {
      const rows = await apiFetch<SymposiumOption>("/api/events/symposiums", { headers: authHeaders });
      setSymposiumOptions(rows);
    } catch (error) {
      const message = error instanceof Error ? error.message : "Unknown error";
      setSymposiumLoadError(`Load failed: ${message}`);
    } finally {
      setIsLoadingSymposia(false);
    }
  }, [authHeaders]);

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
        const loaded = await apiFetch<DepartmentRecord>(
          `/api/events/departments?symposium_id=${encodeURIComponent(symposiumId)}`,
          { headers: authHeaders }
        );
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
    [authHeaders]
  );

  const fetchSymposiumDetails = useCallback(
    async (symposiumId: string) => {
      if (!symposiumId.trim()) {
        setEditSymposiumName("");
        setEditRooms("");
        setEditDefaultBuffer("");
        setEditStartDate("");
        setEditEndDate("");
        setEditAvailability([]);
        return;
      }

      setIsLoadingSymposiumDetails(true);
      setSymposiumEditMessage(null);
      try {
        // This endpoint returns {symposium, timeframes} — a non-standard shape
        // incompatible with apiFetch (which expects an array or {data:[]}), so
        // we use a direct fetch here.
        const response = await fetch(`/api/backend/api/events/symposiums/${symposiumId}`, {
          headers: { "Content-Type": "application/json", ...authHeaders },
        });
        const payload = (await response.json()) as {
          detail?: string;
          symposium?: { id: string; name: string; rooms_available: number; default_buffer?: number };
          timeframes?: TimeframeRecord[];
        };
        if (!response.ok || !payload.symposium) {
          setSymposiumEditMessage(payload.detail ?? "Failed to load selected symposium.");
          return;
        }

        setEditSymposiumName(payload.symposium.name ?? "");
        setEditRooms(String(payload.symposium.rooms_available ?? ""));
        setEditDefaultBuffer(String(payload.symposium.default_buffer ?? "0"));

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
    [authHeaders]
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
    setDepartmentHeadEmail(selectedDepartment.email ?? "");
  }, [departmentAction, departmentToEditId, departments]);

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

    const parsedBuffer = Number.parseInt(createDefaultBuffer, 10);
    if (!Number.isFinite(parsedBuffer) || parsedBuffer < 0) {
      setCreateSaveMessage("Enter a valid default buffer (0 or more minutes).");
      return;
    }

    const timeframes = buildTimeframesFromGrid(createCalendarDates, createAvailability);
    if (!timeframes || timeframes.length === 0) {
      setCreateSaveMessage("Select at least one available time slot.");
      return;
    }

    setIsSavingCreate(true);
    try {
      const { raw } = await apiPost("/api/events/add_symposium", {
        symposium_name: trimmedName,
        rooms_available: parsedRooms,
        default_buffer: parsedBuffer,
        timeframes: timeframes.map(([start_time, end_time]) => ({ start_time, end_time })),
      }, authHeaders);

      setCreateSaveMessage("Event created successfully.");
      await fetchSymposia();
      if (raw.symposium_id) setSelectedSymposiumId(String(raw.symposium_id));
      setActiveTab("edit");
    } catch (error) {
      const message = error instanceof Error ? error.message : "Unknown error";
      setCreateSaveMessage(message);
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

    const parsedBuffer = Number.parseInt(editDefaultBuffer, 10);
    if (!Number.isFinite(parsedBuffer) || parsedBuffer < 0) {
      setSymposiumEditMessage("Enter a valid default buffer (0 or more minutes).");
      return;
    }

    const timeframes = buildTimeframesFromGrid(editCalendarDates, editAvailability);
    if (!timeframes || timeframes.length === 0) {
      setSymposiumEditMessage("Select at least one available time slot.");
      return;
    }

    setIsSavingSymposiumEdit(true);
    try {
      await apiPut("/api/events/update_symposium", {
        symposium_id: selectedSymposiumId,
        symposium_name: trimmedName,
        rooms_available: parsedRooms,
        default_buffer: parsedBuffer,
        timeframes: timeframes.map(([start_time, end_time]) => ({ start_time, end_time })),
      }, authHeaders);

      setSymposiumEditMessage("Event updated successfully.");
      await fetchSymposia();
    } catch (error) {
      const message = error instanceof Error ? error.message : "Unknown error";
      setSymposiumEditMessage(message);
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
      await apiDelete(
        `/api/events/delete_symposium?symposium_id=${encodeURIComponent(selectedSymposiumId)}`,
        authHeaders
      );

      setSymposiumEditMessage("Event deleted.");
      setSelectedSymposiumId("");
      await fetchSymposia();
    } catch (error) {
      const message = error instanceof Error ? error.message : "Unknown error";
      setSymposiumEditMessage(message);
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
        await apiPost("/api/events/add_department", {
          symposium_id: selectedSymposiumId,
          department_name: departmentName.trim(),
          department_head_name: departmentHeadName.trim(),
          email: departmentHeadEmail.trim().toLowerCase(),
        }, authHeaders);

        setDepartmentName("");
        setDepartmentHeadName("");
        setDepartmentHeadEmail("");
        setDepartmentMessage("Department added.");
        setDepartmentMessageKind("success");
      } else if (departmentAction === "edit") {
        await apiPut("/api/events/update_department", {
          department_id: departmentToEditId,
          department_name: departmentName.trim(),
          department_head_name: departmentHeadName.trim(),
          email: departmentHeadEmail.trim().toLowerCase(),
        }, authHeaders);

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
      setDepartmentMessage(message);
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
      await apiDelete(
        `/api/events/delete_department?department_id=${encodeURIComponent(department.id)}`,
        authHeaders
      );

      setDepartmentMessage("Department deleted.");
      setDepartmentMessageKind("success");
      await fetchDepartments(selectedSymposiumId);
    } catch (error) {
      const message = error instanceof Error ? error.message : "Unknown error";
      setDepartmentMessage(message);
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
    setDepartmentHeadEmail(department.email ?? "");
    setDepartmentMessage(null);
    setDepartmentMessageKind(null);
  };

  const handleCreateAdmin = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setAdminMessage(null);
    setAdminMessageKind(null);

    const trimmedEmail = newAdminEmail.trim().toLowerCase();
    if (!trimmedEmail || !/^[^\s@]+@hamilton\.edu$/i.test(trimmedEmail)) {
      setAdminMessage("Enter a valid @hamilton.edu email.");
      setAdminMessageKind("error");
      return;
    }

    if (!newAdminPassword || newAdminPassword.length < 8) {
      setAdminMessage("Password must be at least 8 characters.");
      setAdminMessageKind("error");
      return;
    }

    if (newAdminPassword !== newAdminConfirmPassword) {
      setAdminMessage("Passwords do not match.");
      setAdminMessageKind("error");
      return;
    }

    setIsCreatingAdmin(true);
    try {
      await apiPost("/api/auth/admin/create", {
        email: trimmedEmail,
        password: newAdminPassword,
      }, authHeaders);

      setAdminMessage(`Admin created successfully (${trimmedEmail}).`);
      setAdminMessageKind("success");
      setNewAdminEmail("");
      setNewAdminPassword("");
      setNewAdminConfirmPassword("");
    } catch (error) {
      const message = error instanceof Error ? error.message : "Unknown error";
      setAdminMessage(message);
      setAdminMessageKind("error");
    } finally {
      setIsCreatingAdmin(false);
    }
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
    setDeployEventMessage("Deploy is not connected yet.");
  };

  const resetCreateTabState = () => {
    setCreateSymposiumName("");
    setCreateRooms("");
    setCreateStartDate("");
    setCreateEndDate("");
    setCreateAvailability([]);
    setIsSavingCreate(false);
    setCreateSaveMessage(null);
  };

  const resetEditTabState = () => {
    setSelectedSymposiumId("");
    setEditSymposiumName("");
    setEditRooms("");
    setEditDefaultBuffer("");
    setEditStartDate("");
    setEditEndDate("");
    setEditAvailability([]);
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

  const resetAdminsTabState = () => {
    setNewAdminEmail("");
    setNewAdminPassword("");
    setNewAdminConfirmPassword("");
    setIsCreatingAdmin(false);
    setAdminMessage(null);
    setAdminMessageKind(null);
  };

  const handleTabSwitch = (tab: AdminTab) => {
    setActiveTab(tab);
    if (tab === "create") {
      resetCreateTabState();
      return;
    }
    if (tab === "admins") {
      resetAdminsTabState();
      return;
    }
    if (tab === "schedule") {
      return;
    }
    resetEditTabState();
    void fetchSymposia();
  };

  return (
    <main className="min-h-screen bg-[linear-gradient(180deg,#f7f9ff_0%,#f4f4f4_55%,#f1f1f1_100%)] px-4 py-8">
      <div className="mx-auto w-full max-w-6xl">
        <div className="mb-3 flex justify-end">
          <button
            type="button"
            onClick={onSignOut}
            className="rounded-md border border-[#9ca3af] bg-[#e5e7eb] px-4 py-1.5 text-sm font-semibold text-[#1f2937] transition hover:border-red-500 hover:bg-red-500 hover:text-white"
          >
            Sign Out
          </button>
        </div>
        <header className="mb-5 rounded-2xl border border-[#d8e2ff] bg-white/90 px-5 py-5 shadow-[0_10px_30px_rgba(20,44,120,0.08)] backdrop-blur">
          <h1 className="text-center text-2xl font-extrabold tracking-wide text-black md:text-4xl">
            OCC THESIS SYMPOSIUM - ADMIN
          </h1>
        </header>

        <nav className="mb-4 grid grid-cols-1 gap-3 md:grid-cols-4">
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
              isEditTab
                ? "border-[#0f33a8] bg-[#0f33a8] text-white shadow-[0_8px_20px_rgba(15,51,168,0.25)]"
                : "border-[#c6d2f6] bg-white text-[#111] hover:border-[#0f33a8]"
            }`}
          >
            Edit Existing Event
          </button>
          <button
            type="button"
            onClick={() => handleTabSwitch("schedule")}
            className={`rounded-xl border-2 px-4 py-3 text-lg font-semibold transition md:text-xl ${
              activeTab === "schedule"
                ? "border-[#0f33a8] bg-[#0f33a8] text-white shadow-[0_8px_20px_rgba(15,51,168,0.25)]"
                : "border-[#c6d2f6] bg-white text-[#111] hover:border-[#0f33a8]"
            }`}
          >
            Schedule
          </button>
          <button
            type="button"
            onClick={() => handleTabSwitch("admins")}
            className={`rounded-xl border-2 px-4 py-3 text-lg font-semibold transition md:text-xl ${
              activeTab === "admins"
                ? "border-[#0f33a8] bg-[#0f33a8] text-white shadow-[0_8px_20px_rgba(15,51,168,0.25)]"
                : "border-[#c6d2f6] bg-white text-[#111] hover:border-[#0f33a8]"
            }`}
          >
            Manage Admins
          </button>
        </nav>

        {activeTab === "schedule" ? (
          <section className="rounded-2xl border border-[#d7bf92] bg-white p-4 shadow-[0_16px_30px_rgba(80,60,20,0.08)] md:p-6">
            <h2 className="mb-5 text-xl font-bold text-[#111] md:text-2xl">Schedule Editor</h2>
            <ScheduleTab token={token} />
          </section>
        ) : null}

        {activeTab === "admins" ? (
          <section className="rounded-2xl border border-[#d7bf92] bg-white p-4 shadow-[0_16px_30px_rgba(80,60,20,0.08)] md:p-6">
            <h2 className="mb-5 text-xl font-bold text-[#111] md:text-2xl">Create New Admin</h2>

            <form onSubmit={handleCreateAdmin} className="max-w-md space-y-4">
              <label className="flex flex-col gap-1.5">
                <span className="text-xs font-bold uppercase tracking-wide text-[#2d3d7a] md:text-sm">Email</span>
                <input
                  type="email"
                  className={fieldClass}
                  placeholder="name@hamilton.edu"
                  value={newAdminEmail}
                  onChange={(event) => setNewAdminEmail(event.target.value)}
                  disabled={isCreatingAdmin}
                />
              </label>
              <label className="flex flex-col gap-1.5">
                <span className="text-xs font-bold uppercase tracking-wide text-[#2d3d7a] md:text-sm">Password</span>
                <div className="relative">
                  <input
                    type={showAdminPassword ? "text" : "password"}
                    className={fieldClass + " pr-10"}
                    placeholder="At least 8 characters"
                    value={newAdminPassword}
                    onChange={(event) => setNewAdminPassword(event.target.value)}
                    disabled={isCreatingAdmin}
                  />
                  <button
                    type="button"
                    onClick={() => setShowAdminPassword(!showAdminPassword)}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-[#2d3d7a] hover:text-[#0f33a8]"
                    tabIndex={-1}
                  >
                    {showAdminPassword ? (
                      <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94"/><path d="M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19"/><line x1="1" y1="1" x2="23" y2="23"/></svg>
                    ) : (
                      <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>
                    )}
                  </button>
                </div>
              </label>
              <label className="flex flex-col gap-1.5">
                <span className="text-xs font-bold uppercase tracking-wide text-[#2d3d7a] md:text-sm">Confirm Password</span>
                <div className="relative">
                  <input
                    type={showAdminConfirmPassword ? "text" : "password"}
                    className={fieldClass + " pr-10"}
                    placeholder="Re-enter password"
                    value={newAdminConfirmPassword}
                    onChange={(event) => setNewAdminConfirmPassword(event.target.value)}
                    disabled={isCreatingAdmin}
                  />
                  <button
                    type="button"
                    onClick={() => setShowAdminConfirmPassword(!showAdminConfirmPassword)}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-[#2d3d7a] hover:text-[#0f33a8]"
                    tabIndex={-1}
                  >
                    {showAdminConfirmPassword ? (
                      <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94"/><path d="M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19"/><line x1="1" y1="1" x2="23" y2="23"/></svg>
                    ) : (
                      <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>
                    )}
                  </button>
                </div>
              </label>

              <button
                type="submit"
                disabled={isCreatingAdmin}
                className="rounded-lg bg-[#0f33a8] px-5 py-2.5 text-sm font-semibold text-white shadow-[0_8px_18px_rgba(15,51,168,0.25)] transition hover:bg-[#0b2a8d] disabled:cursor-not-allowed disabled:opacity-60 md:text-base"
              >
                {isCreatingAdmin ? "Creating..." : "Create Admin"}
              </button>

              {adminMessage ? (
                <p
                  className={`text-sm font-semibold ${
                    adminMessageKind === "error" ? "text-[#9a1f1f]" : "text-[#1f5132]"
                  }`}
                >
                  {adminMessage}
                </p>
              ) : null}
            </form>
          </section>
        ) : isCreateTab ? (
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
                  <label className="flex flex-col gap-1.5">
                    <span className="text-xs font-bold uppercase tracking-wide text-[#2d3d7a] md:text-sm">Default Buffer (Minutes)</span>
                    <input
                      type="number"
                      min={0}
                      className={fieldClass}
                      placeholder="Ex. 5"
                      value={createDefaultBuffer}
                      onChange={(event) => setCreateDefaultBuffer(event.target.value)}
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
                            <div className="h-4 overflow-hidden pr-1 text-right text-[11px] leading-4 font-semibold text-[#444]">
                              {slotIndex % 4 === 0 ? formatTimeLabel(slotIndex) : ""}
                            </div>
                            {createCalendarDates.map((date, dayIndex) => {
                              const available = createAvailability[dayIndex]?.[slotIndex] ?? false;
                              const showHourLine = slotIndex % 4 === 0;
                              return (
                                <button
                                  key={`${date.toISOString()}-${slotIndex}`}
                                  type="button"
                                  onMouseDown={() => handleCreateCellMouseDown(dayIndex, slotIndex)}
                                  onMouseEnter={() => handleCreateCellMouseEnter(dayIndex, slotIndex)}
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
        ) : isEditTab ? (
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
                      <label className="flex flex-col gap-1.5">
                        <span className="text-xs font-bold uppercase tracking-wide text-[#2d3d7a] md:text-sm">Default Buffer (Minutes)</span>
                        <input
                          type="number"
                          min={0}
                          className={fieldClass}
                          value={editDefaultBuffer}
                          onChange={(event) => setEditDefaultBuffer(event.target.value)}
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
                                <div className="h-4 overflow-hidden pr-1 text-right text-[11px] leading-4 font-semibold text-[#444]">
                                  {slotIndex % 4 === 0 ? formatTimeLabel(slotIndex) : ""}
                                </div>
                                {editCalendarDates.map((date, dayIndex) => {
                                  const available = editAvailability[dayIndex]?.[slotIndex] ?? false;
                                  const showHourLine = slotIndex % 4 === 0;
                                  return (
                                    <button
                                      key={`${date.toISOString()}-${slotIndex}`}
                                      type="button"
                                      onMouseDown={() => handleEditCellMouseDown(dayIndex, slotIndex)}
                                      onMouseEnter={() => handleEditCellMouseEnter(dayIndex, slotIndex)}
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

                  <div className="mt-3 flex flex-wrap items-center gap-3">
                    <button
                      type="button"
                      onClick={handleDeployEvent}
                      className="rounded-lg bg-[#1b6e2b] px-4 py-2 text-sm font-semibold text-white transition hover:bg-[#155622]"
                    >
                      Deploy
                    </button>
                    {deployEventMessage ? <p className="text-sm font-semibold text-[#222]">{deployEventMessage}</p> : null}
                  </div>

                </div>

              </>
            ) : (
              <div className="mt-5 rounded-xl border border-[#e0e0e0] bg-[#f9f9f9] p-4 text-sm font-semibold text-[#333]">
                Select an existing symposium to edit its event details and manage departments.
              </div>
            )}
          </section>
        ) : null}
      </div>
    </main>
  );
}
