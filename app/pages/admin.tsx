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
  formatCalendarDate,
  dayKey,
  buildCalendarDates,
  buildTimeframesFromGrid,
  gridFromTimeframes,
  toErrorMessage,
  isHamiltonEmail,
} from "../lib/utils";
import { apiFetch, apiPost, apiPut, apiDelete, BACKEND_URL } from "../lib/api";
import { confirmDialog } from "../lib/dialog";
import { useCalendarGrid } from "../lib/useCalendarGrid";
import { useWeekPagination } from "../lib/useWeekPagination";
import ScheduleTab from "./schedule-tab";
import ManageRecordsTab from "./manage-records-tab";
import { AvailabilityGrid } from "../components/AvailabilityGrid";
import { FIELD_CLASS as fieldClass } from "../lib/styles";

function normalizeRoomNames(roomNames: Array<string | null> | null | undefined, roomCount: number): string[] {
  return Array.from({ length: Math.max(0, roomCount) }, (_, index) => roomNames?.[index]?.trim() ?? "");
}

function roomNamesForSave(roomNames: string[], roomCount: number): Array<string | null> {
  const saved = Array.from({ length: Math.max(0, roomCount) }, (_, index) => {
    const name = roomNames[index]?.trim() ?? "";
    return name || null;
  });
  while (saved.length > 0 && saved[saved.length - 1] === null) {
    saved.pop();
  }
  return saved;
}

type AdminEntry = { id: string; email: string; is_superadmin: boolean };

