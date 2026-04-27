"use client";

import Link from "next/link";
import { Suspense, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";

type SymposiumOption = { id: string; name: string };
type Timeframe = { id: string; start_time: string; end_time: string };
type DepartmentRecord = {
  id: string;
  department_name: string;
  department_head_name: string;
};
type ClassRecord = {
  id: string;
  department_id: string;
};
type PresentationRecord = {
  id: string;
  class_id: string;
  title: string;
  presenterNames: string[];
};
type SymposiumDetails = {
  id: string;
  name: string;
  rooms_available?: number | null;
};

function parseBackendDateTime(value: string) {
  const normalized = value.includes(" ") ? value.replace(" ", "T") : value;
  return new Date(normalized);
}

function normalizeId(value: string) {
  return value.trim().toLowerCase();
}

function dayKey(date: Date) {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, "0");
  const d = String(date.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

function dayLabel(key: string) {
  return new Date(`${key}T00:00:00`).toLocaleDateString(undefined, {
    weekday: "long",
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

function timeLabel(start: string, end: string) {
  const s = parseBackendDateTime(start);
  const e = parseBackendDateTime(end);
  return `${s.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })} - ${e.toLocaleTimeString([], {
    hour: "numeric",
    minute: "2-digit",
  })}`;
}

function HomeContent() {
  const searchParams = useSearchParams();
  const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:8000";
  const backendApiKey = process.env.NEXT_PUBLIC_BACKEND_API_KEY ?? "";
  const authHeaders = useMemo(() => (backendApiKey ? { "X-API-Key": backendApiKey } : undefined), [backendApiKey]);

  const [symposiums, setSymposiums] = useState<SymposiumOption[]>([]);
  const [selectedSymposiumId, setSelectedSymposiumId] = useState("");
  const [timeframes, setTimeframes] = useState<Timeframe[]>([]);
  const [departments, setDepartments] = useState<DepartmentRecord[]>([]);
  const [classes, setClasses] = useState<ClassRecord[]>([]);
  const [presentations, setPresentations] = useState<PresentationRecord[]>([]);
  const [roomsAvailable, setRoomsAvailable] = useState(1);
  const [selectedDay, setSelectedDay] = useState("");
  const [searchQuery, setSearchQuery] = useState("");
  const [locationFilter, setLocationFilter] = useState("");
  const [professorFilter, setProfessorFilter] = useState("");
  const [departmentFilter, setDepartmentFilter] = useState("");
  const [message, setMessage] = useState<string | null>(null);

  const isLoggedIn = Boolean(
    searchParams.get("student_id") ||
      searchParams.get("professor_id") ||
      searchParams.get("department_id") ||
      searchParams.get("user_id")
  );

  useEffect(() => {
    async function loadSymposiums() {
      try {
        const response = await fetch(`${backendUrl}/api/events/symposiums`, { headers: authHeaders });
        const payload = (await response.json().catch(() => ({}))) as { detail?: string; data?: SymposiumOption[] };
        if (!response.ok) throw new Error(payload.detail ?? "Failed to load symposiums.");
        const list = payload.data ?? [];
        setSymposiums(list);
        setSelectedSymposiumId(list[0]?.id ?? "");
      } catch (error) {
        const msg = error instanceof Error ? error.message : "Unknown error";
        setMessage(msg);
      }
    }
    void loadSymposiums();
  }, [authHeaders, backendUrl]);

  useEffect(() => {
    async function loadSymposiumDetails() {
      if (!selectedSymposiumId) {
        setTimeframes([]);
        setDepartments([]);
        setClasses([]);
        setPresentations([]);
        setRoomsAvailable(1);
        setSelectedDay("");
        return;
      }

      try {
        setMessage(null);
        const [symposiumRes, departmentsRes] = await Promise.all([
          fetch(`${backendUrl}/api/events/symposiums/${selectedSymposiumId}`, { headers: authHeaders }),
          fetch(`${backendUrl}/api/events/departments?symposium_id=${encodeURIComponent(selectedSymposiumId)}`, {
            headers: authHeaders,
          }),
        ]);

        const symposiumPayload = (await symposiumRes.json().catch(() => ({}))) as {
          detail?: string;
          symposium?: SymposiumDetails;
          timeframes?: Timeframe[];
        };
        const departmentsPayload = (await departmentsRes.json().catch(() => ({}))) as {
          detail?: string;
          departments?: DepartmentRecord[];
        };

        if (!symposiumRes.ok) throw new Error(symposiumPayload.detail ?? "Failed to load symposium schedule.");

        const list = (symposiumPayload.timeframes ?? []).slice().sort((a, b) => {
          const ta = parseBackendDateTime(a.start_time).getTime();
          const tb = parseBackendDateTime(b.start_time).getTime();
          return ta - tb;
        });
        setTimeframes(list);
        const parsedRooms = Number(symposiumPayload.symposium?.rooms_available ?? 1);
        setRoomsAvailable(Number.isFinite(parsedRooms) && parsedRooms > 0 ? Math.floor(parsedRooms) : 1);

        if (departmentsRes.ok) {
          const departmentRows = departmentsPayload.departments ?? [];
          setDepartments(departmentRows);

          const classResponses = await Promise.all(
            departmentRows.map((department) =>
              fetch(`${backendUrl}/api/events/classes?department_id=${encodeURIComponent(department.id)}`, {
                headers: authHeaders,
              })
            )
          );

          const classPayloads = await Promise.all(
            classResponses.map((response) =>
              response.json().catch(() => ({} as { data?: Array<{ id?: string; department_id?: string }> }))
            )
          );

          const classRows = classPayloads.flatMap((payload, index) => {
            if (!classResponses[index].ok) return [];
            const list: Array<{ id?: string; department_id?: string }> = Array.isArray(payload)
              ? payload
              : (payload.data ?? []);
            return list
              .map((row) => ({
                id: row.id ?? "",
                department_id: row.department_id ?? "",
              }))
              .filter((row): row is ClassRecord => Boolean(row.id && row.department_id));
          });
          setClasses(classRows);

          const [presentationResponses, studentResponses] = await Promise.all([
            Promise.all(
              classRows.map((row) =>
                fetch(`${backendUrl}/api/events/presentations?class_id=${encodeURIComponent(row.id)}`, {
                  headers: authHeaders,
                })
              )
            ),
            Promise.all(
              classRows.map((row) =>
                fetch(`${backendUrl}/api/events/students?class_id=${encodeURIComponent(row.id)}`, {
                  headers: authHeaders,
                })
              )
            ),
          ]);

          const [presentationPayloads, studentPayloads] = await Promise.all([
            Promise.all(
              presentationResponses.map((response) =>
                response.json().catch(
                  () =>
                    ({} as {
                      data?: Array<{
                        id?: string;
                        class_id?: string;
                        title?: string;
                        presenting_students?: Array<{ id?: string; student_id?: string; name?: string }>;
                      }>;
                    })
                )
              )
            ),
            Promise.all(
              studentResponses.map((response) =>
                response.json().catch(
                  () => ({} as { data?: Array<{ id?: string; name?: string; class_id?: string }> })
                )
              )
            ),
          ]);

          const studentRows = studentPayloads.flatMap((payload, index) => {
            if (!studentResponses[index].ok) return [];
            const list: Array<{ id?: string; name?: string; class_id?: string }> = Array.isArray(payload)
              ? payload
              : (payload.data ?? []);
            return list
              .map((row) => ({
                id: row.id ?? "",
                name: row.name?.trim() ?? "",
              }))
              .filter((row): row is { id: string; name: string } => Boolean(row.id && row.name));
          });
          const studentNameById = new Map(studentRows.map((row) => [normalizeId(row.id), row.name]));

          const presentationRows = presentationPayloads.flatMap((payload, index) => {
            if (!presentationResponses[index].ok) return [];
            const list: Array<{
              id?: string;
              class_id?: string;
              title?: string;
              presenting_students?: Array<{ id?: string; student_id?: string; name?: string }>;
            }> = Array.isArray(payload)
              ? payload
              : (payload.data ?? []);
            return list
              .map((row) => {
                const presenterNames = (row.presenting_students ?? [])
                  .map((student) => {
                    const directName = student.name?.trim() ?? "";
                    if (directName) return directName;
                    const studentId = student.id ?? student.student_id ?? "";
                    return studentNameById.get(normalizeId(studentId)) ?? "";
                  })
                  .filter((name) => name.length > 0);
                return {
                  id: row.id ?? "",
                  class_id: row.class_id ?? "",
                  title: row.title?.trim() ?? "",
                  presenterNames: Array.from(new Set(presenterNames)),
                };
              })
              .filter((row): row is PresentationRecord => Boolean(row.id && row.class_id));
          });
          setPresentations(presentationRows);
        } else {
          setDepartments([]);
          setClasses([]);
          setPresentations([]);
        }

        const days = Array.from(new Set(list.map((item) => dayKey(parseBackendDateTime(item.start_time)))));
        setSelectedDay(days[0] ?? "");
        if (list.length === 0) setMessage("No presentation times posted for this symposium yet.");
      } catch (error) {
        const msg = error instanceof Error ? error.message : "Unknown error";
        setMessage(msg);
        setTimeframes([]);
        setDepartments([]);
        setClasses([]);
        setPresentations([]);
        setRoomsAvailable(1);
      }
    }
    void loadSymposiumDetails();
  }, [authHeaders, backendUrl, selectedSymposiumId]);

  const days = useMemo(
    () => Array.from(new Set(timeframes.map((item) => dayKey(parseBackendDateTime(item.start_time))))),
    [timeframes]
  );

  const visibleRows = useMemo(() => {
    return timeframes.filter((item) => {
      const start = parseBackendDateTime(item.start_time);
      const end = parseBackendDateTime(item.end_time);
      if (Number.isNaN(start.getTime()) || Number.isNaN(end.getTime()) || end <= start) return false;
      return dayKey(start) === selectedDay;
    });
  }, [selectedDay, timeframes]);

  const cards = useMemo(
    () => {
      const departmentById = new Map(departments.map((department) => [department.id, department]));
      const departmentIdByClassId = new Map(classes.map((classRow) => [classRow.id, classRow.department_id]));

      const cardsFromPresentations = presentations
        .map((presentation, index) => {
          const departmentId = departmentIdByClassId.get(presentation.class_id);
          const department = departmentId ? departmentById.get(departmentId) : undefined;
          if (!department) return null;
          return {
            department,
            timeframe: visibleRows[index] ?? null,
            room: `Room ${(index % roomsAvailable) + 1}`,
            title: presentation.title || `${department.department_name} Presentation`,
            presenterNames: Array.isArray(presentation.presenterNames) ? presentation.presenterNames : [],
          };
        })
        .filter(
          (
            card
          ): card is {
            department: DepartmentRecord;
            timeframe: Timeframe;
            room: string;
            title: string;
            presenterNames: string[];
          } => Boolean(card)
        );

      if (cardsFromPresentations.length > 0) return cardsFromPresentations;

      return departments.map((department, index) => ({
        department,
        timeframe: visibleRows[index] ?? null,
        room: `Room ${(index % roomsAvailable) + 1}`,
        title: `${department.department_name} Presentation`,
        presenterNames: [],
      }));
    },
    [classes, departments, presentations, roomsAvailable, visibleRows]
  );

  const filterOptions = useMemo(() => {
    return {
      locations: Array.from(new Set(cards.map((card) => card.room))).sort(),
      professors: Array.from(new Set(cards.map((card) => card.department.department_head_name))).sort(),
      departments: Array.from(new Set(cards.map((card) => card.department.department_name))).sort(),
    };
  }, [cards]);

  const filteredCards = useMemo(() => {
    const query = searchQuery.trim().toLowerCase();
    return cards.filter((card) => {
      const haystack = [
        card.title,
        ...(card.presenterNames ?? []),
        card.department.department_name,
        card.department.department_head_name,
        card.room,
      ]
        .join(" ")
        .toLowerCase();
      const matchesQuery = query ? haystack.includes(query) : true;
      const matchesLocation = locationFilter ? card.room === locationFilter : true;
      const matchesProfessor = professorFilter ? card.department.department_head_name === professorFilter : true;
      const matchesDepartment = departmentFilter ? card.department.department_name === departmentFilter : true;
      return matchesQuery && matchesLocation && matchesProfessor && matchesDepartment;
    });
  }, [cards, departmentFilter, locationFilter, professorFilter, searchQuery]);

  return (
    <main className="min-h-screen bg-[#f5f5f5] px-4 py-6">
      <div className="mx-auto w-full max-w-6xl">
        <div className="mb-4 flex justify-end">
          <Link
            href="/pages?view=login"
            className="rounded-md border border-[#0f766e] bg-[#0f766e] px-4 py-2 text-sm font-semibold text-white transition hover:border-[#0b5f59] hover:bg-[#0b5f59]"
          >
            Login
          </Link>
        </div>
        <div className="mb-4 flex flex-wrap justify-center gap-2">
          <Link
            href="/pages?view=admin"
            className="rounded-md border border-[#9ca3af] bg-[#e5e7eb] px-4 py-2 text-sm font-semibold text-[#1f2937] transition hover:border-[#0f33a8] hover:bg-[#0f33a8] hover:text-white"
          >
            Admin Page
          </Link>
          <Link
            href="/pages?view=department-head"
            className="rounded-md border border-[#9ca3af] bg-[#e5e7eb] px-5 py-2 text-sm font-semibold text-[#1f2937] transition hover:border-[#0f33a8] hover:bg-[#0f33a8] hover:text-white md:text-base"
          >
            Department Head Page
          </Link>
          <Link
            href="/pages?view=professor"
            className="rounded-md border border-[#9ca3af] bg-[#e5e7eb] px-4 py-2 text-sm font-semibold text-[#1f2937] transition hover:border-[#0f33a8] hover:bg-[#0f33a8] hover:text-white"
          >
            Professor Page
          </Link>
          <Link
            href="/pages?view=student"
            className="rounded-md border border-[#9ca3af] bg-[#e5e7eb] px-4 py-2 text-sm font-semibold text-[#1f2937] transition hover:border-[#0f33a8] hover:bg-[#0f33a8] hover:text-white"
          >
            Student Page
          </Link>
        </div>

        <h1 className="mb-4 text-center text-4xl font-extrabold tracking-wide text-black md:text-6xl">OCC THESIS SYMPOSIUM</h1>

        <div className="mb-4 rounded-xl border border-[#b9c6f8] bg-white p-4">
          <label className="block text-xs font-bold uppercase tracking-wide text-[#1b338f]">Select Symposium</label>
          <select
            value={selectedSymposiumId}
            onChange={(event) => setSelectedSymposiumId(event.target.value)}
            className="mt-2 w-full rounded-lg border-2 border-[#1635a7] bg-white px-3 py-2.5 text-xl text-black"
          >
            {symposiums.length === 0 ? <option value="">Select an event...</option> : null}
            {symposiums.map((symposium) => (
              <option key={symposium.id} value={symposium.id}>
                {symposium.name}
              </option>
            ))}
          </select>
        </div>

        <section className="overflow-hidden rounded-lg border-4 border-[#1635a7] bg-[#1635a7]">
          <div className="grid grid-cols-1 md:grid-cols-5">
            {days.map((day) => {
              const active = day === selectedDay;
              return (
                <button
                  key={day}
                  type="button"
                  onClick={() => setSelectedDay(day)}
                  className={`border-b border-r border-[#1635a7] px-4 py-3 text-left text-lg leading-tight ${
                    active ? "bg-white text-[#111]" : "bg-[#1635a7] text-white"
                  }`}
                >
                  {dayLabel(day)}
                </button>
              );
            })}
          </div>

          <div className="grid grid-cols-1 md:grid-cols-[1fr_auto]">
            <button type="button" className="border-r border-t border-[#1635a7] bg-white px-4 py-2 text-xl font-semibold text-[#111]">
              Filter
            </button>
            {isLoggedIn ? (
              <button type="button" className="border-t border-[#1635a7] bg-white px-6 py-2 text-xl font-semibold text-[#111]">
                My Itinerary
              </button>
            ) : null}
          </div>
        </section>

        <div className="mt-2 grid grid-cols-1 gap-2 md:grid-cols-2">
          <input
            value={searchQuery}
            onChange={(event) => setSearchQuery(event.target.value)}
            placeholder="Search title, professor, or department"
            className="rounded-full border border-[#d7b980] bg-white px-4 py-2 text-xl"
          />
          <div className="rounded-3xl border border-[#d7b980] bg-white p-3 text-lg">
            <div className="grid grid-cols-1 gap-2 md:grid-cols-3">
              <select
                value={locationFilter}
                onChange={(event) => setLocationFilter(event.target.value)}
                className="rounded-md border border-[#ddd] bg-white px-2 py-2 text-base"
              >
                <option value="">Location</option>
                {filterOptions.locations.map((option) => (
                  <option key={option} value={option}>
                    {option}
                  </option>
                ))}
              </select>
              <select
                value={professorFilter}
                onChange={(event) => setProfessorFilter(event.target.value)}
                className="rounded-md border border-[#ddd] bg-white px-2 py-2 text-base"
              >
                <option value="">Advisor/Professor</option>
                {filterOptions.professors.map((option) => (
                  <option key={option} value={option}>
                    {option}
                  </option>
                ))}
              </select>
              <select
                value={departmentFilter}
                onChange={(event) => setDepartmentFilter(event.target.value)}
                className="rounded-md border border-[#ddd] bg-white px-2 py-2 text-base"
              >
                <option value="">Department</option>
                {filterOptions.departments.map((option) => (
                  <option key={option} value={option}>
                    {option}
                  </option>
                ))}
              </select>
            </div>
          </div>
        </div>

        <p className="mt-4 text-2xl font-semibold text-[#111]">Time Zone: {Intl.DateTimeFormat().resolvedOptions().timeZone}</p>

        <div className="mt-4 space-y-4">
          {message ? <p className="text-sm font-semibold text-[#9a1f1f]">{message}</p> : null}
          {!message && departments.length === 0 ? (
            <p className="text-sm font-semibold text-[#555]">No departments are registered for this symposium yet.</p>
          ) : null}
          {!message && departments.length > 0 && !selectedDay ? (
            <p className="text-sm font-semibold text-[#555]">Select a symposium day to view presentations.</p>
          ) : null}
          {!message && departments.length > 0 && selectedDay && filteredCards.length === 0 ? (
            <p className="text-sm font-semibold text-[#555]">No matches found for your search.</p>
          ) : null}

          {filteredCards.map(({ department, timeframe, room, title, presenterNames }, index) => {
            const dept = department.department_name;
            const prof = department.department_head_name;
            const safePresenterNames = presenterNames ?? [];
            return (
              <article key={`${department.id}-${selectedDay || "no-day"}-${index}`} className="overflow-hidden rounded-md border border-[#d6b676] bg-white">
                <div className="bg-[#1635a7] px-4 py-2 text-2xl font-semibold text-white">
                  {timeframe ? timeLabel(timeframe.start_time, timeframe.end_time) : "Time TBD"}
                </div>
                <div className="px-4 py-3">
                  <h3 className="text-3xl font-extrabold text-[#111]">{title}</h3>
                  <div className="mt-2 flex flex-wrap gap-x-6 gap-y-1 text-xl text-[#111]">
                    <span>{room}</span>
                    {safePresenterNames.length > 0 ? (
                      safePresenterNames.map((name) => <span key={`${department.id}-${title}-${name}`}>{name}</span>)
                    ) : (
                      <span>Presenters TBD</span>
                    )}
                    <span>{dept}</span>
                    <span>{prof}</span>
                  </div>
                </div>
              </article>
            );
          })}
        </div>
      </div>
    </main>
  );
}

export default function Home() {
  return (
    <Suspense fallback={<main className="min-h-screen bg-[#f5f5f5] px-4 py-8">Loading...</main>}>
      <HomeContent />
    </Suspense>
  );
}
