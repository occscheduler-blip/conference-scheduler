"use client";

import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import type {
  CalendarDay,
  FacultyTab,
  PresentationGroup,
  ProfessorOption,
  UploadedStudent,
} from "./types";
import {
  totalSlots,
  normalizeId,
  parseCsvLine,
  isUuid,
  buildCalendarFromTimeframes,
  toBackendDateTime,
  toErrorMessage,
} from "../lib/utils";
import { apiFetch, apiPost, apiPut, apiDelete } from "../lib/api";
import { confirmDialog } from "../lib/dialog";
import { useCalendarGrid } from "../lib/useCalendarGrid";
import { useWeekPagination } from "../lib/useWeekPagination";
import { AvailabilityGrid } from "../components/AvailabilityGrid";

// Renders the professor page and manages its data and interactions.
function ProfessorPageContent({ token, onSignOut, entityId }: { token: string; onSignOut: () => void; entityId: string }) {
  const [activeTab, setActiveTab] = useState<FacultyTab>("availability");
  const [professorOptions, setProfessorOptions] = useState<ProfessorOption[]>([]);
  const [selectedProfessorId, setSelectedProfessorId] = useState<string>("");
  const [loadingProfessors, setLoadingProfessors] = useState(false);
  const [editableSlots, setEditableSlots] = useState<boolean[][]>([]);
  const [calendarDays, setCalendarDays] = useState<CalendarDay[]>([]);
  const [calendarMessage, setCalendarMessage] = useState<string>("");
  const { availability, setAvailability, handleCellMouseDown, handleCellMouseEnter } = useCalendarGrid(calendarDays.length, editableSlots);
  const weekPagination = useWeekPagination(calendarDays.map((d) => d.key));
  const [availabilityMessage, setAvailabilityMessage] = useState<string>("");
  const [savingAvailability, setSavingAvailability] = useState(false);
  const [csvFile, setCsvFile] = useState<File | null>(null);
  const [csvUploading, setCsvUploading] = useState(false);
  const [csvMessage, setCsvMessage] = useState<string | null>(null);
  const [deletingStudentIds, setDeletingStudentIds] = useState<string[]>([]);
  const [showManualStudentEntry, setShowManualStudentEntry] = useState(false);
  const [manualStudentName, setManualStudentName] = useState("");
  const [manualStudentEmail, setManualStudentEmail] = useState("");
  const [manualStudentSubmitting, setManualStudentSubmitting] = useState(false);
  const [manualStudentMessage, setManualStudentMessage] = useState<string | null>(null);
  const csvInputRef = useRef<HTMLInputElement | null>(null);
  const [uploadedStudents, setUploadedStudents] = useState<UploadedStudent[]>([]);
  const [selectedUploadedStudentKeys, setSelectedUploadedStudentKeys] = useState<string[]>([]);
  const [presentationGroups, setPresentationGroups] = useState<PresentationGroup[]>([]);
  const [deployedPresentationGroups, setDeployedPresentationGroups] = useState<PresentationGroup[]>([]);
  const [groupMessage, setGroupMessage] = useState<string>("");
  const [emailMessage, setEmailMessage] = useState<string>("");
  const [emailingPresentations, setDeployingPresentations] = useState<boolean>(false);
  const [deletingPresentationGroupIds, setDeletingPresentationGroupIds] = useState<string[]>([]);
  const [editingDeployedPresentationId, setEditingDeployedPresentationId] = useState<string | null>(null);
  const [editingPresentationName, setEditingPresentationName] = useState<string>("");
  const [editingPresentationDuration, setEditingPresentationDuration] = useState<string>("");
  const [editingPresentationBuffer, setEditingPresentationBuffer] = useState<string>("");
  const [savingEditedPresentationId, setSavingEditedPresentationId] = useState<string | null>(null);
  const [defaultPresentationDuration, setDefaultPresentationDuration] = useState<string>("");
  const [usePerPresentationDuration, setUsePerPresentationDuration] = useState<boolean>(false);
  const [defaultBufferDuration, setDefaultBufferDuration] = useState<string>("");
  const [usePerBufferDuration, setUsePerBufferDuration] = useState<boolean>(false);
  const [professorName, setProfessorName] = useState<string>("");
  const [classId, setClassId] = useState<string>("");
  const [className, setClassName] = useState<string>("");
  const [symposiumName, setSymposiumName] = useState<string>("");
  const [loadingIdentity, setLoadingIdentity] = useState(false);
  const [identityMessage, setIdentityMessage] = useState<string>("");

  const isAvailabilityTab = activeTab === "availability";
  const hasSelectedProfessor = Boolean(selectedProfessorId);
  const identityReady = hasSelectedProfessor && !loadingIdentity && Boolean(professorName);
  const pageLocked = !hasSelectedProfessor || (!loadingIdentity && !professorName);
  const authHeaders = useMemo(() => ({ Authorization: `Bearer ${token}` }), [token]);

  // AI template: fetches and normalizes student names for a class, with URL fallback logic.
  // Loads the students for a class from the backend.
  const fetchClassStudentNames = useCallback(
    async (targetClassId: string) => {
      if (!targetClassId) return [] as UploadedStudent[];
      const rows = await apiFetch<{ id?: string; name?: string }>(
        `/api/events/students?class_id=${encodeURIComponent(targetClassId)}`,
        { headers: authHeaders, cache: "no-store" }
      );
      return rows
        .map((row, index) => ({
          id: row.id ?? `row-${index}`,
          name: (row.name ?? "").trim(),
        }))
        .filter((row) => row.name.length > 0);
    },
    [authHeaders]
  );

  useEffect(() => {
    let ignore = false;

    // Loads professor options and selects a valid default.
    const loadProfessorOptions = async () => {
      setLoadingProfessors(true);
      setIdentityMessage("");
      try {
        const professorRows = await apiFetch<{ id?: string; name?: string; class_id?: string }>(
          "/api/events/professors", { headers: authHeaders, cache: "no-store" }
        );
        const nextProfessorOptions = professorRows
          .filter((row) => row.id)
          .map((row) => ({
            id: row.id as string,
            name: row.name?.trim() || (row.id as string),
            classId: row.class_id ?? "",
          }));

        if (ignore) return;
        setProfessorOptions(nextProfessorOptions);
        setSelectedProfessorId((current) => {
          if (current && nextProfessorOptions.some((professor) => professor.id === current)) return current;
          if (entityId && nextProfessorOptions.some((professor) => professor.id === entityId)) return entityId;
          return nextProfessorOptions[0]?.id ?? "";
        });
        if (nextProfessorOptions.length === 0) {
          setIdentityMessage("No professors found.");
        }
      } catch (error) {
        if (ignore) return;
        const message = toErrorMessage(error);
        setIdentityMessage(message);
        setProfessorOptions([]);
        setSelectedProfessorId("");
      } finally {
        if (!ignore) setLoadingProfessors(false);
      }
    };

    void loadProfessorOptions();
    return () => {
      ignore = true;
    };
  }, [authHeaders]);

  useEffect(() => {
    if (!selectedProfessorId) {
      setProfessorName("");
      setClassId("");
      setClassName("");
      setSymposiumName("");
      if (!loadingProfessors) {
        setIdentityMessage((current) => (current ? current : "Select a professor to load data."));
      }
      setEditableSlots([]);
      setCalendarDays([]);
      setCalendarMessage("");
      return;
    }

    let ignore = false;
    // AI template: loads identity, resolves the class/symposium chain, maps timeframes to calendar slots, loads uploaded students, and fetches deployed presentations.
    const loadIdentity = async () => {
      setLoadingIdentity(true);
      setIdentityMessage("");
      setCalendarMessage("");
      try {
        const [classRows, departmentRows, symposiumRows] = await Promise.all([
          apiFetch<{ id?: string; name?: string; department_id?: string }>("/api/events/classes", { headers: authHeaders }),
          apiFetch<{ id?: string; symposium_id?: string }>("/api/events/departments", { headers: authHeaders }),
          apiFetch<{ id?: string; name?: string; symposium_name?: string }>("/api/events/symposiums", { headers: authHeaders }),
        ]);
        const professor = professorOptions.find((row) => row.id === selectedProfessorId);
        if (!professor) {
          throw new Error("Select a professor to load data.");
        }

        const resolvedClassId = professor.classId ?? "";
        const matchedClass = classRows.find((row) => row.id === resolvedClassId);
        const matchedDepartment = departmentRows.find((row) => row.id === matchedClass?.department_id);
        const symposiumId = matchedDepartment?.symposium_id ?? "";
        const matchedSymposium = symposiumRows.find((row) => row.id === symposiumId);
        const existingStudents = resolvedClassId ? await fetchClassStudentNames(resolvedClassId) : [];
        const studentById = new Map(existingStudents.map((student) => [normalizeId(student.id), student]));

        let existingGroups: PresentationGroup[] = [];
        if (resolvedClassId) {
          const presentationRows = await apiFetch<{
            id?: string;
            title?: string;
            minutes?: number;
            buffer?: number;
            presenting_students?: Array<{ id?: string; student_id?: string; studentId?: string }>;
          }>(`/api/events/presentations?class_id=${encodeURIComponent(resolvedClassId)}`, { headers: authHeaders });
          const groups: PresentationGroup[] = [];

          for (const presentation of presentationRows) {
            const presentationId = presentation.id ?? "";
            if (!presentationId) continue;

            const presentingRows = presentation.presenting_students ?? [];
            const studentIds = presentingRows
              .map((row) => row.id ?? row.student_id ?? row.studentId ?? "")
              .map((id) => normalizeId(id))
              .filter((id) => id.length > 0);
            const studentNames = studentIds
              .map((studentId) => studentById.get(studentId)?.name)
              .filter((name): name is string => Boolean(name && name.trim().length > 0));

            groups.push({
              id: presentationId,
              studentIds,
              studentNames,
              presentationName: presentation.title ?? "",
              durationMinutes:
                typeof presentation.minutes === "number" ? String(presentation.minutes) : "",
              bufferMinutes:
                typeof presentation.buffer === "number" ? String(presentation.buffer) : "",
            });
          }
          existingGroups = groups;
        }

        let nextCalendarDays: CalendarDay[] = [];
        let nextEditableSlots: boolean[][] = [];
        let nextAvailability: boolean[][] = [];
        if (symposiumId) {
          const symposiumTimeframeRows = await apiFetch<{ start_time?: string; end_time?: string }>(
            `/api/events/timeframes?linked_id=${encodeURIComponent(symposiumId)}`, { headers: authHeaders }
          );
          const professorTimeframeRows = await apiFetch<{ start_time?: string; end_time?: string }>(
            `/api/events/timeframes?linked_id=${encodeURIComponent(selectedProfessorId)}`, { headers: authHeaders }
          );

          ({ calendarDays: nextCalendarDays, editableSlots: nextEditableSlots, availability: nextAvailability } =
            buildCalendarFromTimeframes(symposiumTimeframeRows, professorTimeframeRows));
        }

        if (ignore) return;
        setEditableSlots(nextEditableSlots);
        setAvailability(nextAvailability);
        setProfessorName(professor.name || "Professor");
        setClassId(resolvedClassId);
        setClassName(matchedClass?.name ?? "");
        setSymposiumName(matchedSymposium?.name ?? matchedSymposium?.symposium_name ?? "");
        const groupedStudentIds = new Set(existingGroups.flatMap((group) => group.studentIds));
        setUploadedStudents(existingStudents.filter((student) => !groupedStudentIds.has(normalizeId(student.id))));
        setSelectedUploadedStudentKeys([]);
        setPresentationGroups([]);
        setDeployedPresentationGroups(existingGroups);
        const uniqueDurations = Array.from(
          new Set(
            existingGroups
              .map((group) => group.durationMinutes.trim())
              .filter((value) => value.length > 0)
          )
        );
        if (uniqueDurations.length === 1) {
          setDefaultPresentationDuration(uniqueDurations[0]);
        } else {
          setDefaultPresentationDuration("");
        }
        setUsePerPresentationDuration(false);
        const uniqueBuffers = Array.from(
          new Set(
            existingGroups
              .map((group) => group.bufferMinutes.trim())
              .filter((value) => value.length > 0)
          )
        );
        if (uniqueBuffers.length === 1) {
          setDefaultBufferDuration(uniqueBuffers[0]);
        } else {
          setDefaultBufferDuration("");
        }
        setUsePerBufferDuration(false);
        setGroupMessage("");
        setCalendarDays(nextCalendarDays);
        setCalendarMessage(nextCalendarDays.length === 0 ? "No symposium dates are configured yet." : "");
      } catch (error) {
        if (ignore) return;
        const message = toErrorMessage(error);
        setIdentityMessage(message);
        setSymposiumName("");
        setUploadedStudents([]);
        setSelectedUploadedStudentKeys([]);
        setPresentationGroups([]);
        setDeployedPresentationGroups([]);
        setUsePerPresentationDuration(false);
        setDefaultPresentationDuration("");
        setGroupMessage("");
        setEditableSlots([]);
        setCalendarDays([]);
        setAvailability([]);
      } finally {
        if (!ignore) setLoadingIdentity(false);
      }
    };

    void loadIdentity();
    return () => {
      ignore = true;
    };
  }, [authHeaders, fetchClassStudentNames, loadingProfessors, professorOptions, selectedProfessorId]);

  // Saves selected availability slots to backend timeframes.
  const handleSaveAvailability = async () => {
    setAvailabilityMessage("");
    if (!selectedProfessorId) {
      setAvailabilityMessage("Select a professor first.");
      return;
    }
    if (calendarDays.length === 0) {
      setAvailabilityMessage("No symposium dates are configured yet.");
      return;
    }

    const timeframes: Array<{ start_time: string; end_time: string }> = [];
    for (let dayIndex = 0; dayIndex < calendarDays.length; dayIndex += 1) {
      const day = calendarDays[dayIndex];
      const [year, month, dayOfMonth] = day.key.split("-").map((part) => Number.parseInt(part, 10));
      if (!year || !month || !dayOfMonth) continue;

      let rangeStart: Date | null = null;
      let rangeEnd: Date | null = null;

      for (let slotIndex = 0; slotIndex < totalSlots; slotIndex += 1) {
        const editable = editableSlots[dayIndex]?.[slotIndex] ?? false;
        const available = availability[dayIndex]?.[slotIndex] ?? false;

        if (editable && available) {
          const slotStart = new Date(Date.UTC(year, month - 1, dayOfMonth, 9, 0, 0, 0));
          slotStart.setUTCMinutes(slotStart.getUTCMinutes() + slotIndex * 15);
          const slotEnd = new Date(slotStart);
          slotEnd.setUTCMinutes(slotEnd.getUTCMinutes() + 15);

          if (!rangeStart) {
            rangeStart = slotStart;
            rangeEnd = slotEnd;
          } else {
            rangeEnd = slotEnd;
          }
        } else if (rangeStart && rangeEnd) {
          timeframes.push({ start_time: toBackendDateTime(rangeStart), end_time: toBackendDateTime(rangeEnd) });
          rangeStart = null;
          rangeEnd = null;
        }
      }

      if (rangeStart && rangeEnd) {
        timeframes.push({ start_time: toBackendDateTime(rangeStart), end_time: toBackendDateTime(rangeEnd) });
      }
    }

    setSavingAvailability(true);
    try {
      await apiPut("/api/events/update_timeframes", {
        linked_id: selectedProfessorId,
        timeframes,
      }, authHeaders);
      setAvailabilityMessage(`Saved ${timeframes.length} availability slot${timeframes.length === 1 ? "" : "s"}.`);
    } catch (error) {
      const message = toErrorMessage(error);
      setAvailabilityMessage(`Save failed: ${message}`);
    } finally {
      setSavingAvailability(false);
    }
  };

  // AI template: parses a CSV file and uploads each student row to the backend for the current class.
  // Parses and uploads a CSV file of students for this class.
  async function handleCsvUpload(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!classId) {
      setCsvMessage("No class is linked to the selected professor.");
      return;
    }
    if (!csvFile) {
      setCsvMessage("Select a CSV file before uploading.");
      return;
    }

    setCsvUploading(true);
    setCsvMessage("Uploading CSV...");

    try {
      const raw = await csvFile.text();
      const lines = raw
        .replace(/\r\n/g, "\n")
        .replace(/\r/g, "\n")
        .split("\n")
        .filter((line) => line.trim().length > 0);

      if (lines.length < 2) {
        setCsvMessage("CSV must include a header row and at least one student row.");
        return;
      }

      const headers = parseCsvLine(lines[0]).map((header) => header.trim());
      const requiredHeaders = ["Student Name", "Student ID", "Class Level", "Preferred Email"];
      const missingHeaders = requiredHeaders.filter((header) => !headers.includes(header));
      if (missingHeaders.length > 0) {
        setCsvMessage(`CSV is missing required columns: ${missingHeaders.join(", ")}`);
        return;
      }

      const studentNameIndex = headers.indexOf("Student Name");
      const preferredEmailIndex = headers.indexOf("Preferred Email");
      const students = lines
        .slice(1)
        .map((line) => parseCsvLine(line))
        .map((cells) => ({
          name: (cells[studentNameIndex] ?? "").trim(),
          email: (cells[preferredEmailIndex] ?? "").trim().toLowerCase(),
        }))
        .filter((row) => row.name.length > 0 && row.email.length > 0);

      if (students.length === 0) {
        setCsvMessage("No valid student rows found. Ensure Student Name and Preferred Email are filled.");
        return;
      }

      const { raw: payload } = await apiPost<Record<string, unknown>>("/api/events/add_students", {
        class_id: classId,
        students,
      }, authHeaders);

      const inserted = (payload.records_inserted as { students?: number })?.students ?? students.length;
      const skipped = Math.max(0, lines.length - 1 - students.length);
      setCsvMessage(`Upload successful: inserted ${inserted} student${inserted === 1 ? "" : "s"}${skipped > 0 ? `, skipped ${skipped}` : ""}.`);
      const refreshedStudents = await fetchClassStudentNames(classId);
      const mergedStudents = [...refreshedStudents];
      const seen = new Set(mergedStudents.map((student) => student.name.trim().toLowerCase()));
      for (const student of students) {
        const nameKey = student.name.trim().toLowerCase();
        if (!nameKey || seen.has(nameKey)) continue;
        seen.add(nameKey);
        mergedStudents.push({
          id: `temp-${Date.now()}-${Math.random().toString(16).slice(2)}`,
          name: student.name.trim(),
        });
      }
      setUploadedStudents(mergedStudents);
      setSelectedUploadedStudentKeys([]);
      setGroupMessage("");
      setCsvFile(null);
      if (csvInputRef.current) csvInputRef.current.value = "";
    } catch (error) {
      const message = toErrorMessage(error);
      if (message.toLowerCase().includes("load failed") || message.toLowerCase().includes("failed to fetch")) {
        setCsvMessage("CSV upload failed: backend is unreachable at http://localhost:8000.");
      } else {
        setCsvMessage(`CSV upload failed: ${message}`);
      }
    } finally {
      setCsvUploading(false);
    }
  }

  // Adds one student manually to the selected class.
  const handleManualStudentAdd = async () => {
    setManualStudentMessage(null);
    if (!classId) {
      setManualStudentMessage("No class is linked to the selected professor.");
      return;
    }

    const name = manualStudentName.trim();
    const email = manualStudentEmail.trim().toLowerCase();
    if (!name) {
      setManualStudentMessage("Enter a student name.");
      return;
    }
    if (!email) {
      setManualStudentMessage("Enter a student email.");
      return;
    }

    setManualStudentSubmitting(true);
    try {
      await apiPost("/api/events/add_students", {
        class_id: classId,
        students: [{ name, email }],
      }, authHeaders);

      const refreshedStudents = await fetchClassStudentNames(classId);
      setUploadedStudents(refreshedStudents);
      setManualStudentName("");
      setManualStudentEmail("");
      setManualStudentMessage(`Added ${name}.`);
    } catch (error) {
      const message = toErrorMessage(error);
      setManualStudentMessage(`Add failed: ${message}`);
    } finally {
      setManualStudentSubmitting(false);
    }
  };

  // Toggles whether a student is selected for grouping.
  const toggleUploadedStudent = (studentKey: string) => {
    setSelectedUploadedStudentKeys((current) =>
      current.includes(studentKey) ? current.filter((key) => key !== studentKey) : [...current, studentKey]
    );
  };

  // Deletes a student after confirmation and updates the local list.
  const deleteUploadedStudent = async (studentId: string, studentName: string) => {
    const confirmed = await confirmDialog(`Delete ${studentName}?`, "Delete student");
    if (!confirmed) return;
    const previousStudents = uploadedStudents;
    const previousSelectedKeys = selectedUploadedStudentKeys;
    // Optimistic UI update: remove immediately so the student disappears on click.
    setUploadedStudents((current) => current.filter((student) => student.id !== studentId));
    setSelectedUploadedStudentKeys((current) => current.filter((key) => key !== studentId));
    setDeletingStudentIds((current) => [...current, studentId]);
    try {
      await apiDelete(`/api/events/delete_student?student_id=${encodeURIComponent(studentId)}`, authHeaders);
      setCsvMessage(`Deleted ${studentName}.`);
    } catch (error) {
      setUploadedStudents(previousStudents);
      setSelectedUploadedStudentKeys(previousSelectedKeys);
      const message = toErrorMessage(error);
      setCsvMessage(`Delete failed: ${message}`);
    } finally {
      setDeletingStudentIds((current) => current.filter((id) => id !== studentId));
    }
  };

  // Creates a draft presentation group from selected students.
  const handleMakePresentationGroup = () => {
    const selectedEntries = uploadedStudents.filter((student) => selectedUploadedStudentKeys.includes(student.id));
    const selectedNames = selectedEntries.map((entry) => entry.name);
    const selectedIds = selectedEntries.map((entry) => entry.id);
    if (selectedNames.length === 0) {
      setGroupMessage("Select at least one student to make a presentation group.");
      return;
    }
    setPresentationGroups((current) => [
      ...current,
      {
        id: `${Date.now()}-${Math.random().toString(16).slice(2)}`,
        studentIds: selectedIds,
        studentNames: selectedNames,
        presentationName: "",
        durationMinutes: "",
        bufferMinutes: "",
      },
    ]);
    setUploadedStudents((current) => current.filter((student) => !selectedUploadedStudentKeys.includes(student.id)));
    setSelectedUploadedStudentKeys([]);
    setGroupMessage("");
  };

  // Updates the name of a draft presentation group.
  const setPresentationGroupName = (groupId: string, value: string) => {
    setPresentationGroups((current) =>
      current.map((group) => (group.id === groupId ? { ...group, presentationName: value } : group))
    );
  };

  // Updates the duration of a draft presentation group.
  const setPresentationGroupDuration = (groupId: string, value: string) => {
    setPresentationGroups((current) =>
      current.map((group) => (group.id === groupId ? { ...group, durationMinutes: value } : group))
    );
  };

  // Updates the buffer duration of a draft presentation group.
  const setPresentationGroupBuffer = (groupId: string, value: string) => {
    setPresentationGroups((current) =>
      current.map((group) => (group.id === groupId ? { ...group, bufferMinutes: value } : group))
    );
  };


  // Returns students from a removed group back to the available student list.
  const restoreStudentsFromGroup = (target: PresentationGroup) => {
    setUploadedStudents((students) => {
      const existing = new Set(students.map((student) => normalizeId(student.id)));
      const additions: UploadedStudent[] = [];
      target.studentIds.forEach((studentId, index) => {
        const normalized = normalizeId(studentId);
        if (existing.has(normalized)) return;
        existing.add(normalized);
        additions.push({
          id: studentId,
          name: target.studentNames[index] ?? "Student",
        });
      });
      return [...students, ...additions];
    });
  };

  // Removes a presentation group from the UI and restores its students.
  const removePresentationGroupFromUi = (groupId: string, source: "draft" | "deployed" = "draft") => {
    if (source === "deployed") {
      setDeployedPresentationGroups((current) => {
        const target = current.find((group) => group.id === groupId);
        if (target) restoreStudentsFromGroup(target);
        return current.filter((group) => group.id !== groupId);
      });
      return;
    }
    setPresentationGroups((current) => {
      const target = current.find((group) => group.id === groupId);
      if (target) restoreStudentsFromGroup(target);
      return current.filter((group) => group.id !== groupId);
    });
  };

  // Deletes a presentation group from backend when saved, otherwise removes it locally.
  const handleDeletePresentationGroup = async (
    group: PresentationGroup,
    source: "draft" | "deployed" = "draft"
  ) => {
    const confirmed = await confirmDialog(`Delete presentation "${group.presentationName || "Untitled"}"?`, "Delete presentation");
    if (!confirmed) return;

    if (source === "draft" && !isUuid(group.id)) {
      removePresentationGroupFromUi(group.id, source);
      setEmailMessage("Removed unsaved presentation group.");
      return;
    }
    if (!isUuid(group.id)) {
      setEmailMessage("Delete failed: deployed presentation is missing a valid ID.");
      return;
    }

    setDeletingPresentationGroupIds((current) => [...current, group.id]);
    try {
      await apiDelete(`/api/events/delete_presentation?presentation_id=${encodeURIComponent(group.id)}`, authHeaders);
      removePresentationGroupFromUi(group.id, source);
      setEmailMessage("Deleted presentation group.");
    } catch (error) {
      const message = toErrorMessage(error);
      setEmailMessage(`Delete failed: ${message}`);
    } finally {
      setDeletingPresentationGroupIds((current) => current.filter((id) => id !== group.id));
    }
  };

  const startEditDeployedPresentation = (group: PresentationGroup) => {
    setEditingDeployedPresentationId(group.id);
    setEditingPresentationName(group.presentationName);
    setEditingPresentationDuration(group.durationMinutes);
    setEditingPresentationBuffer(group.bufferMinutes);
    setEmailMessage("");
  };

  const cancelEditDeployedPresentation = () => {
    setEditingDeployedPresentationId(null);
    setEditingPresentationName("");
    setEditingPresentationDuration("");
    setEditingPresentationBuffer("");
  };

  const handleSaveEditedPresentation = async (group: PresentationGroup) => {
    if (!isUuid(group.id)) {
      setEmailMessage("Save failed: deployed presentation is missing a valid ID.");
      return;
    }
    const title = editingPresentationName.trim();
    const minutes = Number.parseInt(editingPresentationDuration.trim(), 10);
    const buffer = Number.parseInt(editingPresentationBuffer.trim(), 10);
    if (!title) {
      setEmailMessage("Save failed: presentation title cannot be empty.");
      return;
    }
    if (!Number.isFinite(minutes) || minutes < 1) {
      setEmailMessage("Save failed: duration must be at least 1 minute.");
      return;
    }
    if (!Number.isFinite(buffer) || buffer < 0) {
      setEmailMessage("Save failed: buffer must be 0 or more minutes.");
      return;
    }
    const studentIds = group.studentIds.filter((id) => isUuid(id));
    if (studentIds.length !== group.studentIds.length) {
      setEmailMessage("Save failed: one or more presenting students have invalid IDs.");
      return;
    }
    if (!classId || !isUuid(classId)) {
      setEmailMessage("Save failed: class ID is missing or invalid.");
      return;
    }

    setSavingEditedPresentationId(group.id);
    try {
      await apiPut("/api/events/update_presentation", {
        presentation_id: group.id,
        title,
        class_id: classId,
        minutes,
        buffer,
        presenting_students: studentIds,
      }, authHeaders);

      setDeployedPresentationGroups((current) =>
        current.map((candidate) =>
          candidate.id === group.id
            ? {
                ...candidate,
                presentationName: title,
                durationMinutes: String(minutes),
                bufferMinutes: String(buffer),
              }
            : candidate
        )
      );
      setEmailMessage("Presentation updated.");
      cancelEditDeployedPresentation();
    } catch (error) {
      const message = toErrorMessage(error);
      setEmailMessage(`Save failed: ${message}`);
    } finally {
      setSavingEditedPresentationId(null);
    }
  };

  // Validates and deploys draft presentation groups to the backend.
  const handleEmailPresentations = async () => {
    setEmailMessage("");
    if (!classId) {
      setEmailMessage("No class is linked to the selected professor.");
      return;
    }
    if (presentationGroups.length === 0) {
      setEmailMessage("Create at least one presentation group before deploying.");
      return;
    }

    for (let i = 0; i < presentationGroups.length; i += 1) {
      const group = presentationGroups[i];
      if (!group.presentationName.trim()) {
        setEmailMessage(`Enter a presentation title for Group ${i + 1}.`);
        return;
      }
      const durationValue = usePerPresentationDuration
        ? group.durationMinutes.trim()
        : defaultPresentationDuration.trim();
      const parsedDuration = Number.parseInt(durationValue, 10);
      if (!Number.isFinite(parsedDuration) || parsedDuration < 1) {
        setEmailMessage(
          usePerPresentationDuration
            ? `Enter a valid duration for Group ${i + 1}.`
            : "Enter a valid default presentation duration."
        );
        return;
      }
      const bufferValue = usePerBufferDuration
        ? group.bufferMinutes.trim()
        : defaultBufferDuration.trim();
      const parsedBuffer = Number.parseInt(bufferValue, 10);
      if (!Number.isFinite(parsedBuffer) || parsedBuffer < 0) {
        setEmailMessage(
          usePerBufferDuration
            ? `Enter a valid buffer for Group ${i + 1}.`
            : "Enter a valid default buffer duration."
        );
        return;
      }
    }

    setDeployingPresentations(true);
    try {
      let insertedCount = 0;
      const nextGroups: PresentationGroup[] = [];
      for (const group of presentationGroups) {
        const durationValue = usePerPresentationDuration
          ? group.durationMinutes.trim()
          : defaultPresentationDuration.trim();
        const minutes = Number.parseInt(durationValue, 10);
        const bufferValue = usePerBufferDuration
          ? group.bufferMinutes.trim()
          : defaultBufferDuration.trim();
        const buffer = Number.parseInt(bufferValue, 10);

        const { raw: payload } = await apiPost<Record<string, unknown>>("/api/events/add_presentation", {
          title: group.presentationName.trim(),
          class_id: classId,
          minutes,
          buffer,
          presenting_students: group.studentIds,
        }, authHeaders);
        insertedCount += 1;
        nextGroups.push({
          ...group,
          id: (payload.presentation_id as string) ?? group.id,
        });
      }

      setPresentationGroups([]);
      setDeployedPresentationGroups((current) => {
        const merged = [...current];
        const seen = new Set(current.map((group) => group.id));
        for (const group of nextGroups) {
          if (seen.has(group.id)) continue;
          seen.add(group.id);
          merged.push(group);
        }
        return merged;
      });
      let emailCount = 0;
      for (const group of nextGroups) {
        const { raw: emailResult } = await apiPost("/api/events/email_students", { presentation_id: group.id }, authHeaders);
        emailCount += (emailResult.emails_sent as number) ?? 0;
      }
      setEmailMessage(`Saved ${insertedCount} presentation${insertedCount === 1 ? "" : "s"} and emailed ${emailCount} student${emailCount === 1 ? "" : "s"}.`);
    } catch (error) {
      const message = toErrorMessage(error);
      setEmailMessage(`Failed: ${message}`);
    } finally {
      setDeployingPresentations(false);
    }
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
            OCC THESIS SYMPOSIUM - PROFESSOR
          </h1>
          {identityMessage ? <p className="mt-2 text-center text-sm font-semibold text-[#9a1f1f]">{identityMessage}</p> : null}
        </header>
        <p className="mb-3 text-center text-3xl font-extrabold tracking-wide text-[#0f33a8] md:text-5xl">
          {loadingIdentity ? "Hello!" : `Hello${professorName ? `, ${professorName}` : ""}!`}
        </p>
        {identityReady ? (
          <div className="mb-3 overflow-hidden rounded-xl border border-[#d7e0ff] bg-white text-sm text-[#2d3d7a] md:grid md:grid-cols-2">
            <div className="grid grid-cols-[auto_1fr] px-3 py-2.5 font-semibold md:border-r md:border-[#e4ebff]">
              <span className="border-r border-[#e4ebff] bg-[#eef3ff] px-3 py-2 text-sm font-bold uppercase tracking-wide text-[#1e3a8a]">
                Symposium
              </span>
              <span className="px-4 py-2 text-base font-semibold">{symposiumName || "Unknown"}</span>
            </div>
            <div className="grid grid-cols-[auto_1fr] border-t border-[#e4ebff] px-3 py-2.5 font-semibold md:border-t-0">
              <span className="border-r border-[#e4ebff] bg-[#eef3ff] px-3 py-2 text-sm font-bold uppercase tracking-wide text-[#1e3a8a]">
                Class
              </span>
              <span className="px-4 py-2 text-base font-semibold">{className || "Unknown"}</span>
            </div>
          </div>
        ) : null}

        <nav className="mb-4 grid grid-cols-1 gap-3 md:grid-cols-2">
          <button
            type="button"
            onClick={() => setActiveTab("availability")}
            disabled={pageLocked}
            className={`rounded-xl border-2 px-4 py-3 text-lg font-semibold transition md:text-xl ${
              isAvailabilityTab
                ? "border-[#0f33a8] bg-[#0f33a8] text-white shadow-[0_8px_20px_rgba(15,51,168,0.25)]"
                : "border-[#c6d2f6] bg-white text-[#111] hover:border-[#0f33a8]"
            }`}
          >
            Update Availability
          </button>
          <button
            type="button"
            onClick={() => setActiveTab("students")}
            disabled={pageLocked}
            className={`rounded-xl border-2 px-4 py-3 text-lg font-semibold transition md:text-xl ${
              isAvailabilityTab
                ? "border-[#c6d2f6] bg-white text-[#111] hover:border-[#0f33a8]"
                : "border-[#0f33a8] bg-[#0f33a8] text-white shadow-[0_8px_20px_rgba(15,51,168,0.25)]"
            }`}
          >
            {className ? `Add Students to ${className}` : "Add Students"}
          </button>
        </nav>

        <section className="rounded-2xl border border-[#d7bf92] bg-white p-4 shadow-[0_16px_30px_rgba(80,60,20,0.08)] md:p-6">
          <h2 className="text-xl font-bold text-[#111] md:text-2xl">
            {isAvailabilityTab ? "Update Availability" : className ? `Add Students to ${className}` : "Add Students"}
          </h2>
          {!identityReady ? (
            <p className="mt-2 text-sm font-semibold text-[#9a1f1f]">
              Select a professor above to access this page.
            </p>
          ) : null}

          {isAvailabilityTab && identityReady ? (
            <div className="mt-4">
              <div className="mb-4 flex flex-wrap items-center gap-5 text-sm font-semibold text-[#333] md:text-base">
                <div className="flex items-center gap-2">
                  <span>Unavailable</span>
                  <span className="inline-block h-6 w-8 border border-[#777] bg-[#f0d7d9]" />
                </div>
                <div className="flex items-center gap-2">
                  <span>Available</span>
                  <span className="inline-block h-6 w-8 border border-[#777] bg-[#38a000]" />
                </div>
                <div className="flex items-center gap-2">
                  <span>Not editable</span>
                  <span className="inline-block h-6 w-8 border border-[#777] bg-[#d1d5db]" />
                </div>
              </div>

              <p className="mb-3 text-sm font-semibold text-[#444] md:text-base">
                Click and drag to toggle availability.
              </p>

              {weekPagination.hasMultipleWeeks && (
                <div className="mb-3 flex items-center gap-3">
                  <button type="button" onClick={weekPagination.prevWeek} disabled={!weekPagination.hasPrev} className="rounded-lg border border-[#c7c7c7] bg-white px-3 py-1 text-sm font-semibold text-[#333] transition hover:bg-[#f5f5f5] disabled:cursor-not-allowed disabled:opacity-40" aria-label="Previous week">&larr;</button>
                  <span className="text-sm font-semibold text-[#333]">Week {weekPagination.weekNumber} of {weekPagination.totalWeeks}: {weekPagination.weekLabel}</span>
                  <button type="button" onClick={weekPagination.nextWeek} disabled={!weekPagination.hasNext} className="rounded-lg border border-[#c7c7c7] bg-white px-3 py-1 text-sm font-semibold text-[#333] transition hover:bg-[#f5f5f5] disabled:cursor-not-allowed disabled:opacity-40" aria-label="Next week">&rarr;</button>
                </div>
              )}
              <div className="w-full overflow-x-auto rounded-xl border border-[#cfcfcf] bg-white p-3">
                <AvailabilityGrid
                  calendarDays={calendarDays}
                  availability={availability}
                  editableSlots={editableSlots}
                  weekPagination={weekPagination}
                  handleCellMouseDown={handleCellMouseDown}
                  handleCellMouseEnter={handleCellMouseEnter}
                />
              </div>
              {calendarMessage ? <p className="mt-3 text-sm font-semibold text-[#9a1f1f]">{calendarMessage}</p> : null}
              <div className="mt-4">
                <button
                  type="button"
                  onClick={() => void handleSaveAvailability()}
                  disabled={pageLocked || calendarDays.length === 0 || savingAvailability}
                  className="rounded-lg bg-[#0f33a8] px-4 py-2 text-sm font-semibold text-white shadow-[0_8px_18px_rgba(15,51,168,0.25)] transition hover:bg-[#0b2a8d] disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {savingAvailability ? "Saving..." : "Save"}
                </button>
                {availabilityMessage ? <p className="mt-2 text-sm font-semibold text-[#222]">{availabilityMessage}</p> : null}
              </div>
            </div>
          ) : identityReady ? (
            <form onSubmit={handleCsvUpload} className="mt-4 w-full space-y-3">
              <p className="text-sm font-semibold text-[#2d3d7a] md:text-base">
                File with all students in thesis section:
              </p>
              <p className="text-sm text-[#3b4a7c]">
                Required columns: Student Name, Student ID, Class Level, Preferred Email
              </p>
              <label className="flex w-full cursor-pointer flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed border-[#2f53c4] bg-[#f7f9ff] px-4 py-10 text-center transition hover:bg-[#edf2ff]">
                <span className="text-base font-semibold text-[#1d2d63]">Drop CSV file here or click to upload</span>
                <span className="text-sm text-[#4b5d99]">Accepted format: .csv</span>
                <input
                  ref={csvInputRef}
                  type="file"
                  accept=".csv,text/csv"
                  className="hidden"
                  onChange={(event) => {
                    setCsvFile(event.target.files?.[0] ?? null);
                    setCsvMessage(null);
                  }}
                />
              </label>
              <div className="flex flex-wrap gap-2">
                <button
                  type="submit"
                  disabled={csvUploading}
                  className="rounded-lg bg-[#0f33a8] px-4 py-2 text-sm font-semibold text-white shadow-[0_8px_18px_rgba(15,51,168,0.25)] transition hover:bg-[#0b2a8d] disabled:cursor-not-allowed disabled:opacity-60 md:text-base"
                >
                  {csvUploading ? "Uploading..." : "Upload"}
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setShowManualStudentEntry((current) => !current);
                    setManualStudentMessage(null);
                  }}
                  className="rounded-lg border border-[#0f33a8] bg-white px-4 py-2 text-sm font-semibold text-[#0f33a8] transition hover:bg-[#eef3ff]"
                >
                  Enter Student Manually
                </button>
              </div>
              {showManualStudentEntry ? (
                <div className="rounded-lg border border-[#d7e0ff] bg-[#fdfdff] p-3">
                  <p className="text-xs font-bold uppercase tracking-wide text-[#2d3d7a]">Manual Student Entry</p>
                  <div className="mt-2 grid grid-cols-1 gap-2 md:grid-cols-2">
                    <input
                      value={manualStudentName}
                      onChange={(event) => setManualStudentName(event.target.value)}
                      placeholder="Student name"
                      className="w-full rounded-lg border border-[#c7c7c7] bg-white px-3 py-2 text-sm text-black shadow-sm outline-none transition focus:border-[#1237af] focus:ring-2 focus:ring-[#c7d4ff]"
                    />
                    <input
                      type="email"
                      value={manualStudentEmail}
                      onChange={(event) => setManualStudentEmail(event.target.value)}
                      placeholder="student@hamilton.edu"
                      className="w-full rounded-lg border border-[#c7c7c7] bg-white px-3 py-2 text-sm text-black shadow-sm outline-none transition focus:border-[#1237af] focus:ring-2 focus:ring-[#c7d4ff]"
                    />
                  </div>
                  <div className="mt-2">
                    <button
                      type="button"
                      onClick={() => void handleManualStudentAdd()}
                      disabled={manualStudentSubmitting}
                      className="rounded-lg bg-[#0f33a8] px-4 py-2 text-sm font-semibold text-white shadow-[0_8px_18px_rgba(15,51,168,0.25)] transition hover:bg-[#0b2a8d] disabled:cursor-not-allowed disabled:opacity-60"
                    >
                      {manualStudentSubmitting ? "Adding..." : "Add Student"}
                    </button>
                  </div>
                  {manualStudentMessage ? <p className="mt-2 text-sm font-semibold text-[#222]">{manualStudentMessage}</p> : null}
                </div>
              ) : null}
              {csvFile ? <p className="text-sm text-[#333]">Selected file: {csvFile.name}</p> : null}
              {csvMessage ? <p className="text-sm text-[#222]">{csvMessage}</p> : null}
              {uploadedStudents.length > 0 ||
              presentationGroups.length > 0 ||
              deployedPresentationGroups.length > 0 ? (
                <div className="w-full rounded-lg border border-[#d7e0ff] bg-[#fdfdff] p-3">
                  <p className="text-sm font-bold uppercase tracking-wide text-[#2d3d7a]">Uploaded Students</p>
                  <p className="mt-1 text-xs font-semibold text-[#4b5d99]">
                    Click student names to select them, then click Make Presentation Group.
                  </p>
                  {uploadedStudents.length > 0 ? (
                    <div className="mt-2 grid grid-cols-1 gap-2 md:grid-cols-2">
                      {uploadedStudents.map((student) => {
                        const studentKey = student.id;
                        const isSelected = selectedUploadedStudentKeys.includes(studentKey);
                        const isDeleting = deletingStudentIds.includes(student.id);
                        return (
                          <div
                            key={studentKey}
                            className={`flex items-center rounded-lg border text-sm font-semibold transition ${
                              isSelected
                                ? "border-[#0f33a8] bg-[#e9efff] text-[#0f33a8]"
                                : "border-[#c7c7c7] bg-white text-[#222]"
                            }`}
                          >
                            <button
                              type="button"
                              onClick={() => toggleUploadedStudent(studentKey)}
                              disabled={isDeleting}
                              className="flex-1 px-3 py-2 text-left"
                            >
                              {student.name}
                            </button>
                            <button
                              type="button"
                              onClick={() => void deleteUploadedStudent(student.id, student.name)}
                              disabled={isDeleting}
                              className="mr-2 rounded border border-[#bdbdbd] bg-white px-2 py-0.5 text-xs font-bold text-[#444] transition hover:border-[#9a1f1f] hover:text-[#9a1f1f]"
                              aria-label={`Delete ${student.name}`}
                            >
                              {isDeleting ? "..." : "X"}
                            </button>
                          </div>
                        );
                      })}
                    </div>
                  ) : (
                    <p className="mt-2 text-sm font-semibold text-[#555]">No ungrouped students remaining.</p>
                  )}
                  <div className="mt-3">
                    <button
                      type="button"
                      onClick={handleMakePresentationGroup}
                      disabled={uploadedStudents.length === 0}
                      className="rounded-lg bg-[#0f33a8] px-4 py-2 text-sm font-semibold text-white shadow-[0_8px_18px_rgba(15,51,168,0.25)] transition hover:bg-[#0b2a8d]"
                    >
                      Make Presentation Group
                    </button>
                    {groupMessage ? <p className="mt-2 text-sm font-semibold text-[#9a1f1f]">{groupMessage}</p> : null}
                  </div>
                  {presentationGroups.length > 0 ? (
                    <div className="mt-4 space-y-3">
                      <div className="rounded-lg border border-[#cfd8ff] bg-white p-3">
                        <div className="flex gap-4">
                          <div className="flex flex-1 flex-col gap-1">
                            <label className="flex flex-col gap-1">
                              <span className="text-xs font-bold uppercase tracking-wide text-[#2d3d7a]">
                                Presentation Duration (Minutes)
                              </span>
                              <input
                                type="number"
                                min={1}
                                value={defaultPresentationDuration}
                                onChange={(event) => setDefaultPresentationDuration(event.target.value)}
                                placeholder="e.g. 15"
                                disabled={usePerPresentationDuration}
                                className="w-full rounded-lg border border-[#c7c7c7] bg-white px-3 py-2 text-sm text-black shadow-sm outline-none transition focus:border-[#1237af] focus:ring-2 focus:ring-[#c7d4ff] disabled:cursor-not-allowed disabled:bg-[#f3f4f6]"
                              />
                            </label>
                            <label className="inline-flex items-center gap-2 text-sm font-semibold text-[#1f2937]">
                              <input
                                type="checkbox"
                                checked={usePerPresentationDuration}
                                onChange={(event) => setUsePerPresentationDuration(event.target.checked)}
                              />
                              Set duration per presentation
                            </label>
                          </div>
                          <div className="flex flex-1 flex-col gap-1">
                            <label className="flex flex-col gap-1">
                              <span className="text-xs font-bold uppercase tracking-wide text-[#2d3d7a]">
                                Buffer Duration (Minutes)
                              </span>
                              <input
                                type="number"
                                min={1}
                                value={defaultBufferDuration}
                                onChange={(event) => setDefaultBufferDuration(event.target.value)}
                                placeholder="e.g. 5"
                                className="w-full rounded-lg border border-[#c7c7c7] bg-white px-3 py-2 text-sm text-black shadow-sm outline-none transition focus:border-[#1237af] focus:ring-2 focus:ring-[#c7d4ff]"
                              />
                            </label>
                            <label className="inline-flex items-center gap-2 text-sm font-semibold text-[#1f2937]">
                              <input
                                type="checkbox"
                                checked={usePerBufferDuration}
                                onChange={(event) => setUsePerBufferDuration(event.target.checked)}
                              />
                              Set duration per presentation
                            </label>
                          </div>
                        </div>
                      </div>
                      {presentationGroups.map((group, groupIndex) => (
                        <div key={group.id} className="rounded-lg border border-[#cfd8ff] bg-white p-3">
                          <div className="flex items-start justify-between gap-2">
                            <p className="text-xs font-bold uppercase tracking-wide text-[#2d3d7a]">
                              Group {groupIndex + 1}
                            </p>
                            <button
                              type="button"
                              onClick={() => void handleDeletePresentationGroup(group, "draft")}
                              disabled={deletingPresentationGroupIds.includes(group.id)}
                              className="rounded border border-[#bdbdbd] bg-white px-2 py-0.5 text-xs font-bold text-[#444] transition hover:border-[#9a1f1f] hover:text-[#9a1f1f] disabled:cursor-not-allowed disabled:opacity-60"
                            >
                              {deletingPresentationGroupIds.includes(group.id) ? "..." : "Delete"}
                            </button>
                          </div>
                          <p className="mt-1 text-sm text-[#222]">{group.studentNames.join(", ")}</p>
                          <label className="mt-2 flex flex-col gap-1">
                            <span className="text-xs font-bold uppercase tracking-wide text-[#2d3d7a]">
                              Presentation Name
                            </span>
                            <input
                              value={group.presentationName}
                              onChange={(event) => setPresentationGroupName(group.id, event.target.value)}
                              placeholder="Enter presentation title"
                              className="w-full rounded-lg border border-[#c7c7c7] bg-white px-3 py-2 text-sm text-black shadow-sm outline-none transition focus:border-[#1237af] focus:ring-2 focus:ring-[#c7d4ff]"
                            />
                          </label>
                          <div className="mt-2 flex gap-4">
                            {usePerPresentationDuration ? (
                              <label className="flex flex-1 flex-col gap-1">
                                <span className="text-xs font-bold uppercase tracking-wide text-[#2d3d7a]">
                                  Duration (Minutes)
                                </span>
                                <input
                                  type="number"
                                  min={1}
                                  value={group.durationMinutes}
                                  onChange={(event) => setPresentationGroupDuration(group.id, event.target.value)}
                                  placeholder="e.g. 15"
                                  className="w-full rounded-lg border border-[#c7c7c7] bg-white px-3 py-2 text-sm text-black shadow-sm outline-none transition focus:border-[#1237af] focus:ring-2 focus:ring-[#c7d4ff]"
                                />
                              </label>
                            ) : (
                              <p className="flex-1 text-sm font-semibold text-[#2d3d7a]">
                                Duration: {defaultPresentationDuration.trim() ? `${defaultPresentationDuration} minutes` : "Not set"}
                              </p>
                            )}
                            {usePerBufferDuration ? (
                              <label className="flex flex-1 flex-col gap-1">
                                <span className="text-xs font-bold uppercase tracking-wide text-[#2d3d7a]">
                                  Buffer (Minutes)
                                </span>
                                <input
                                  type="number"
                                  min={1}
                                  value={group.bufferMinutes}
                                  onChange={(event) => setPresentationGroupBuffer(group.id, event.target.value)}
                                  placeholder="e.g. 5"
                                  className="w-full rounded-lg border border-[#c7c7c7] bg-white px-3 py-2 text-sm text-black shadow-sm outline-none transition focus:border-[#1237af] focus:ring-2 focus:ring-[#c7d4ff]"
                                />
                              </label>
                            ) : (
                              <p className="flex-1 text-sm font-semibold text-[#2d3d7a]">
                                Buffer: {defaultBufferDuration.trim() ? `${defaultBufferDuration} minutes` : "Not set"}
                              </p>
                            )}
                          </div>
                        </div>
                      ))}
                      <div className="pt-1">
                        <button
                          type="button"
                          onClick={() => void handleEmailPresentations()}
                          disabled={emailingPresentations}
                          className="rounded-lg bg-[#1b6e2b] px-4 py-2 text-sm font-semibold text-white shadow-[0_8px_18px_rgba(27,110,43,0.25)] transition hover:bg-[#155622]"
                        >
                          {emailingPresentations ? "Sending Emails..." : "Send Emails"}
                        </button>
                        {emailMessage ? <p className="mt-2 text-sm font-semibold text-[#222]">{emailMessage}</p> : null}
                      </div>
                    </div>
                  ) : null}
                  {deployedPresentationGroups.length > 0 ? (
                    <div className="mt-4 rounded-lg border border-[#d7e0ff] bg-white p-3">
                      <h4 className="text-sm font-bold uppercase tracking-wide text-[#2d3d7a] md:text-base">
                        Deployed Presentations
                      </h4>
                      <div className="mt-2 space-y-2">
                        {deployedPresentationGroups.map((group, index) => (
                          <div key={`deployed-${group.id}`} className="rounded border border-[#cfd8ff] bg-[#fdfdff] p-2">
                            <div className="flex items-start justify-between gap-2">
                              <p className="text-sm font-semibold text-[#111]">{`Presentation ${index + 1}`}</p>
                              <div className="flex items-center gap-1">
                                {editingDeployedPresentationId === group.id ? (
                                  <>
                                    <button
                                      type="button"
                                      onClick={() => void handleSaveEditedPresentation(group)}
                                      disabled={savingEditedPresentationId === group.id}
                                      className="rounded border border-[#1b6e2b] bg-white px-2 py-0.5 text-xs font-bold text-[#1b6e2b] transition hover:bg-[#edf8f0] disabled:cursor-not-allowed disabled:opacity-60"
                                    >
                                      {savingEditedPresentationId === group.id ? "Saving..." : "Save"}
                                    </button>
                                    <button
                                      type="button"
                                      onClick={cancelEditDeployedPresentation}
                                      disabled={savingEditedPresentationId === group.id}
                                      className="rounded border border-[#bdbdbd] bg-white px-2 py-0.5 text-xs font-bold text-[#444] transition hover:border-[#666]"
                                    >
                                      Cancel
                                    </button>
                                  </>
                                ) : (
                                  <button
                                    type="button"
                                    onClick={() => startEditDeployedPresentation(group)}
                                    className="rounded border border-[#0f33a8] bg-white px-2 py-0.5 text-xs font-bold text-[#0f33a8] transition hover:bg-[#eef3ff]"
                                  >
                                    Edit
                                  </button>
                                )}
                                <button
                                  type="button"
                                  onClick={() => void handleDeletePresentationGroup(group, "deployed")}
                                  disabled={deletingPresentationGroupIds.includes(group.id) || savingEditedPresentationId === group.id}
                                  className="rounded border border-[#bdbdbd] bg-white px-2 py-0.5 text-xs font-bold text-[#444] transition hover:border-[#9a1f1f] hover:text-[#9a1f1f] disabled:cursor-not-allowed disabled:opacity-60"
                                >
                                  {deletingPresentationGroupIds.includes(group.id) ? "..." : "Delete"}
                                </button>
                              </div>
                            </div>
                            {editingDeployedPresentationId === group.id ? (
                              <div className="mt-2 grid grid-cols-1 gap-2 md:grid-cols-3">
                                <label className="flex flex-col gap-1">
                                  <span className="text-xs font-bold uppercase tracking-wide text-[#2d3d7a]">
                                    Presentation Name
                                  </span>
                                  <input
                                    value={editingPresentationName}
                                    onChange={(event) => setEditingPresentationName(event.target.value)}
                                    className="w-full rounded-lg border border-[#c7c7c7] bg-white px-3 py-2 text-sm text-black shadow-sm outline-none transition focus:border-[#1237af] focus:ring-2 focus:ring-[#c7d4ff]"
                                  />
                                </label>
                                <label className="flex flex-col gap-1">
                                  <span className="text-xs font-bold uppercase tracking-wide text-[#2d3d7a]">
                                    Duration (Minutes)
                                  </span>
                                  <input
                                    type="number"
                                    min={1}
                                    value={editingPresentationDuration}
                                    onChange={(event) => setEditingPresentationDuration(event.target.value)}
                                    className="w-full rounded-lg border border-[#c7c7c7] bg-white px-3 py-2 text-sm text-black shadow-sm outline-none transition focus:border-[#1237af] focus:ring-2 focus:ring-[#c7d4ff]"
                                  />
                                </label>
                                <label className="flex flex-col gap-1">
                                  <span className="text-xs font-bold uppercase tracking-wide text-[#2d3d7a]">
                                    Buffer (Minutes)
                                  </span>
                                  <input
                                    type="number"
                                    min={0}
                                    value={editingPresentationBuffer}
                                    onChange={(event) => setEditingPresentationBuffer(event.target.value)}
                                    className="w-full rounded-lg border border-[#c7c7c7] bg-white px-3 py-2 text-sm text-black shadow-sm outline-none transition focus:border-[#1237af] focus:ring-2 focus:ring-[#c7d4ff]"
                                  />
                                </label>
                              </div>
                            ) : (
                              <>
                                <p className="text-sm font-semibold text-[#111]">
                                  {group.presentationName.trim() || `Presentation ${index + 1}`}
                                </p>
                                <p className="text-xs text-[#444]">
                                  {group.durationMinutes.trim()
                                    ? `${group.durationMinutes.trim()} minutes`
                                    : "Duration not set"}
                                  {group.bufferMinutes.trim()
                                    ? ` | Buffer: ${group.bufferMinutes.trim()} min`
                                    : ""}
                                </p>
                              </>
                            )}
                            <p className="text-xs text-[#444]">{group.studentNames.join(", ")}</p>
                          </div>
                        ))}
                      </div>
                    </div>
                  ) : null}
                </div>
              ) : null}
            </form>
          ) : null}
        </section>
      </div>
    </main>
  );
}

// Wraps the professor page content in a suspense boundary.
export default function ProfessorPage({ token, onSignOut, entityId }: { token: string; onSignOut: () => void; entityId: string }) {
  return (
    <Suspense fallback={<main className="min-h-screen bg-[#f5f5f5] px-4 py-8">Loading...</main>}>
      <ProfessorPageContent token={token} onSignOut={onSignOut} entityId={entityId} />
    </Suspense>
  );
}
