"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

type FacultyTab = "availability" | "students";
const totalSlots = 32; // 9:00 AM to 5:00 PM in 15-minute increments
type CalendarDay = { key: string; label: string };
type PresentationGroup = { id: string; studentNames: string[]; presentationName: string };

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

function parseCsvLine(line: string): string[] {
  const cells: string[] = [];
  let current = "";
  let inQuotes = false;

  for (let i = 0; i < line.length; i += 1) {
    const char = line[i];
    if (char === '"') {
      if (inQuotes && line[i + 1] === '"') {
        current += '"';
        i += 1;
      } else {
        inQuotes = !inQuotes;
      }
      continue;
    }
    if (char === "," && !inQuotes) {
      cells.push(current.trim());
      current = "";
      continue;
    }
    current += char;
  }
  cells.push(current.trim());
  return cells;
}

function buildCandidateUrls(baseUrl: string, path: string): string[] {
  const normalizedBase = baseUrl.replace(/\/+$/, "");
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  const direct = `${normalizedBase}${normalizedPath}`;
  if (normalizedBase.endsWith("/api") && normalizedPath.startsWith("/api/")) {
    const withoutDupApi = `${normalizedBase}${normalizedPath.replace(/^\/api/, "")}`;
    return [direct, withoutDupApi];
  }
  if (!normalizedBase.endsWith("/api") && normalizedPath.startsWith("/api/")) {
    const withoutApi = `${normalizedBase}${normalizedPath.replace(/^\/api/, "")}`;
    return [direct, withoutApi];
  }
  return [direct];
}

