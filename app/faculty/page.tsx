"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

type FacultyTab = "availability" | "students";
const totalSlots = 32; // 9:00 AM to 5:00 PM in 15-minute increments
type CalendarDay = { key: string; label: string };

function formatTimeLabel(slotIndex: number) {
  const totalMinutes = 9 * 60 + slotIndex * 15;
  const hour24 = Math.floor(totalMinutes / 60);
  const minutes = totalMinutes % 60;
  const suffix = hour24 >= 12 ? "PM" : "AM";
  const hour12 = hour24 % 12 === 0 ? 12 : hour24 % 12;
  const minutePart = minutes.toString().padStart(2, "0");
  return `${hour12}:${minutePart} ${suffix}`;
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

export default function FacultyPage() {
  const searchParams = useSearchParams();
  const professorId = searchParams.get("professor_id") ?? "";
  const [activeTab, setActiveTab] = useState<FacultyTab>("availability");
  const [availability, setAvailability] = useState<boolean[][]>([]);
  const [calendarDays, setCalendarDays] = useState<CalendarDay[]>([]);
  const [calendarMessage, setCalendarMessage] = useState<string>("");
  const [isDragging, setIsDragging] = useState(false);
  const [dragValue, setDragValue] = useState<boolean | null>(null);
  const [csvFile, setCsvFile] = useState<File | null>(null);
  const [csvUploading, setCsvUploading] = useState(false);
  const [csvMessage, setCsvMessage] = useState<string | null>(null);
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
    if (calendarDays.length === 0) {
      setAvailability([]);
      return;
    }
    setAvailability((current) =>
      Array.from({ length: calendarDays.length }, (_, dayIndex) =>
        Array.from({ length: totalSlots }, (_, slotIndex) => current[dayIndex]?.[slotIndex] ?? false)
      )
    );
  }, [calendarDays]);

  useEffect(() => {
    if (!professorId) {
      setProfessorName("");
      setClassId("");
      setClassName("");
      setSymposiumName("");
      setIdentityMessage("Missing professor_id in URL.");
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
        if (symposiumId) {
          const timeframesRes = await fetch(
            `${backendUrl}/api/events/timeframes?linked_id=${encodeURIComponent(symposiumId)}`,
            { headers: authHeaders }
          );
          const timeframesPayload = (await timeframesRes.json().catch(() => ({}))) as
            | { data?: Array<{ start_time?: string }> }
            | Array<{ start_time?: string }>;

          if (!timeframesRes.ok) {
            throw new Error(toMessage((timeframesPayload as { detail?: unknown }).detail, "Failed to load symposium dates."));
          }

          const timeframeRows = Array.isArray(timeframesPayload) ? timeframesPayload : (timeframesPayload.data ?? []);
          const uniqueDayKeys = new Set<string>();
          for (const row of timeframeRows) {
            if (!row.start_time) continue;
            const date = new Date(row.start_time);
            if (Number.isNaN(date.getTime())) continue;
            const key = `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(
              date.getDate()
            ).padStart(2, "0")}`;
            uniqueDayKeys.add(key);
          }

          nextCalendarDays = Array.from(uniqueDayKeys)
            .sort()
            .map((key) => {
              const date = new Date(`${key}T00:00:00`);
              return {
                key,
                label: date.toLocaleDateString(undefined, {
                  weekday: "short",
                  month: "short",
                  day: "numeric",
                }),
              };
            });
        }

        if (ignore) return;
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
        setCalendarDays([]);
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
    const nextValue = !(availability[dayIndex]?.[slotIndex] ?? false);
    setCell(dayIndex, slotIndex, nextValue);
    setDragValue(nextValue);
    setIsDragging(true);
  };

  const handleCellMouseEnter = (dayIndex: number, slotIndex: number) => {
    if (!isDragging || dragValue === null) return;
    setCell(dayIndex, slotIndex, dragValue);
  };

  async function handleCsvUpload(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!professorId) {
      setCsvMessage("Missing professor_id in URL.");
      return;
    }
    if (!csvFile) {
      setCsvMessage("Select a CSV file before uploading.");
      return;
    }

    const formData = new FormData();
    formData.append("file", csvFile);
    if (classId) formData.append("class_id", classId);
    setCsvUploading(true);
    setCsvMessage("Uploading CSV...");

    try {
      const response = await fetch(`${backendUrl}/api/events/upload-students-csv`, {
        method: "POST",
        headers: authHeaders,
        body: formData,
      });
      const payload = (await response.json()) as {
        detail?: unknown;
        rows_inserted?: number;
        rows_received?: number;
      };

      if (!response.ok) {
        setCsvMessage(toMessage(payload.detail, "CSV upload failed."));
        return;
      }

      setCsvMessage(
        `Upload successful: inserted ${payload.rows_inserted ?? 0} of ${payload.rows_received ?? 0} rows.`,
      );
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
                          const showHourLine = slotIndex % 4 === 0;
                          return (
                            <button
                              key={`${dayIndex}-${slotIndex}`}
                              type="button"
                              onMouseDown={() => handleCellMouseDown(dayIndex, slotIndex)}
                              onMouseEnter={() => handleCellMouseEnter(dayIndex, slotIndex)}
                              onDragStart={(event) => event.preventDefault()}
                              className={`h-6 border-r border-l border-b border-[#333] ${
                                showHourLine ? "border-t border-t-[#333]" : ""
                              } ${available ? "bg-[#38a000]" : "bg-[#f0d7d9]"}`}
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
            <form onSubmit={handleCsvUpload} className="mt-4 max-w-2xl space-y-3">
              <p className="text-sm font-semibold text-[#2d3d7a] md:text-base">
                File with all students in thesis section:
              </p>
              <p className="text-sm text-[#3b4a7c]">
                Required columns: Student Name, Student ID, Class Level, Preferred Email
              </p>
              <label className="flex cursor-pointer flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed border-[#2f53c4] bg-[#f7f9ff] px-4 py-10 text-center transition hover:bg-[#edf2ff]">
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
            </form>
          ) : null}
        </section>
      </div>
    </main>
  );
}
