"use client";

import { useEffect, useMemo, useState } from "react";
import type { CalendarDay, SavedProfessorRequest, StudentOption, StudentTab } from "./types";
import {
  totalSlots,
  formatTimeLabel,
  buildCalendarFromTimeframes,
} from "../lib/utils";
import { apiFetch, apiPost, apiPut } from "../lib/api";
import { useCalendarGrid } from "../lib/useCalendarGrid";
import { useWeekPagination } from "../lib/useWeekPagination";

// Renders the student page and manages its data and interactions.
export default function StudentPage({ token, onSignOut, entityId }: { token: string; onSignOut: () => void; entityId: string }) {
  const authHeaders = useMemo(() => ({ Authorization: `Bearer ${token}` }), [token]);
  const [studentOptions, setStudentOptions] = useState<StudentOption[]>([]);
  const [selectedStudentId, setSelectedStudentId] = useState("");
  const [loadingStudents, setLoadingStudents] = useState(false);
  const [activeTab, setActiveTab] = useState<StudentTab>("availability");
  const [editableSlots, setEditableSlots] = useState<boolean[][]>([]);
  const [calendarDays, setCalendarDays] = useState<CalendarDay[]>([]);
  const [calendarMessage, setCalendarMessage] = useState("");
  const { availability, setAvailability, handleCellMouseDown, handleCellMouseEnter } = useCalendarGrid(calendarDays.length, editableSlots);
  const weekPagination = useWeekPagination(calendarDays.map((d) => d.key));
  const hasSelectedStudent = Boolean(selectedStudentId);
  const [studentName, setStudentName] = useState("");
  const [symposiumName, setSymposiumName] = useState("");
  const [className, setClassName] = useState("");
  const [presentationName, setPresentationName] = useState("");
  const [loadingIdentity, setLoadingIdentity] = useState(false);
  const [identityMessage, setIdentityMessage] = useState("");
  const [preferredProfessorName, setPreferredProfessorName] = useState("");
  const [preferredProfessorEmail, setPreferredProfessorEmail] = useState("");
  const [savedProfessorRequests, setSavedProfessorRequests] = useState<SavedProfessorRequest[]>([]);
  const [savingPreferences, setSavingPreferences] = useState(false);
  const [preferencesMessage, setPreferencesMessage] = useState("");
  const [savingAvailability, setSavingAvailability] = useState(false);
  const [availabilityMessage, setAvailabilityMessage] = useState("");
  const identityReady = hasSelectedStudent && !loadingIdentity && Boolean(studentName);

  const isAvailabilityTab = activeTab === "availability";

  useEffect(() => {
    let ignore = false;
    // Loads student options and selects a valid default.
    const loadStudentOptions = async () => {
      setLoadingStudents(true);
      setIdentityMessage("");
      try {
        const studentRows = await apiFetch<{ id?: string; name?: string }>("/api/events/students", { headers: authHeaders });
        const nextOptions = studentRows
          .filter((row) => row.id)
          .map((row) => ({
            id: row.id as string,
            name: (row.name ?? "").trim() || (row.id as string),
          }));

        if (ignore) return;
        setStudentOptions(nextOptions);
        setSelectedStudentId((current) => {
          if (current && nextOptions.some((option) => option.id === current)) return current;
          if (entityId && nextOptions.some((option) => option.id === entityId)) return entityId;
          return nextOptions[0]?.id ?? "";
        });
        if (nextOptions.length === 0) {
          setIdentityMessage("No students found.");
        }
      } catch (error) {
        if (ignore) return;
        const message = error instanceof Error ? error.message : "Unknown error";
        setIdentityMessage(message);
        setStudentOptions([]);
        setSelectedStudentId("");
      } finally {
        if (!ignore) setLoadingStudents(false);
      }
    };

    void loadStudentOptions();
    return () => {
      ignore = true;
    };
  }, [authHeaders]);

  useEffect(() => {
    if (!selectedStudentId) {
      setStudentName("");
      setSymposiumName("");
      setClassName("");
      setPresentationName("");
      if (!loadingStudents) {
        setIdentityMessage((current) => (current ? current : "Select a student to load data."));
      }
      setCalendarDays([]);
      setEditableSlots([]);
      setAvailability([]);
      setCalendarMessage("");
      setAvailabilityMessage("");
      setPreferredProfessorName("");
      setPreferredProfessorEmail("");
      setSavedProfessorRequests([]);
      return;
    }

    let ignore = false;
    // AI template: loads student identity, resolves the class/symposium chain, maps timeframes to calendar slots, and fetches saved preference requests.
    const loadStudent = async () => {
      setLoadingIdentity(true);
      setIdentityMessage("");
      setCalendarMessage("");
      setAvailabilityMessage("");
      try {
        const [studentRows, classRows, departmentRows, symposiumInfoRows] = await Promise.all([
          apiFetch<{ id?: string; name?: string; email?: string; class_id?: string }>("/api/events/students", { headers: authHeaders }),
          apiFetch<{ id?: string; name?: string; department_id?: string }>("/api/events/classes", { headers: authHeaders }),
          apiFetch<{ id?: string; symposium_id?: string }>("/api/events/departments", { headers: authHeaders }),
          apiFetch<{ id?: string; name?: string; symposium_name?: string }>("/api/events/symposiums", { headers: authHeaders }),
        ]);

        const student = studentRows.find((row) => row.id === selectedStudentId);
        if (!student) {
          throw new Error("Select a student to load data.");
        }

        const classId = student.class_id ?? "";
        const classRow = classRows.find((row) => row.id === classId);
        const departmentRow = departmentRows.find((row) => row.id === classRow?.department_id);
        const symposiumId = departmentRow?.symposium_id ?? "";
        const symposiumRow = symposiumInfoRows.find((row) => row.id === symposiumId);
        if (!symposiumId) {
          throw new Error("No symposium is linked to this student.");
        }

        let resolvedPresentationName = "";
        if (classId) {
          try {
            const presentationRows = await apiFetch<{
              id?: string;
              title?: string;
              presenting_students?: Array<{ id?: string; student_id?: string }>;
            }>(`/api/events/presentations?class_id=${encodeURIComponent(classId)}`, { headers: authHeaders });
            const presentingMembershipRows = presentationRows.flatMap((presentation) =>
              (presentation.presenting_students ?? []).map((presentingStudent) => ({
                presentationId: presentation.id ?? "",
                studentId: (presentingStudent.id ?? presentingStudent.student_id ?? "").trim(),
              }))
            );
            const matchedPresentationId =
              presentingMembershipRows.find((membership) => membership.studentId === selectedStudentId)?.presentationId ??
              "";
            resolvedPresentationName =
              presentationRows.find((presentation) => presentation.id === matchedPresentationId)?.title ?? "";
          } catch { /* presentations are optional context */ }
        }

        const symposiumTimeframeRows = await apiFetch<{ start_time?: string; end_time?: string }>(
          `/api/events/timeframes?linked_id=${encodeURIComponent(symposiumId)}`, { headers: authHeaders }
        );

        let studentRowsTf: Array<{ start_time?: string; end_time?: string }> = [];
        try {
          studentRowsTf = await apiFetch<{ start_time?: string; end_time?: string }>(
            `/api/events/timeframes?linked_id=${encodeURIComponent(selectedStudentId)}`, { headers: authHeaders }
          );
        } catch { /* student availability is optional */ }

        const { calendarDays: nextCalendarDays, editableSlots: nextEditableSlots, availability: nextAvailability } =
          buildCalendarFromTimeframes(symposiumTimeframeRows, studentRowsTf);

        if (ignore) return;
        let requestRows: Array<{ id?: string; name?: string; email?: string }> = [];
        try {
          requestRows = await apiFetch<{ id?: string; name?: string; email?: string }>(
            `/api/events/requests?student_id=${encodeURIComponent(selectedStudentId)}`, { headers: authHeaders }
          );
        } catch { /* requests are optional */ }
        const nextSavedRequests: SavedProfessorRequest[] = requestRows
          .filter((row) => row.id && row.name && row.email)
          .map((row) => ({
            id: row.id as string,
            professorId: "",
            professorName: row.name as string,
            professorEmail: (row.email as string).toLowerCase(),
          }));

        setStudentName(student.name ?? "Student");
        setSymposiumName(symposiumRow?.name ?? symposiumRow?.symposium_name ?? "");
        setClassName(classRow?.name ?? "");
        setPresentationName(resolvedPresentationName);
        setPreferredProfessorName("");
        setPreferredProfessorEmail("");
        setSavedProfessorRequests(nextSavedRequests);
        setCalendarDays(nextCalendarDays);
        setEditableSlots(nextEditableSlots);
        setAvailability(nextAvailability);
        setCalendarMessage(nextCalendarDays.length === 0 ? "No symposium dates are configured yet." : "");
      } catch (error) {
        if (ignore) return;
        const message = error instanceof Error ? error.message : "Unknown error";
        setStudentName("");
        setSymposiumName("");
        setClassName("");
        setPresentationName("");
        setIdentityMessage(message);
        setCalendarDays([]);
        setEditableSlots([]);
        setAvailability([]);
        setPreferredProfessorName("");
        setPreferredProfessorEmail("");
        setSavedProfessorRequests([]);
      } finally {
        if (!ignore) setLoadingIdentity(false);
      }
    };

    void loadStudent();
    return () => {
      ignore = true;
    };
  }, [authHeaders, loadingStudents, selectedStudentId]);

  // Saves one preferred professor request for the selected student.
  const handleSavePreferences = async () => {
    setPreferencesMessage("");
    if (!selectedStudentId) {
      setPreferencesMessage("Select a student first.");
      return;
    }

    const requestName = preferredProfessorName.trim();
    const requestEmail = preferredProfessorEmail.trim().toLowerCase();
    if (!requestName || !requestEmail) {
      setPreferencesMessage("Enter a name and email.");
      return;
    }

    setSavingPreferences(true);
    try {
      await apiPost("/api/events/add_request", {
        name: requestName,
        email: requestEmail,
        student_id: selectedStudentId,
      }, authHeaders);

      let requestRows: Array<{ id?: string; name?: string; email?: string }> = [];
      try {
        requestRows = await apiFetch<{ id?: string; name?: string; email?: string }>(
          `/api/events/requests?student_id=${encodeURIComponent(selectedStudentId)}`, { headers: authHeaders }
        );
      } catch { /* ignore refresh failure */ }
      const nextSavedRequests: SavedProfessorRequest[] = requestRows
        .filter((row) => row.id && row.name && row.email)
        .map((row) => ({
          id: row.id as string,
          professorId: "",
          professorName: row.name as string,
          professorEmail: (row.email as string).toLowerCase(),
        }));
      setSavedProfessorRequests(nextSavedRequests);

      setPreferencesMessage("Request saved.");
      setPreferredProfessorName("");
      setPreferredProfessorEmail("");
    } catch (error) {
      const message = error instanceof Error ? error.message : "Unknown error";
      setPreferencesMessage(`Save failed: ${message}`);
    } finally {
      setSavingPreferences(false);
    }
  };

  // Saves selected availability slots to the backend.
  const handleSaveAvailability = async () => {
    setAvailabilityMessage("");
    if (!selectedStudentId) {
      setAvailabilityMessage("Select a student first.");
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
          const slotStart = new Date(year, month - 1, dayOfMonth, 9, 0, 0, 0);
          slotStart.setMinutes(slotStart.getMinutes() + slotIndex * 15);
          const slotEnd = new Date(slotStart);
          slotEnd.setMinutes(slotEnd.getMinutes() + 15);

          if (!rangeStart) {
            rangeStart = slotStart;
            rangeEnd = slotEnd;
          } else {
            rangeEnd = slotEnd;
          }
        } else if (rangeStart && rangeEnd) {
          timeframes.push({ start_time: rangeStart.toISOString(), end_time: rangeEnd.toISOString() });
          rangeStart = null;
          rangeEnd = null;
        }
      }

      if (rangeStart && rangeEnd) {
        timeframes.push({ start_time: rangeStart.toISOString(), end_time: rangeEnd.toISOString() });
      }
    }

    setSavingAvailability(true);
    try {
      await apiPut("/api/events/update_timeframes", {
        linked_id: selectedStudentId,
        timeframes,
      }, authHeaders);
      setAvailabilityMessage(`Saved ${timeframes.length} availability slot${timeframes.length === 1 ? "" : "s"}.`);
    } catch (error) {
      const message = error instanceof Error ? error.message : "Unknown error";
      setAvailabilityMessage(`Save failed: ${message}`);
    } finally {
      setSavingAvailability(false);
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
            OCC THESIS SYMPOSIUM - STUDENT
          </h1>
          {identityMessage ? <p className="mt-2 text-center text-sm font-semibold text-[#9a1f1f]">{identityMessage}</p> : null}
        </header>
        <p className="mb-3 text-center text-3xl font-extrabold tracking-wide text-[#0f33a8] md:text-5xl">
          {loadingIdentity ? "Hello!" : `Hello${studentName ? `, ${studentName}` : ""}!`}
        </p>
        {identityReady ? (
          <div className="mb-3 overflow-hidden rounded-xl border border-[#d7e0ff] bg-white text-sm text-[#2d3d7a] md:grid md:grid-cols-3">
            <div className="grid grid-cols-[auto_1fr] px-3 py-2.5 font-semibold md:border-r md:border-[#e4ebff]">
              <span className="border-r border-[#e4ebff] bg-[#eef3ff] px-3 py-2 text-sm font-bold uppercase tracking-wide text-[#1e3a8a]">
                Symposium
              </span>
              <span className="px-4 py-2 text-base font-semibold">{symposiumName || "Unknown"}</span>
            </div>
            <div className="grid grid-cols-[auto_1fr] border-t border-[#e4ebff] px-3 py-2.5 font-semibold md:border-t-0 md:border-r md:border-[#e4ebff]">
              <span className="border-r border-[#e4ebff] bg-[#eef3ff] px-3 py-2 text-sm font-bold uppercase tracking-wide text-[#1e3a8a]">
                Class
              </span>
              <span className="px-4 py-2 text-base font-semibold">{className || "Unknown"}</span>
            </div>
            <div className="grid grid-cols-[auto_1fr] border-t border-[#e4ebff] px-3 py-2.5 font-semibold md:border-t-0">
              <span className="border-r border-[#e4ebff] bg-[#eef3ff] px-3 py-2 text-sm font-bold uppercase tracking-wide text-[#1e3a8a]">
                Presentation
              </span>
              <span className="px-4 py-2 text-base font-semibold">{presentationName || "Unknown"}</span>
            </div>
          </div>
        ) : null}

        <nav className="mb-4 grid grid-cols-1 gap-3 md:grid-cols-2">
          <button
            type="button"
            onClick={() => setActiveTab("availability")}
            disabled={!identityReady}
            className={`rounded-xl border-2 px-4 py-3 text-lg font-semibold transition md:text-xl ${
              isAvailabilityTab
                ? "border-[#0f33a8] bg-[#0f33a8] text-white shadow-[0_8px_20px_rgba(15,51,168,0.25)]"
                : "border-[#c6d2f6] bg-white text-[#111] hover:border-[#0f33a8]"
            } disabled:cursor-not-allowed disabled:opacity-60`}
          >
            Update Availability
          </button>
          <button
            type="button"
            onClick={() => setActiveTab("preferences")}
            disabled={!identityReady}
            className={`rounded-xl border-2 px-4 py-3 text-lg font-semibold transition md:text-xl ${
              isAvailabilityTab
                ? "border-[#c6d2f6] bg-white text-[#111] hover:border-[#0f33a8]"
                : "border-[#0f33a8] bg-[#0f33a8] text-white shadow-[0_8px_20px_rgba(15,51,168,0.25)]"
            } disabled:cursor-not-allowed disabled:opacity-60`}
          >
            Update Preferences
          </button>
        </nav>

        <section className="rounded-2xl border border-[#d7bf92] bg-white p-4 shadow-[0_16px_30px_rgba(80,60,20,0.08)] md:p-6">
          <h2 className="text-xl font-bold text-[#111] md:text-2xl">
            {isAvailabilityTab
              ? presentationName
                ? `Update Availability for ${presentationName}`
                : "Update Availability"
              : "Update Preferences"}
          </h2>
          {!identityReady ? (
            <p className="mt-2 text-sm font-semibold text-[#9a1f1f]">
              Select a student above to access this page.
            </p>
          ) : null}

          {/* AI template: drag-to-edit availability calendar grid */}
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
                <div className="min-w-[720px] select-none">
                  <div
                    className="grid text-center text-2xl font-bold text-[#222]"
                    style={{ gridTemplateColumns: `90px repeat(${weekPagination.visibleDayIndices.length}, minmax(120px, 1fr))` }}
                  >
                    <div />
                    {weekPagination.visibleDayIndices.map((di) => (
                      <div key={calendarDays[di].key} className="border-b border-[#777] pb-1 text-sm md:text-lg">
                        {calendarDays[di].label}
                      </div>
                    ))}
                  </div>

                  <div
                    className="grid"
                    style={{ gridTemplateColumns: `90px repeat(${weekPagination.visibleDayIndices.length}, minmax(120px, 1fr))` }}
                  >
                    {Array.from({ length: totalSlots }, (_, slotIndex) => (
                      <div key={slotIndex} className="contents">
                        <div className="h-6 overflow-hidden pr-2 text-right text-sm leading-6 font-semibold text-[#444]">
                          {slotIndex % 4 === 0 ? formatTimeLabel(slotIndex) : ""}
                        </div>

                        {weekPagination.visibleDayIndices.map((dayIndex) => {
                          const day = calendarDays[dayIndex];
                          const available = availability[dayIndex]?.[slotIndex] ?? false;
                          const editable = editableSlots[dayIndex]?.[slotIndex] ?? false;
                          const showHourLine = slotIndex % 4 === 0;
                          return (
                            <button
                              key={`${dayIndex}-${slotIndex}`}
                              type="button"
                              onMouseDown={() => handleCellMouseDown(dayIndex, slotIndex)}
                              onMouseEnter={() => handleCellMouseEnter(dayIndex, slotIndex)}
                              onDragStart={(event) => event.preventDefault()}
                              disabled={!editable}
                              className={`h-6 border-r border-l border-b border-[#333] ${
                                showHourLine ? "border-t border-t-[#333]" : ""
                              } ${
                                !editable ? "cursor-not-allowed bg-[#d1d5db]" : available ? "bg-[#38a000]" : "bg-[#f0d7d9]"
                              }`}
                              aria-label={`${day.label} ${formatTimeLabel(slotIndex)}`}
                            />
                          );
                        })}
                      </div>
                    ))}
                  </div>
                </div>
              </div>
              {calendarMessage ? <p className="mt-3 text-sm font-semibold text-[#9a1f1f]">{calendarMessage}</p> : null}
              <div className="mt-4 flex items-center gap-4">
                <button
                  type="button"
                  onClick={() => void handleSaveAvailability()}
                  disabled={savingAvailability}
                  className="rounded-lg bg-[#0f33a8] px-6 py-2 text-sm font-semibold text-white shadow-[0_8px_18px_rgba(15,51,168,0.25)] transition hover:bg-[#0b2a8d] disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {savingAvailability ? "Saving..." : "Save"}
                </button>
                {availabilityMessage ? <p className="text-sm font-semibold text-[#222]">{availabilityMessage}</p> : null}
              </div>
            </div>
          ) : identityReady ? (
            
            <div className="mt-4 w-full max-w-4xl rounded-xl border border-[#e6ecff] bg-[#fdfdff] p-4">
              <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
                <label className="flex flex-col gap-1">
                  <span className="text-xs font-bold uppercase tracking-wide text-[#2d3d7a]">Name</span>
                  <input
                    type="text"
                    value={preferredProfessorName}
                    onChange={(event) => setPreferredProfessorName(event.target.value)}
                    placeholder="Enter name"
                    className="w-full rounded-lg border border-[#c7c7c7] bg-white px-3 py-2.5 text-black shadow-sm outline-none transition focus:border-[#1237af] focus:ring-2 focus:ring-[#c7d4ff]"
                  />
                </label>
                <label className="flex flex-col gap-1">
                  <span className="text-xs font-bold uppercase tracking-wide text-[#2d3d7a]">Email</span>
                  <input
                    type="email"
                    value={preferredProfessorEmail}
                    onChange={(event) => setPreferredProfessorEmail(event.target.value)}
                    placeholder="Enter email"
                    className="w-full rounded-lg border border-[#c7c7c7] bg-white px-3 py-2.5 text-black shadow-sm outline-none transition focus:border-[#1237af] focus:ring-2 focus:ring-[#c7d4ff]"
                  />
                </label>
                <div className="md:col-span-2">
                  <button
                    type="button"
                    onClick={() => void handleSavePreferences()}
                    disabled={savingPreferences}
                    className="rounded-lg bg-[#0f33a8] px-4 py-2 text-sm font-semibold text-white shadow-[0_8px_18px_rgba(15,51,168,0.25)] transition hover:bg-[#0b2a8d] disabled:cursor-not-allowed disabled:opacity-60"
                  >
                    {savingPreferences ? "Saving..." : "Save"}
                  </button>
                </div>
                {preferencesMessage ? <p className="text-sm font-semibold text-[#222] md:col-span-2">{preferencesMessage}</p> : null}
                <div className="rounded-lg border border-[#d7e0ff] bg-white p-3 md:col-span-2">
                  <p className="text-sm font-bold uppercase tracking-wide text-[#2d3d7a]">Saved Requests</p>
                  {savedProfessorRequests.length === 0 ? (
                    <p className="mt-2 text-sm text-[#555]">No saved requests yet.</p>
                  ) : (
                    <ul className="mt-2 space-y-1 text-sm text-[#222]">
                      {savedProfessorRequests.map((request) => (
                        <li key={request.id} className="rounded border border-[#e5e7eb] bg-[#fafafa] px-2 py-1">
                          {request.professorName} ({request.professorEmail})
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              </div>
            </div>
          ) : null}
        </section>
      </div>
    </main>
  );
}