export default function AdminPage({ token, onSignOut, isSuperAdmin, entityId }: { token: string; onSignOut: () => void; isSuperAdmin: boolean; entityId: string }) {
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
  const [editRoomNames, setEditRoomNames] = useState<string[]>([]);
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
  const [emailEventMessage, setEmailEventMessage] = useState<string | null>(null);

  // Manage Admins tab state
  const [newAdminEmail, setNewAdminEmail] = useState("");
  const [newAdminPassword, setNewAdminPassword] = useState("");
  const [newAdminConfirmPassword, setNewAdminConfirmPassword] = useState("");
  const [showAdminPassword, setShowAdminPassword] = useState(false);
  const [showAdminConfirmPassword, setShowAdminConfirmPassword] = useState(false);
  const [isCreatingAdmin, setIsCreatingAdmin] = useState(false);
  const [adminMessage, setAdminMessage] = useState<string | null>(null);
  const [adminMessageKind, setAdminMessageKind] = useState<"success" | "error" | null>(null);

  // Admin list state
  const [adminList, setAdminList] = useState<AdminEntry[]>([]);
  const [isLoadingAdmins, setIsLoadingAdmins] = useState(false);
  const [adminListError, setAdminListError] = useState<string | null>(null);
  const [editingAdminId, setEditingAdminId] = useState<string | null>(null);
  const [editingAdminEmail, setEditingAdminEmail] = useState("");
  const [isSavingAdminEdit, setIsSavingAdminEdit] = useState(false);
  const [adminEditError, setAdminEditError] = useState<string | null>(null);
  const [togglingAdminId, setTogglingAdminId] = useState<string | null>(null);
  const [deletingAdminId, setDeletingAdminId] = useState<string | null>(null);
  const [resetPasswordAdminId, setResetPasswordAdminId] = useState<string | null>(null);
  const [resetPasswordValue, setResetPasswordValue] = useState("");
  const [resetPasswordConfirm, setResetPasswordConfirm] = useState("");
  const [showResetPassword, setShowResetPassword] = useState(false);
  const [showResetPasswordConfirm, setShowResetPasswordConfirm] = useState(false);
  const [isSavingResetPassword, setIsSavingResetPassword] = useState(false);
  const [resetPasswordError, setResetPasswordError] = useState<string | null>(null);

  const isCreateTab = activeTab === "create";
  const isEditTab = activeTab === "edit";
  const isRecordsTab = activeTab === "records";
  const hasSelectedSymposium = Boolean(selectedSymposiumId.trim());

  const createCalendarDates = useMemo(
    () => buildCalendarDates(createStartDate, createEndDate),
    [createStartDate, createEndDate]
  );
  const editCalendarDates = useMemo(() => buildCalendarDates(editStartDate, editEndDate), [editStartDate, editEndDate]);
  const createDateKeys = useMemo(() => createCalendarDates.map((d) => dayKey(d)), [createCalendarDates]);
  const editDateKeys = useMemo(() => editCalendarDates.map((d) => dayKey(d)), [editCalendarDates]);
  const createWeekPagination = useWeekPagination(createDateKeys);
  const editWeekPagination = useWeekPagination(editDateKeys);
  const createCalendarDays = useMemo(
    () => createCalendarDates.map((d) => ({ key: d.toISOString(), label: formatCalendarDate(d) })),
    [createCalendarDates],
  );
  const editCalendarDays = useMemo(
    () => editCalendarDates.map((d) => ({ key: d.toISOString(), label: formatCalendarDate(d) })),
    [editCalendarDates],
  );

  const fetchSymposia = useCallback(async () => {
    setIsLoadingSymposia(true);
    setSymposiumLoadError(null);
    try {
      const rows = await apiFetch<SymposiumOption>("/api/events/symposiums", { headers: authHeaders });
      setSymposiumOptions(rows);
    } catch (error) {
      const message = toErrorMessage(error);
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
        const message = toErrorMessage(error);
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
        setEditRoomNames([]);
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
        const response = await fetch(`${BACKEND_URL}/api/events/symposiums/${symposiumId}`, {
          headers: { "Content-Type": "application/json", ...authHeaders },
        });
        const payload = (await response.json()) as {
          detail?: string;
          symposium?: {
            id: string;
            name: string;
            rooms_available: number;
            room_names?: Array<string | null> | null;
            default_buffer?: number;
          };
          timeframes?: TimeframeRecord[];
        };
        if (!response.ok || !payload.symposium) {
          setSymposiumEditMessage(payload.detail ?? "Failed to load selected symposium.");
          return;
        }

        setEditSymposiumName(payload.symposium.name ?? "");
        const loadedRooms = Number(payload.symposium.rooms_available ?? 0);
        const normalizedLoadedRooms = Number.isFinite(loadedRooms) && loadedRooms > 0 ? Math.floor(loadedRooms) : 0;
        setEditRooms(String(payload.symposium.rooms_available ?? ""));
        setEditRoomNames(normalizeRoomNames(payload.symposium.room_names, normalizedLoadedRooms));
        setEditDefaultBuffer(String(payload.symposium.default_buffer ?? "0"));

        const grid = gridFromTimeframes(payload.timeframes ?? []);
        setEditStartDate(grid.startDate);
        setEditEndDate(grid.endDate);
        setEditAvailability(grid.availability);
      } catch (error) {
        const message = toErrorMessage(error);
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
      const message = toErrorMessage(error);
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
    const roomNames = roomNamesForSave(editRoomNames, parsedRooms);

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
        room_names: roomNames,
        default_buffer: parsedBuffer,
        timeframes: timeframes.map(([start_time, end_time]) => ({ start_time, end_time })),
      }, authHeaders);

      await fetchSymposia();
      await fetchSymposiumDetails(selectedSymposiumId);
      setSymposiumEditMessage("Event updated successfully.");
    } catch (error) {
      const message = toErrorMessage(error);
      setSymposiumEditMessage(message);
    } finally {
      setIsSavingSymposiumEdit(false);
    }
  };

  const handleDeleteEvent = async () => {
    if (!selectedSymposiumId) return;
    const selectedEvent = symposiumOptions.find((option) => option.id === selectedSymposiumId);
    if (!(await confirmDialog(`Delete event "${selectedEvent?.name ?? selectedSymposiumId}"?`, "Delete event"))) return;

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
      const message = toErrorMessage(error);
      setSymposiumEditMessage(message);
    } finally {
      setIsDeletingSymposium(false);
    }
  };

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
      const message = toErrorMessage(error);
      setDepartmentMessage(message);
      setDepartmentMessageKind("error");
    } finally {
      setIsSavingDepartment(false);
    }
  };

  const handleDeleteDepartment = async (department: DepartmentRecord) => {
    const confirmed = await confirmDialog(`Delete department "${department.department_name}"?`, "Delete department");
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
      const message = toErrorMessage(error);
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

  const fetchAdminList = useCallback(async () => {
    setIsLoadingAdmins(true);
    setAdminListError(null);
    try {
      const rows = await apiFetch<AdminEntry>("/api/auth/admin/list", { headers: authHeaders });
      setAdminList(rows);
    } catch (err) {
      setAdminListError(toErrorMessage(err, "Failed to load admins."));
    } finally {
      setIsLoadingAdmins(false);
    }
  }, [authHeaders]);

  const handleCreateAdmin = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setAdminMessage(null);
    setAdminMessageKind(null);

    const trimmedEmail = newAdminEmail.trim().toLowerCase();
    if (!trimmedEmail || !isHamiltonEmail(trimmedEmail)) {
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
      void fetchAdminList();
    } catch (error) {
      const message = toErrorMessage(error);
      setAdminMessage(message);
      setAdminMessageKind("error");
    } finally {
      setIsCreatingAdmin(false);
    }
  };

  const handleUpdateAdminEmail = async (adminId: string) => {
    const trimmed = editingAdminEmail.trim().toLowerCase();
    if (!trimmed || !isHamiltonEmail(trimmed)) {
      setAdminEditError("Enter a valid @hamilton.edu email.");
      return;
    }
    setIsSavingAdminEdit(true);
    setAdminEditError(null);
    try {
      await apiPut(`/api/auth/admin/${adminId}`, { email: trimmed }, authHeaders);
      setAdminList((list) => list.map((a) => a.id === adminId ? { ...a, email: trimmed } : a));
      setEditingAdminId(null);
    } catch (err) {
      setAdminEditError(toErrorMessage(err, "Failed to update email."));
    } finally {
      setIsSavingAdminEdit(false);
    }
  };

  const handleToggleSuperAdmin = async (adminId: string, current: boolean) => {
    setTogglingAdminId(adminId);
    try {
      await apiPut(`/api/auth/admin/${adminId}`, { is_superadmin: !current }, authHeaders);
      setAdminList((list) => list.map((a) => a.id === adminId ? { ...a, is_superadmin: !current } : a));
    } catch (err) {
      setAdminListError(toErrorMessage(err, "Failed to update admin."));
    } finally {
      setTogglingAdminId(null);
    }
  };

  const handleResetPassword = async (adminId: string) => {
    if (resetPasswordValue.length < 8) {
      setResetPasswordError("Password must be at least 8 characters.");
      return;
    }
    if (resetPasswordValue !== resetPasswordConfirm) {
      setResetPasswordError("Passwords do not match.");
      return;
    }
    setIsSavingResetPassword(true);
    setResetPasswordError(null);
    try {
      await apiPut(`/api/auth/admin/${adminId}`, { password: resetPasswordValue }, authHeaders);
      setResetPasswordAdminId(null);
      setResetPasswordValue("");
      setResetPasswordConfirm("");
      setShowResetPassword(false);
      setShowResetPasswordConfirm(false);
    } catch (err) {
      setResetPasswordError(toErrorMessage(err, "Failed to reset password."));
    } finally {
      setIsSavingResetPassword(false);
    }
  };

  const handleDeleteAdmin = async (adminId: string, email: string) => {
    const confirmed = await confirmDialog(`Delete admin ${email}? This cannot be undone.`);
    if (!confirmed) return;
    setDeletingAdminId(adminId);
    try {
      await apiDelete(`/api/auth/admin/${adminId}`, authHeaders);
      setAdminList((list) => list.filter((a) => a.id !== adminId));
    } catch (err) {
      setAdminListError(toErrorMessage(err, "Failed to delete admin."));
    } finally {
      setDeletingAdminId(null);
    }
  };

  const handleEmailEvent = async () => {
    setEmailEventMessage(null);
    if (!selectedSymposiumId) {
      setEmailEventMessage("Select an event first.");
      return;
    }
    if (departments.length === 0) {
      setEmailEventMessage("Add at least one department before sending emails.");
      return;
    }
    try {
      const { raw } = await apiPost("/api/events/email_symposium", { symposium_id: selectedSymposiumId }, authHeaders);
      const count = raw.emails_sent as number;
      setEmailEventMessage(`Emailed ${count} department head${count === 1 ? "" : "s"}.`);
      setDepartments((current) => current.map((d) => ({ ...d, emailed: true })));
    } catch (error) {
      const message = toErrorMessage(error);
      setEmailEventMessage(message);
    }
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
    setEditRoomNames([]);
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
    setEmailEventMessage(null);
  };

  const resetAdminsTabState = () => {
    setNewAdminEmail("");
    setNewAdminPassword("");
    setNewAdminConfirmPassword("");
    setIsCreatingAdmin(false);
    setAdminMessage(null);
    setAdminMessageKind(null);
    setAdminList([]);
    setAdminListError(null);
    setEditingAdminId(null);
    setEditingAdminEmail("");
    setIsSavingAdminEdit(false);
    setAdminEditError(null);
    setTogglingAdminId(null);
    setDeletingAdminId(null);
    setResetPasswordAdminId(null);
    setResetPasswordValue("");
    setResetPasswordConfirm("");
    setShowResetPassword(false);
    setShowResetPasswordConfirm(false);
    setIsSavingResetPassword(false);
    setResetPasswordError(null);
  };

  const handleTabSwitch = (tab: AdminTab) => {
    setActiveTab(tab);
    if (tab === "create") {
      resetCreateTabState();
      return;
    }
    if (tab === "admins") {
      resetAdminsTabState();
      void fetchAdminList();
      return;
    }
    if (tab === "records") {
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

        <nav className={`mb-4 grid grid-cols-1 gap-3 ${isSuperAdmin ? "md:grid-cols-5" : "md:grid-cols-4"}`}>
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
            onClick={() => handleTabSwitch("records")}
            className={`rounded-xl border-2 px-4 py-3 text-lg font-semibold transition md:text-xl ${
              isRecordsTab
                ? "border-[#0f33a8] bg-[#0f33a8] text-white shadow-[0_8px_20px_rgba(15,51,168,0.25)]"
                : "border-[#c6d2f6] bg-white text-[#111] hover:border-[#0f33a8]"
            }`}
          >
            Manage Records
          </button>
          {isSuperAdmin ? (
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
          ) : null}
        </nav>

        {activeTab === "schedule" ? (
          <section className="rounded-2xl border border-[#d7bf92] bg-white p-4 shadow-[0_16px_30px_rgba(80,60,20,0.08)] md:p-6">
            <h2 className="mb-5 text-xl font-bold text-[#111] md:text-2xl">Schedule Editor</h2>
            <ScheduleTab token={token} />
          </section>
        ) : null}

        {isRecordsTab ? (
          <section className="rounded-2xl border border-[#d7bf92] bg-white p-4 shadow-[0_16px_30px_rgba(80,60,20,0.08)] md:p-6">
            <h2 className="mb-5 text-xl font-bold text-[#111] md:text-2xl">Manage Records</h2>
            <ManageRecordsTab token={token} />
          </section>
        ) : null}

        {activeTab === "admins" && isSuperAdmin ? (
          <section className="space-y-6">
            {/* Existing admins list */}
            <div className="rounded-2xl border border-[#d7bf92] bg-white p-4 shadow-[0_16px_30px_rgba(80,60,20,0.08)] md:p-6">
              <h2 className="mb-5 text-xl font-bold text-[#111] md:text-2xl">Manage Admins</h2>

              {isLoadingAdmins ? (
                <p className="text-sm text-[#555]">Loading admins...</p>
              ) : adminListError ? (
                <p className="text-sm font-semibold text-[#9a1f1f]">{adminListError}</p>
              ) : adminList.length === 0 ? (
                <p className="text-sm text-[#555]">No admins found.</p>
              ) : (
                <ul className="divide-y divide-[#e6ecff]">
                  {adminList.map((admin) => {
                    const isEditing = editingAdminId === admin.id;
                    const isToggling = togglingAdminId === admin.id;
                    const isDeleting = deletingAdminId === admin.id;
                    const isResettingPassword = resetPasswordAdminId === admin.id;
                    const isSelf = admin.id === entityId;
                    return (
                      <li key={admin.id} className="flex flex-col gap-2 py-3">
                        <div className="flex items-center gap-4">
                        {/* Email / edit input */}
                        <div className="flex flex-1 items-center gap-2 min-w-0">
                          {isEditing ? (
                            <input
                              type="email"
                              className={fieldClass + " flex-1"}
                              value={editingAdminEmail}
                              onChange={(e) => setEditingAdminEmail(e.target.value)}
                              disabled={isSavingAdminEdit}
                              autoFocus
                            />
                          ) : (
                            <span className="truncate text-sm font-medium text-[#111]">{admin.email}</span>
                          )}
                          {admin.is_superadmin ? (
                            <span className="shrink-0 rounded-full bg-[#0f33a8] px-2 py-0.5 text-xs font-bold text-white">Super Admin</span>
                          ) : null}
                          {isSelf ? (
                            <span className="shrink-0 rounded-full border border-[#c6d2f6] px-2 py-0.5 text-xs font-semibold text-[#2d3d7a]">You</span>
                          ) : null}
                        </div>

                        {/* Action buttons */}
                        <div className="flex shrink-0 items-center gap-2">
                          {isEditing ? (
                            <>
                              <button
                                type="button"
                                onClick={() => handleUpdateAdminEmail(admin.id)}
                                disabled={isSavingAdminEdit}
                                className="rounded-md bg-[#0f33a8] px-3 py-1.5 text-xs font-semibold text-white transition hover:bg-[#0b2a8d] disabled:opacity-60"
                              >
                                {isSavingAdminEdit ? "Saving..." : "Save"}
                              </button>
                              <button
                                type="button"
                                onClick={() => { setEditingAdminId(null); setAdminEditError(null); }}
                                disabled={isSavingAdminEdit}
                                className="rounded-md border border-[#c6d2f6] px-3 py-1.5 text-xs font-semibold text-[#111] transition hover:border-[#0f33a8] disabled:opacity-60"
                              >
                                Cancel
                              </button>
                            </>
                          ) : (
                            <button
                              type="button"
                              onClick={() => { setEditingAdminId(admin.id); setEditingAdminEmail(admin.email); setAdminEditError(null); }}
                              disabled={!!editingAdminId || isToggling || isDeleting}
                              className="rounded-md border border-[#c6d2f6] px-3 py-1.5 text-xs font-semibold text-[#111] transition hover:border-[#0f33a8] disabled:opacity-40"
                            >
                              Edit Email
                            </button>
                          )}

                          <button
                            type="button"
                            onClick={() => handleToggleSuperAdmin(admin.id, admin.is_superadmin)}
                            disabled={isToggling || isDeleting || !!editingAdminId || (isSelf && admin.is_superadmin)}
                            title={isSelf && admin.is_superadmin ? "Cannot remove your own super admin status" : undefined}
                            className={`rounded-md px-3 py-1.5 text-xs font-semibold transition disabled:opacity-40 ${
                              admin.is_superadmin
                                ? "border border-[#c6d2f6] text-[#111] hover:border-[#9a1f1f] hover:text-[#9a1f1f]"
                                : "border border-[#0f33a8] text-[#0f33a8] hover:bg-[#0f33a8] hover:text-white"
                            }`}
                          >
                            {isToggling ? "..." : admin.is_superadmin ? "Demote" : "Promote"}
                          </button>

                          <button
                            type="button"
                            onClick={() => {
                              setResetPasswordAdminId(isResettingPassword ? null : admin.id);
                              setResetPasswordValue("");
                              setResetPasswordConfirm("");
                              setShowResetPassword(false);
                              setShowResetPasswordConfirm(false);
                              setResetPasswordError(null);
                            }}
                            disabled={isDeleting || isToggling || !!editingAdminId}
                            className={`rounded-md px-3 py-1.5 text-xs font-semibold transition disabled:opacity-40 ${isResettingPassword ? "border border-[#c6d2f6] text-[#111] hover:border-[#0f33a8]" : "border border-[#c6d2f6] text-[#111] hover:border-[#0f33a8]"}`}
                          >
                            {isResettingPassword ? "Cancel" : "Reset Password"}
                          </button>

                          <button
                            type="button"
                            onClick={() => handleDeleteAdmin(admin.id, admin.email)}
                            disabled={isDeleting || isToggling || !!editingAdminId || isSelf}
                            title={isSelf ? "Cannot delete your own account" : undefined}
                            className="rounded-md border border-[#c6d2f6] px-3 py-1.5 text-xs font-semibold text-[#9a1f1f] transition hover:border-[#9a1f1f] hover:bg-[#9a1f1f] hover:text-white disabled:opacity-40"
                          >
                            {isDeleting ? "Deleting..." : "Delete"}
                          </button>
                        </div>
                        </div>{/* end main row */}

                        {/* Inline edit error */}
                        {isEditing && adminEditError ? (
                          <p className="text-xs font-semibold text-[#9a1f1f]">{adminEditError}</p>
                        ) : null}

                        {/* Inline password reset form */}
                        {isResettingPassword ? (
                          <div className="w-full rounded-xl border border-[#e6ecff] bg-[#fdfdff] p-3 sm:col-span-2">
                            <p className="mb-2 text-xs font-bold uppercase tracking-wide text-[#2d3d7a]">New Password for {admin.email}</p>
                            <div className="flex flex-col gap-2 sm:flex-row sm:items-start">
                              <div className="relative flex-1">
                                <input
                                  type={showResetPassword ? "text" : "password"}
                                  className={fieldClass + " pr-10 text-sm"}
                                  placeholder="New password (min 8 chars)"
                                  value={resetPasswordValue}
                                  onChange={(e) => setResetPasswordValue(e.target.value)}
                                  disabled={isSavingResetPassword}
                                  autoFocus
                                />
                                <button type="button" onClick={() => setShowResetPassword((v) => !v)} className="absolute right-3 top-1/2 -translate-y-1/2 text-[#2d3d7a] hover:text-[#0f33a8]" tabIndex={-1}>
                                  {showResetPassword ? <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94"/><path d="M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19"/><line x1="1" y1="1" x2="23" y2="23"/></svg> : <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>}
                                </button>
                              </div>
                              <div className="relative flex-1">
                                <input
                                  type={showResetPasswordConfirm ? "text" : "password"}
                                  className={fieldClass + " pr-10 text-sm"}
                                  placeholder="Confirm new password"
                                  value={resetPasswordConfirm}
                                  onChange={(e) => setResetPasswordConfirm(e.target.value)}
                                  disabled={isSavingResetPassword}
                                />
                                <button type="button" onClick={() => setShowResetPasswordConfirm((v) => !v)} className="absolute right-3 top-1/2 -translate-y-1/2 text-[#2d3d7a] hover:text-[#0f33a8]" tabIndex={-1}>
                                  {showResetPasswordConfirm ? <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94"/><path d="M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19"/><line x1="1" y1="1" x2="23" y2="23"/></svg> : <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>}
                                </button>
                              </div>
                              <button
                                type="button"
                                onClick={() => handleResetPassword(admin.id)}
                                disabled={isSavingResetPassword}
                                className="rounded-md bg-[#0f33a8] px-4 py-2 text-xs font-semibold text-white transition hover:bg-[#0b2a8d] disabled:opacity-60"
                              >
                                {isSavingResetPassword ? "Saving..." : "Save"}
                              </button>
                            </div>
                            {resetPasswordError ? (
                              <p className="mt-1.5 text-xs font-semibold text-[#9a1f1f]">{resetPasswordError}</p>
                            ) : null}
                          </div>
                        ) : null}
                      </li>
                    );
                  })}
                </ul>
              )}
            </div>

            {/* Create new admin */}
            <div className="rounded-2xl border border-[#d7bf92] bg-white p-4 shadow-[0_16px_30px_rgba(80,60,20,0.08)] md:p-6">
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
                  <p className={`text-sm font-semibold ${adminMessageKind === "error" ? "text-[#9a1f1f]" : "text-[#1f5132]"}`}>
                    {adminMessage}
                  </p>
                ) : null}
              </form>
            </div>
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
                {createWeekPagination.hasMultipleWeeks && (
                  <div className="mb-3 flex items-center gap-3">
                    <button type="button" onClick={createWeekPagination.prevWeek} disabled={!createWeekPagination.hasPrev} className="rounded-lg border border-[#c7c7c7] bg-white px-3 py-1 text-sm font-semibold text-[#333] transition hover:bg-[#f5f5f5] disabled:cursor-not-allowed disabled:opacity-40" aria-label="Previous week">&larr;</button>
                    <span className="text-sm font-semibold text-[#333]">Week {createWeekPagination.weekNumber} of {createWeekPagination.totalWeeks}: {createWeekPagination.weekLabel}</span>
                    <button type="button" onClick={createWeekPagination.nextWeek} disabled={!createWeekPagination.hasNext} className="rounded-lg border border-[#c7c7c7] bg-white px-3 py-1 text-sm font-semibold text-[#333] transition hover:bg-[#f5f5f5] disabled:cursor-not-allowed disabled:opacity-40" aria-label="Next week">&rarr;</button>
                  </div>
                )}
                <div className="w-full overflow-x-auto rounded-xl border border-[#cfcfcf] bg-white p-2">
                  {createCalendarDates.length === 0 ? (
                    <div className="px-2 py-4 text-sm font-semibold text-[#555]">Select start and end dates first.</div>
                  ) : (
                    <AvailabilityGrid
                      calendarDays={createCalendarDays}
                      availability={createAvailability}
                      weekPagination={createWeekPagination}
                      handleCellMouseDown={handleCreateCellMouseDown}
                      handleCellMouseEnter={handleCreateCellMouseEnter}
                      cellSize="sm"
                      minWidthPx={760}
                      dayHeaderClassName="text-base"
                      dayHeaderCellClassName=""
                    />
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
                          onChange={(event) => {
                            const nextValue = event.target.value;
                            setEditRooms(nextValue);
                            const nextCount = Number.parseInt(nextValue, 10);
                            if (Number.isFinite(nextCount) && nextCount > 0) {
                              setEditRoomNames((current) => normalizeRoomNames(current, nextCount));
                            }
                          }}
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

                    <div className="mt-5">
                      <h4 className="text-sm font-bold uppercase tracking-wide text-[#2d3d7a]">Room Names</h4>
                      <p className="mt-1 text-sm text-[#555]">
                        Leave a room blank to keep its default label.
                      </p>
                      <div className="mt-3 grid grid-cols-1 gap-3 md:grid-cols-2">
                        {editRoomNames.length === 0 ? (
                          <p className="text-sm font-semibold text-[#555]">Enter the number of rooms first.</p>
                        ) : (
                          editRoomNames.map((roomName, index) => (
                            <label key={index} className="flex flex-col gap-1.5">
                              <span className="text-xs font-bold uppercase tracking-wide text-[#2d3d7a] md:text-sm">
                                Room {index + 1}
                              </span>
                              <input
                                className={fieldClass}
                                placeholder={`Ex. KJ ${101 + index}`}
                                value={roomName}
                                onChange={(event) => {
                                  const nextName = event.target.value;
                                  setEditRoomNames((current) => {
                                    const next = normalizeRoomNames(current, current.length);
                                    next[index] = nextName;
                                    return next;
                                  });
                                }}
                                disabled={isLoadingSymposiumDetails}
                              />
                            </label>
                          ))
                        )}
                      </div>
                    </div>
                  </div>

                  <aside className="rounded-xl border border-[#d7bf92] bg-[#fffdf8] p-4 md:p-5">
                    <p className="mb-3 text-sm font-semibold text-[#444]">Click and drag to edit event availability.</p>
                    {editWeekPagination.hasMultipleWeeks && (
                      <div className="mb-3 flex items-center gap-3">
                        <button type="button" onClick={editWeekPagination.prevWeek} disabled={!editWeekPagination.hasPrev} className="rounded-lg border border-[#c7c7c7] bg-white px-3 py-1 text-sm font-semibold text-[#333] transition hover:bg-[#f5f5f5] disabled:cursor-not-allowed disabled:opacity-40" aria-label="Previous week">&larr;</button>
                        <span className="text-sm font-semibold text-[#333]">Week {editWeekPagination.weekNumber} of {editWeekPagination.totalWeeks}: {editWeekPagination.weekLabel}</span>
                        <button type="button" onClick={editWeekPagination.nextWeek} disabled={!editWeekPagination.hasNext} className="rounded-lg border border-[#c7c7c7] bg-white px-3 py-1 text-sm font-semibold text-[#333] transition hover:bg-[#f5f5f5] disabled:cursor-not-allowed disabled:opacity-40" aria-label="Next week">&rarr;</button>
                      </div>
                    )}
                    <div className="w-full overflow-x-auto rounded-xl border border-[#cfcfcf] bg-white p-2">
                      {editCalendarDates.length === 0 ? (
                        <div className="px-2 py-4 text-sm font-semibold text-[#555]">Select start and end dates first.</div>
                      ) : (
                        <AvailabilityGrid
                          calendarDays={editCalendarDays}
                          availability={editAvailability}
                          weekPagination={editWeekPagination}
                          handleCellMouseDown={handleEditCellMouseDown}
                          handleCellMouseEnter={handleEditCellMouseEnter}
                          cellSize="sm"
                          minWidthPx={760}
                          dayHeaderClassName="text-base"
                          dayHeaderCellClassName=""
                        />
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
                                <p className="flex items-center gap-2 text-xs text-[#555]">
                                  <span>{department.department_head_name} ({department.email})</span>
                                  {department.emailed ? (
                                    <span className="rounded-full bg-[#e6f4ea] px-2 py-0.5 text-xs font-semibold text-[#1b6e2b]">Emailed</span>
                                  ) : null}
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

                  <div className="mt-4">
                    <button
                      type="button"
                      onClick={handleEmailEvent}
                      className="rounded-lg bg-[#1b6e2b] px-4 py-2 text-sm font-semibold text-white shadow-[0_8px_18px_rgba(27,110,43,0.25)] transition hover:bg-[#155622]"
                    >
                      Send Emails
                    </button>
                    {emailEventMessage ? <p className="mt-2 text-sm font-semibold text-[#222]">{emailEventMessage}</p> : null}
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