export default function FacultyPage() {
  const searchParams = useSearchParams();
  const professorId = searchParams.get("professor_id") ?? "";
  const [activeTab, setActiveTab] = useState<FacultyTab>("availability");
  const [availability, setAvailability] = useState<boolean[][]>([]);
  const [editableSlots, setEditableSlots] = useState<boolean[][]>([]);
  const [calendarDays, setCalendarDays] = useState<CalendarDay[]>([]);
  const [calendarMessage, setCalendarMessage] = useState<string>("");
  const [isDragging, setIsDragging] = useState(false);
  const [dragValue, setDragValue] = useState<boolean | null>(null);
  const [availabilityMessage, setAvailabilityMessage] = useState<string>("");
  const [savingAvailability, setSavingAvailability] = useState(false);
  const [csvFile, setCsvFile] = useState<File | null>(null);
  const [csvUploading, setCsvUploading] = useState(false);
  const [csvMessage, setCsvMessage] = useState<string | null>(null);
  const [uploadedStudentNames, setUploadedStudentNames] = useState<string[]>([]);
  const [selectedUploadedStudentKeys, setSelectedUploadedStudentKeys] = useState<string[]>([]);
  const [presentationGroups, setPresentationGroups] = useState<PresentationGroup[]>([]);
  const [groupMessage, setGroupMessage] = useState<string>("");
  const [deployMessage, setDeployMessage] = useState<string>("");
  const [professorName, setProfessorName] = useState<string>("");
  const [classId, setClassId] = useState<string>("");
  const [className, setClassName] = useState<string>("");
  const [symposiumName, setSymposiumName] = useState<string>("");
  const [loadingIdentity, setLoadingIdentity] = useState(false);
  const [identityMessage, setIdentityMessage] = useState<string>("");

  const isAvailabilityTab = activeTab === "availability";
  const hasProfessorLink = Boolean(professorId);
  const identityReady = hasProfessorLink && !loadingIdentity && Boolean(professorName);
  const pageLocked = !hasProfessorLink || (!loadingIdentity && !professorName);
  const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:8000";
  const backendApiKey = process.env.NEXT_PUBLIC_BACKEND_API_KEY ?? "";
  const authHeaders = useMemo(
    () => (backendApiKey ? { "X-API-Key": backendApiKey } : undefined),
    [backendApiKey]
  );

  useEffect(() => {
    if (!professorId) {
      setProfessorName("");
      setClassId("");
      setClassName("");
      setSymposiumName("");
      setIdentityMessage("Missing professor_id in URL.");
      setEditableSlots([]);
      setCalendarDays([]);
      setCalendarMessage("");
      return;
    }

    let ignore = false;
    const loadIdentity = async () => {
      setLoadingIdentity(true);
      setIdentityMessage("");
      setCalendarMessage("");
      try {
        const [professorsRes, classesRes, departmentsRes, symposiumsRes] = await Promise.all([
          fetch(`${backendUrl}/api/events/professors`, { headers: authHeaders }),
          fetch(`${backendUrl}/api/events/classes`, { headers: authHeaders }),
          fetch(`${backendUrl}/api/events/departments`, { headers: authHeaders }),
          fetch(`${backendUrl}/api/events/symposiums`, { headers: authHeaders }),
        ]);

        const professorsPayload = (await professorsRes.json().catch(() => ({}))) as
          | { data?: Array<{ id?: string; name?: string; class_id?: string }> }
          | Array<{ id?: string; name?: string; class_id?: string }>;
        const classesPayload = (await classesRes.json().catch(() => ({}))) as
          | { data?: Array<{ id?: string; name?: string; department_id?: string }> }
          | Array<{ id?: string; name?: string; department_id?: string }>;
        const departmentsPayload = (await departmentsRes.json().catch(() => ({}))) as
          | { data?: Array<{ id?: string; symposium_id?: string }> }
          | Array<{ id?: string; symposium_id?: string }>;
        const symposiumsPayload = (await symposiumsRes.json().catch(() => ({}))) as
          | { data?: Array<{ id?: string; name?: string; symposium_name?: string }> }
          | Array<{ id?: string; name?: string; symposium_name?: string }>;

        if (!professorsRes.ok) {
          throw new Error(toMessage((professorsPayload as { detail?: unknown }).detail, "Failed to load professor."));
        }
        if (!classesRes.ok) {
          throw new Error(toMessage((classesPayload as { detail?: unknown }).detail, "Failed to load class data."));
        }
        if (!departmentsRes.ok) {
          throw new Error(toMessage((departmentsPayload as { detail?: unknown }).detail, "Failed to load departments."));
        }
        if (!symposiumsRes.ok) {
          throw new Error(toMessage((symposiumsPayload as { detail?: unknown }).detail, "Failed to load symposium."));
        }

        const professorRows = Array.isArray(professorsPayload) ? professorsPayload : (professorsPayload.data ?? []);
        const classRows = Array.isArray(classesPayload) ? classesPayload : (classesPayload.data ?? []);
        const departmentRows = Array.isArray(departmentsPayload) ? departmentsPayload : (departmentsPayload.data ?? []);
        const symposiumRows = Array.isArray(symposiumsPayload) ? symposiumsPayload : (symposiumsPayload.data ?? []);
        const professor = professorRows.find((row) => row.id === professorId);
        if (!professor) {
          throw new Error("Invalid professor link. No professor found for this professor_id.");
        }

        const resolvedClassId = professor.class_id ?? "";
        const matchedClass = classRows.find((row) => row.id === resolvedClassId);
        const matchedDepartment = departmentRows.find((row) => row.id === matchedClass?.department_id);
        const symposiumId = matchedDepartment?.symposium_id ?? "";
        const matchedSymposium = symposiumRows.find((row) => row.id === symposiumId);

        let nextCalendarDays: CalendarDay[] = [];
        let nextEditableSlots: boolean[][] = [];
        let nextAvailability: boolean[][] = [];
        if (symposiumId) {
          const symposiumTimeframesRes = await fetch(
            `${backendUrl}/api/events/timeframes?linked_id=${encodeURIComponent(symposiumId)}`,
            { headers: authHeaders }
          );
          const symposiumTimeframesPayload = (await symposiumTimeframesRes.json().catch(() => ({}))) as
            | { data?: Array<{ start_time?: string; end_time?: string }> }
            | Array<{ start_time?: string; end_time?: string }>;

          if (!symposiumTimeframesRes.ok) {
            throw new Error(
              toMessage((symposiumTimeframesPayload as { detail?: unknown }).detail, "Failed to load symposium dates.")
            );
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
            const end =
              row.end_time && row.end_time.trim().length > 0 ? parseBackendDateTime(row.end_time) : null;
            const key = `${start.getFullYear()}-${String(start.getMonth() + 1).padStart(2, "0")}-${String(
              start.getDate()
            ).padStart(2, "0")}`;
            uniqueDayKeys.add(key);
            parsedSymposiumRows.push({ start, end: end && !Number.isNaN(end.getTime()) ? end : null });
          }

          nextCalendarDays = Array.from(uniqueDayKeys)
            .sort()
            .map((key) => {
              const date = new Date(`${key}T00:00:00`);
              return {
                key,
                label: formatCalendarDate(date),
              };
            });

          const dayIndexByKey = new Map(nextCalendarDays.map((day, index) => [day.key, index]));
          nextEditableSlots = Array.from({ length: nextCalendarDays.length }, () =>
            Array.from({ length: totalSlots }, () => false)
          );
          nextAvailability = Array.from({ length: nextCalendarDays.length }, () =>
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

          const professorTimeframesRes = await fetch(
            `${backendUrl}/api/events/timeframes?linked_id=${encodeURIComponent(professorId)}`,
            { headers: authHeaders }
          );
          const professorTimeframesPayload = (await professorTimeframesRes.json().catch(() => ({}))) as
            | { data?: Array<{ start_time?: string; end_time?: string }> }
            | Array<{ start_time?: string; end_time?: string }>;

          if (!professorTimeframesRes.ok) {
            throw new Error(
              toMessage((professorTimeframesPayload as { detail?: unknown }).detail, "Failed to load saved availability.")
            );
          }

          const professorTimeframeRows = Array.isArray(professorTimeframesPayload)
            ? professorTimeframesPayload
            : (professorTimeframesPayload.data ?? []);

          for (const row of professorTimeframeRows) {
            if (!row.start_time) continue;
            const start = parseBackendDateTime(row.start_time);
            if (Number.isNaN(start.getTime())) continue;
            const end =
              row.end_time && row.end_time.trim().length > 0 ? parseBackendDateTime(row.end_time) : null;

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
        setEditableSlots(nextEditableSlots);
        setAvailability(nextAvailability);
        setProfessorName(professor.name ?? "Professor");
        setClassId(resolvedClassId);
        setClassName(matchedClass?.name ?? "");
        setSymposiumName(matchedSymposium?.name ?? matchedSymposium?.symposium_name ?? "");
        setCalendarDays(nextCalendarDays);
        setCalendarMessage(nextCalendarDays.length === 0 ? "No symposium dates are configured yet." : "");
      } catch (error) {
        if (ignore) return;
        const message = error instanceof Error ? error.message : "Unknown error";
        setIdentityMessage(message);
        setSymposiumName("");
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
  }, [authHeaders, backendUrl, professorId]);

  useEffect(() => {
    const stopDragging = () => {
      setIsDragging(false);
      setDragValue(null);
    };

    window.addEventListener("mouseup", stopDragging);
    return () => window.removeEventListener("mouseup", stopDragging);
  }, []);

  const setCell = (dayIndex: number, slotIndex: number, value: boolean) => {
    setAvailability((current) =>
      Array.from({ length: calendarDays.length }, (_, dIdx) =>
        Array.from({ length: totalSlots }, (_, sIdx) =>
          dIdx === dayIndex && sIdx === slotIndex ? value : (current[dIdx]?.[sIdx] ?? false)
        )
      )
    );
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

  const handleSaveAvailability = async () => {
    setAvailabilityMessage("");
    if (!professorId) {
      setAvailabilityMessage("Missing professor_id in URL.");
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

      for (let slotIndex = 0; slotIndex < totalSlots; slotIndex += 1) {
        const editable = editableSlots[dayIndex]?.[slotIndex] ?? false;
        const available = availability[dayIndex]?.[slotIndex] ?? false;
        if (!editable || !available) continue;

        const start = new Date(year, month - 1, dayOfMonth, 9, 0, 0, 0);
        start.setMinutes(start.getMinutes() + slotIndex * 15);
        const end = new Date(start);
        end.setMinutes(end.getMinutes() + 15);

        timeframes.push({
          start_time: start.toISOString(),
          end_time: end.toISOString(),
        });
      }
    }

    setSavingAvailability(true);
    try {
      const response = await fetch(`${backendUrl}/api/events/update_timeframes`, {
        method: "PUT",
        headers: {
          "Content-Type": "application/json",
          ...(authHeaders ?? {}),
        },
        body: JSON.stringify({
          linked_id: professorId,
          timeframes,
        }),
      });
      const payload = (await response.json().catch(() => ({}))) as { detail?: unknown };
      if (!response.ok) {
        setAvailabilityMessage(`Save failed: ${toMessage(payload.detail, "Unable to save availability.")}`);
        return;
      }
      setAvailabilityMessage(`Saved ${timeframes.length} availability slot${timeframes.length === 1 ? "" : "s"}.`);
    } catch (error) {
      const message = error instanceof Error ? error.message : "Unknown error";
      if (message.toLowerCase().includes("load failed") || message.toLowerCase().includes("failed to fetch")) {
        setAvailabilityMessage(`Save failed: backend is unreachable at ${backendUrl}.`);
      } else {
        setAvailabilityMessage(`Save failed: ${message}`);
      }
    } finally {
      setSavingAvailability(false);
    }
  };

  async function handleCsvUpload(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!classId) {
      setCsvMessage("Missing class_id for this professor link.");
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

      let response: Response | null = null;
      let payload: { detail?: unknown; records_inserted?: { students?: number } } = {};
      for (const url of buildCandidateUrls(backendUrl, "/api/events/add_students")) {
        response = await fetch(url, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            ...(authHeaders ?? {}),
          },
          body: JSON.stringify({
            class_id: classId,
            students,
          }),
        });
        payload = (await response.json().catch(() => ({}))) as {
          detail?: unknown;
          records_inserted?: {
            students?: number;
          };
        };
        if (response.status !== 404) break;
      }

      if (!response || !response.ok) {
        setCsvMessage(toMessage(payload.detail, "CSV upload failed."));
        return;
      }

      const inserted = payload.records_inserted?.students ?? students.length;
      const skipped = Math.max(0, lines.length - 1 - students.length);
      setCsvMessage(`Upload successful: inserted ${inserted} student${inserted === 1 ? "" : "s"}${skipped > 0 ? `, skipped ${skipped}` : ""}.`);
      setUploadedStudentNames(students.map((student) => student.name));
      setSelectedUploadedStudentKeys([]);
      setPresentationGroups([]);
      setGroupMessage("");
      setCsvFile(null);
    } catch (error) {
      const message = error instanceof Error ? error.message : "Unknown error";
      if (message.toLowerCase().includes("load failed") || message.toLowerCase().includes("failed to fetch")) {
        setCsvMessage("CSV upload failed: backend is unreachable at http://localhost:8000.");
      } else {
        setCsvMessage(`CSV upload failed: ${message}`);
      }
    } finally {
      setCsvUploading(false);
    }
  }

  const toggleUploadedStudent = (studentKey: string) => {
    setSelectedUploadedStudentKeys((current) =>
      current.includes(studentKey) ? current.filter((key) => key !== studentKey) : [...current, studentKey]
    );
  };

  const handleMakePresentationGroup = () => {
    const entries = uploadedStudentNames.map((name, index) => ({
      name,
      key: `${name}-${index}`,
    }));
    const selectedEntries = entries.filter((entry) => selectedUploadedStudentKeys.includes(entry.key));
    const selectedNames = selectedEntries.map((entry) => entry.name);
    if (selectedNames.length === 0) {
      setGroupMessage("Select at least one student to make a presentation group.");
      return;
    }
    setPresentationGroups((current) => [
      ...current,
      {
        id: `${Date.now()}-${Math.random().toString(16).slice(2)}`,
        studentNames: selectedNames,
        presentationName: "",
      },
    ]);
    setUploadedStudentNames(entries.filter((entry) => !selectedUploadedStudentKeys.includes(entry.key)).map((entry) => entry.name));
    setSelectedUploadedStudentKeys([]);
    setGroupMessage("");
  };

  const setPresentationGroupName = (groupId: string, value: string) => {
    setPresentationGroups((current) =>
      current.map((group) => (group.id === groupId ? { ...group, presentationName: value } : group))
    );
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
            OCC THESIS SYMPOSIUM - FACULTY
          </h1>
          {identityMessage ? <p className="mt-2 text-center text-sm font-semibold text-[#9a1f1f]">{identityMessage}</p> : null}
          {!professorId ? (
            <p className="mt-2 text-center text-sm font-semibold text-[#9a1f1f]">
              Open this page with `?professor_id=&lt;uuid&gt;` in the URL.
            </p>
          ) : null}
        </header>
        <p className="mb-3 text-center text-3xl font-extrabold tracking-wide text-[#0f33a8] md:text-5xl">
          {loadingIdentity ? "Hello!" : `Hello${professorName ? `, ${professorName}` : ""}!`}
        </p>
        {symposiumName ? (
          <p className="mb-3 text-center text-sm font-semibold text-[#2d3d7a] md:text-base">
            Symposium: {symposiumName}
          </p>
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
              Use your unique professor link to access this page.
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
                  type="file"
                  accept=".csv,text/csv"
                  className="hidden"
                  onChange={(event) => {
                    setCsvFile(event.target.files?.[0] ?? null);
                    setCsvMessage(null);
                  }}
                />
              </label>
              <button
                type="submit"
                disabled={csvUploading}
                className="rounded-lg bg-[#0f33a8] px-4 py-2 text-sm font-semibold text-white shadow-[0_8px_18px_rgba(15,51,168,0.25)] transition hover:bg-[#0b2a8d] disabled:cursor-not-allowed disabled:opacity-60 md:text-base"
              >
                {csvUploading ? "Uploading..." : "Upload"}
              </button>
              {csvFile ? <p className="text-sm text-[#333]">Selected file: {csvFile.name}</p> : null}
              {csvMessage ? <p className="text-sm text-[#222]">{csvMessage}</p> : null}
              {uploadedStudentNames.length > 0 ? (
                <div className="w-full rounded-lg border border-[#d7e0ff] bg-[#fdfdff] p-3">
                  <p className="text-sm font-bold uppercase tracking-wide text-[#2d3d7a]">Uploaded Students</p>
                  <div className="mt-2 grid grid-cols-1 gap-2 md:grid-cols-2">
                    {uploadedStudentNames.map((name, index) => {
                      const studentKey = `${name}-${index}`;
                      const isSelected = selectedUploadedStudentKeys.includes(studentKey);
                      return (
                        <button
                          key={studentKey}
                          type="button"
                          onClick={() => toggleUploadedStudent(studentKey)}
                          className={`rounded-lg border px-3 py-2 text-left text-sm font-semibold transition ${
                            isSelected
                              ? "border-[#0f33a8] bg-[#e9efff] text-[#0f33a8]"
                              : "border-[#c7c7c7] bg-white text-[#222] hover:border-[#0f33a8]"
                          }`}
                        >
                          {name}
                        </button>
                      );
                    })}
                  </div>
                  <div className="mt-3">
                    <button
                      type="button"
                      onClick={handleMakePresentationGroup}
                      className="rounded-lg bg-[#0f33a8] px-4 py-2 text-sm font-semibold text-white shadow-[0_8px_18px_rgba(15,51,168,0.25)] transition hover:bg-[#0b2a8d]"
                    >
                      Make Presentation Group
                    </button>
                    {groupMessage ? <p className="mt-2 text-sm font-semibold text-[#9a1f1f]">{groupMessage}</p> : null}
                  </div>
                  {presentationGroups.length > 0 ? (
                    <div className="mt-4 space-y-3">
                      {presentationGroups.map((group, groupIndex) => (
                        <div key={group.id} className="rounded-lg border border-[#cfd8ff] bg-white p-3">
                          <p className="text-xs font-bold uppercase tracking-wide text-[#2d3d7a]">
                            Group {groupIndex + 1}
                          </p>
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
                        </div>
                      ))}
                      <div className="pt-1">
                        <button
                          type="button"
                          onClick={() =>
                            setDeployMessage(
                              "Deploy Presentation is not connected yet. It will eventually send an email to each student group."
                            )
                          }
                          className="rounded-lg bg-[#1b6e2b] px-4 py-2 text-sm font-semibold text-white shadow-[0_8px_18px_rgba(27,110,43,0.25)] transition hover:bg-[#155622]"
                        >
                          Deploy Presentation
                        </button>
                        {deployMessage ? <p className="mt-2 text-sm font-semibold text-[#222]">{deployMessage}</p> : null}
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
