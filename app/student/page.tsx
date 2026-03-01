"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

type StudentTab = "availability" | "preferences";
type CalendarDay = { key: string; label: string };
type SavedProfessorRequest = { id: string; professorId: string; professorName: string; professorEmail: string };
type StudentOption = { id: string; name: string };

const totalSlots = 32; // 9:00 AM to 5:00 PM in 15-minute increments

function formatTimeLabel(slotIndex: number) {
  const totalMinutes = 9 * 60 + slotIndex * 15;
  const hour24 = Math.floor(totalMinutes / 60);
  const minutes = totalMinutes % 60;
  const suffix = hour24 >= 12 ? "PM" : "AM";
  const hour12 = hour24 % 12 === 0 ? 12 : hour24 % 12;
  const minutePart = minutes.toString().padStart(2, "0");
  return `${hour12}:${minutePart} ${suffix}`;
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
  return new Date(hasExplicitTimezone ? value : `${value}Z`);
}

export default function StudentPage() {
  const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:8000";
  const backendApiKey = process.env.NEXT_PUBLIC_BACKEND_API_KEY ?? "";
  const [studentOptions, setStudentOptions] = useState<StudentOption[]>([]);
  const [selectedStudentId, setSelectedStudentId] = useState("");
  const [loadingStudents, setLoadingStudents] = useState(false);
  const [activeTab, setActiveTab] = useState<StudentTab>("availability");
  const [availability, setAvailability] = useState<boolean[][]>([]);
  const [editableSlots, setEditableSlots] = useState<boolean[][]>([]);
  const [calendarDays, setCalendarDays] = useState<CalendarDay[]>([]);
  const [calendarMessage, setCalendarMessage] = useState("");
  const [isDragging, setIsDragging] = useState(false);
  const [dragValue, setDragValue] = useState<boolean | null>(null);
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
  const identityReady = hasSelectedStudent && !loadingIdentity && Boolean(studentName);

  const isAvailabilityTab = activeTab === "availability";

  useEffect(() => {
    const stopDragging = () => {
      setIsDragging(false);
      setDragValue(null);
    };

    window.addEventListener("mouseup", stopDragging);
    return () => window.removeEventListener("mouseup", stopDragging);
  }, []);

  useEffect(() => {
    let ignore = false;
    const loadStudentOptions = async () => {
      setLoadingStudents(true);
      setIdentityMessage("");
      try {
        const studentsRes = await fetch(`${backendUrl}/api/events/students`, {
          headers: backendApiKey ? { "X-API-Key": backendApiKey } : undefined,
        });
        const studentsPayload = (await studentsRes.json().catch(() => ({}))) as
          | { detail?: unknown; data?: Array<{ id?: string; name?: string }> }
          | Array<{ id?: string; name?: string }>;
        if (!studentsRes.ok) {
          throw new Error("Failed to load students.");
        }
        const studentRows = Array.isArray(studentsPayload) ? studentsPayload : (studentsPayload.data ?? []);
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
  }, [backendApiKey, backendUrl]);

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
      setPreferredProfessorName("");
      setPreferredProfessorEmail("");
      setSavedProfessorRequests([]);
      return;
    }

    let ignore = false;
    const loadStudent = async () => {
      setLoadingIdentity(true);
      setIdentityMessage("");
      setCalendarMessage("");
      try {
        const [studentsRes, classesRes, departmentsRes, symposiumsRes] = await Promise.all([
          fetch(`${backendUrl}/api/events/students`, {
            headers: backendApiKey ? { "X-API-Key": backendApiKey } : undefined,
          }),
          fetch(`${backendUrl}/api/events/classes`, {
            headers: backendApiKey ? { "X-API-Key": backendApiKey } : undefined,
          }),
          fetch(`${backendUrl}/api/events/departments`, {
            headers: backendApiKey ? { "X-API-Key": backendApiKey } : undefined,
          }),
          fetch(`${backendUrl}/api/events/symposiums`, {
            headers: backendApiKey ? { "X-API-Key": backendApiKey } : undefined,
          }),
        ]);

        const studentsPayload = (await studentsRes.json().catch(() => ({}))) as
          | { detail?: unknown; data?: Array<{ id?: string; name?: string; email?: string; class_id?: string }> }
          | Array<{ id?: string; name?: string; email?: string; class_id?: string }>;
        const classesPayload = (await classesRes.json().catch(() => ({}))) as
          | { detail?: unknown; data?: Array<{ id?: string; name?: string; department_id?: string }> }
          | Array<{ id?: string; name?: string; department_id?: string }>;
        const departmentsPayload = (await departmentsRes.json().catch(() => ({}))) as
          | { detail?: unknown; data?: Array<{ id?: string; symposium_id?: string }> }
          | Array<{ id?: string; symposium_id?: string }>;
        const symposiumsPayload = (await symposiumsRes.json().catch(() => ({}))) as
          | { detail?: unknown; data?: Array<{ id?: string; name?: string; symposium_name?: string }> }
          | Array<{ id?: string; name?: string; symposium_name?: string }>;

        if (!studentsRes.ok || !classesRes.ok || !departmentsRes.ok || !symposiumsRes.ok) {
          throw new Error("Failed to load student.");
        }

        const studentRows = Array.isArray(studentsPayload) ? studentsPayload : (studentsPayload.data ?? []);
        const classRows = Array.isArray(classesPayload) ? classesPayload : (classesPayload.data ?? []);
        const departmentRows = Array.isArray(departmentsPayload) ? departmentsPayload : (departmentsPayload.data ?? []);
        const symposiumInfoRows = Array.isArray(symposiumsPayload) ? symposiumsPayload : (symposiumsPayload.data ?? []);

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
          const presentationsRes = await fetch(
            `${backendUrl}/api/events/presentations?class_id=${encodeURIComponent(classId)}`,
            {
              headers: backendApiKey ? { "X-API-Key": backendApiKey } : undefined,
            }
          );
          const presentationsPayload = (await presentationsRes.json().catch(() => ({}))) as
            | {
                data?: Array<{
                  id?: string;
                  title?: string;
                  presenting_students?: Array<{ id?: string; student_id?: string }>;
                }>;
              }
            | Array<{ id?: string; title?: string; presenting_students?: Array<{ id?: string; student_id?: string }> }>;
          if (presentationsRes.ok) {
            const presentationRows = Array.isArray(presentationsPayload)
              ? presentationsPayload
              : (presentationsPayload.data ?? []);
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
          }
        }

        const symposiumTimeframesRes = await fetch(
          `${backendUrl}/api/events/timeframes?linked_id=${encodeURIComponent(symposiumId)}`,
          {
            headers: backendApiKey ? { "X-API-Key": backendApiKey } : undefined,
          }
        );
        const symposiumTimeframesPayload = (await symposiumTimeframesRes.json().catch(() => ({}))) as
          | { detail?: unknown; data?: Array<{ start_time?: string; end_time?: string }> }
          | Array<{ start_time?: string; end_time?: string }>;
        if (!symposiumTimeframesRes.ok) {
          throw new Error("Failed to load symposium timeframe.");
        }

        const symposiumTimeframeRows = Array.isArray(symposiumTimeframesPayload)
          ? symposiumTimeframesPayload
          : (symposiumTimeframesPayload.data ?? []);
        const uniqueDayKeys = new Set<string>();
        const parsedSymposiumRows: Array<{ start: Date; end: Date | null }> = [];
        for (const row of symposiumTimeframeRows) {
          if (!row.start_time) continue;
          const start = parseBackendDateTime(row.start_time);
          if (Number.isNaN(start.getTime())) continue;
          const end = row.end_time ? parseBackendDateTime(row.end_time) : null;
          const key = `${start.getFullYear()}-${String(start.getMonth() + 1).padStart(2, "0")}-${String(
            start.getDate()
          ).padStart(2, "0")}`;
          uniqueDayKeys.add(key);
          parsedSymposiumRows.push({ start, end: end && !Number.isNaN(end.getTime()) ? end : null });
        }

        const nextCalendarDays = Array.from(uniqueDayKeys)
          .sort()
          .map((key) => ({
            key,
            label: formatCalendarDate(new Date(`${key}T00:00:00`)),
          }));
        const dayIndexByKey = new Map(nextCalendarDays.map((day, index) => [day.key, index]));
        const nextEditableSlots = Array.from({ length: nextCalendarDays.length }, () =>
          Array.from({ length: totalSlots }, () => false)
        );
        const nextAvailability = Array.from({ length: nextCalendarDays.length }, () =>
          Array.from({ length: totalSlots }, () => false)
        );

        for (const row of parsedSymposiumRows) {
          const dayKey = `${row.start.getFullYear()}-${String(row.start.getMonth() + 1).padStart(2, "0")}-${String(
            row.start.getDate()
          ).padStart(2, "0")}`;
          const dayIndex = dayIndexByKey.get(dayKey);
          if (dayIndex === undefined) continue;
          const startMinutes = row.start.getHours() * 60 + row.start.getMinutes();
          const startSlot = Math.floor((startMinutes - 9 * 60) / 15);
          const endMinutes = row.end ? row.end.getHours() * 60 + row.end.getMinutes() : startMinutes + 15;
          const slotSpan = Math.max(1, Math.ceil((endMinutes - startMinutes) / 15));
          for (let offset = 0; offset < slotSpan; offset += 1) {
            const slotIndex = startSlot + offset;
            if (slotIndex >= 0 && slotIndex < totalSlots) {
              nextEditableSlots[dayIndex][slotIndex] = true;
            }
          }
        }

        const studentTimeframesRes = await fetch(
          `${backendUrl}/api/events/timeframes?linked_id=${encodeURIComponent(selectedStudentId)}`,
          {
            headers: backendApiKey ? { "X-API-Key": backendApiKey } : undefined,
          }
        );
        const studentTimeframesPayload = (await studentTimeframesRes.json().catch(() => ({}))) as
          | { detail?: unknown; data?: Array<{ start_time?: string; end_time?: string }> }
          | Array<{ start_time?: string; end_time?: string }>;
        if (studentTimeframesRes.ok) {
          const studentRowsTf = Array.isArray(studentTimeframesPayload)
            ? studentTimeframesPayload
            : (studentTimeframesPayload.data ?? []);
          for (const row of studentRowsTf) {
            if (!row.start_time) continue;
            const start = parseBackendDateTime(row.start_time);
            if (Number.isNaN(start.getTime())) continue;
            const end = row.end_time ? parseBackendDateTime(row.end_time) : null;
            const dayKey = `${start.getFullYear()}-${String(start.getMonth() + 1).padStart(2, "0")}-${String(
              start.getDate()
            ).padStart(2, "0")}`;
            const dayIndex = dayIndexByKey.get(dayKey);
            if (dayIndex === undefined) continue;
            const startMinutes = start.getHours() * 60 + start.getMinutes();
            const startSlot = Math.floor((startMinutes - 9 * 60) / 15);
            const endMinutes = end ? end.getHours() * 60 + end.getMinutes() : startMinutes + 15;
            const slotSpan = Math.max(1, Math.ceil((endMinutes - startMinutes) / 15));
            for (let offset = 0; offset < slotSpan; offset += 1) {
              const slotIndex = startSlot + offset;
              if (slotIndex < 0 || slotIndex >= totalSlots) continue;
              if (!nextEditableSlots[dayIndex]?.[slotIndex]) continue;
              nextAvailability[dayIndex][slotIndex] = true;
            }
          }
        }

        if (ignore) return;
        const requestsRes = await fetch(
          `${backendUrl}/api/events/requests?student_id=${encodeURIComponent(selectedStudentId)}`,
          {
            headers: backendApiKey ? { "X-API-Key": backendApiKey } : undefined,
          }
        );
        const requestsPayload = (await requestsRes.json().catch(() => ({}))) as
          | { data?: Array<{ id?: string; name?: string; email?: string }> }
          | Array<{ id?: string; name?: string; email?: string }>;
        const requestRows = requestsRes.ok
          ? Array.isArray(requestsPayload)
            ? requestsPayload
            : (requestsPayload.data ?? [])
          : [];
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
  }, [backendApiKey, backendUrl, loadingStudents, selectedStudentId]);

  const setCell = (dayIndex: number, slotIndex: number, value: boolean) => {
    setAvailability((current) =>
      Array.from({ length: calendarDays.length }, (_, dIdx) =>
        Array.from({ length: totalSlots }, (_, sIdx) =>
          dIdx === dayIndex && sIdx === slotIndex ? value : (current[dIdx]?.[sIdx] ?? false)
        )
      )
    );
  };

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
      const response = await fetch(`${backendUrl}/api/events/add_request`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(backendApiKey ? { "X-API-Key": backendApiKey } : {}),
        },
        body: JSON.stringify({
          name: requestName,
          email: requestEmail,
          student_id: selectedStudentId,
        }),
      });
      const payload = (await response.json().catch(() => ({}))) as { detail?: unknown };
      if (!response.ok) {
        const detail = payload.detail;
        const text =
          typeof detail === "string"
            ? detail
            : Array.isArray(detail)
              ? detail.map((item) => (typeof item === "string" ? item : (item as { msg?: unknown })?.msg)).join("; ")
              : "Unable to save request.";
        setPreferencesMessage(`Save failed: ${text}`);
        return;
      }

      const requestsRes = await fetch(
        `${backendUrl}/api/events/requests?student_id=${encodeURIComponent(selectedStudentId)}`,
        {
          headers: backendApiKey ? { "X-API-Key": backendApiKey } : undefined,
        }
      );
      const requestsPayload = (await requestsRes.json().catch(() => ({}))) as
        | { data?: Array<{ id?: string; name?: string; email?: string }> }
        | Array<{ id?: string; name?: string; email?: string }>;
      if (requestsRes.ok) {
        const requestRows = Array.isArray(requestsPayload) ? requestsPayload : (requestsPayload.data ?? []);
        const nextSavedRequests: SavedProfessorRequest[] = requestRows
          .filter((row) => row.id && row.name && row.email)
          .map((row) => ({
            id: row.id as string,
            professorId: "",
            professorName: row.name as string,
            professorEmail: (row.email as string).toLowerCase(),
          }));
        setSavedProfessorRequests(nextSavedRequests);
      }

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

  const handleCellMouseDown = (dayIndex: number, slotIndex: number) => {
    if (!editableSlots[dayIndex]?.[slotIndex]) return;
    const nextValue = !(availability[dayIndex]?.[slotIndex] ?? false);
    setCell(dayIndex, slotIndex, nextValue);
    setDragValue(nextValue);
    setIsDragging(true);
  };

  const handleCellMouseEnter = (dayIndex: number, slotIndex: number) => {
    if (!isDragging || dragValue === null) return;
    if (!editableSlots[dayIndex]?.[slotIndex]) return;
    setCell(dayIndex, slotIndex, dragValue);
  };

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
            OCC THESIS SYMPOSIUM - STUDENT
          </h1>
          <label className="mx-auto mt-4 block w-full max-w-xl">
            <span className="text-xs font-bold uppercase tracking-wide text-[#2d3d7a]">Student</span>
            <select
              value={selectedStudentId}
              onChange={(event) => setSelectedStudentId(event.target.value)}
              disabled={loadingStudents || studentOptions.length === 0}
              className="mt-2 w-full rounded-lg border border-[#c7c7c7] bg-white px-3 py-2.5 text-black shadow-sm outline-none transition focus:border-[#1237af] focus:ring-2 focus:ring-[#c7d4ff] disabled:cursor-not-allowed disabled:opacity-60"
            >
              <option value="">Select student</option>
              {studentOptions.map((student) => (
                <option key={student.id} value={student.id}>
                  {student.name}
                </option>
              ))}
            </select>
          </label>
          {identityMessage ? <p className="mt-2 text-center text-sm font-semibold text-[#9a1f1f]">{identityMessage}</p> : null}
        </header>
        <p className="mb-3 text-center text-3xl font-extrabold tracking-wide text-[#0f33a8] md:text-5xl">
          {loadingIdentity ? "Hello!" : `Hello${studentName ? `, ${studentName}` : ""}!`}
        </p>
        {identityReady ? (
          <div className="mb-3 overflow-hidden rounded-xl border border-[#d7e0ff] bg-white text-sm text-[#2d3d7a] md:grid md:grid-cols-3">
            <p className="px-3 py-2.5 font-semibold md:border-r md:border-[#e4ebff]">
              <span className="mr-1 font-bold">Symposium:</span>
              <span>{symposiumName || "Unknown"}</span>
            </p>
            <p className="border-t border-[#e4ebff] px-3 py-2.5 font-semibold md:border-t-0 md:border-r md:border-[#e4ebff]">
              <span className="mr-1 font-bold">Class:</span>
              <span>{className || "Unknown"}</span>
            </p>
            <p className="border-t border-[#e4ebff] px-3 py-2.5 font-semibold md:border-t-0">
              <span className="mr-1 font-bold">Presentation:</span>
              <span>{presentationName || "Unknown"}</span>
            </p>
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

              <div className="w-full overflow-x-auto rounded-xl border border-[#cfcfcf] bg-white p-3">
                <div className="min-w-[720px] select-none">
                  <div
                    className="grid text-center text-2xl font-bold text-[#222]"
                    style={{ gridTemplateColumns: `90px repeat(${calendarDays.length}, minmax(120px, 1fr))` }}
                  >
                    <div />
                    {calendarDays.map((day) => (
                      <div key={day.key} className="border-b border-[#777] pb-1 text-sm md:text-lg">
                        {day.label}
                      </div>
                    ))}
                  </div>

                  <div
                    className="grid"
                    style={{ gridTemplateColumns: `90px repeat(${calendarDays.length}, minmax(120px, 1fr))` }}
                  >
                    {Array.from({ length: totalSlots }, (_, slotIndex) => (
                      <div key={slotIndex} className="contents">
                        <div className="pr-2 pt-1 text-right text-sm font-semibold text-[#444]">
                          {slotIndex % 4 === 0 ? formatTimeLabel(slotIndex) : ""}
                        </div>

                        {calendarDays.map((day, dayIndex) => {
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
