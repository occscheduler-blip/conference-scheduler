"use client";

import Link from "next/link";
import { Suspense, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import type {
  ClassRecord,
  DepartmentRecord,
  PresentationRecord,
  SymposiumDetails,
  SymposiumOption,
  Timeframe,
} from "./types";
import { parseBackendDateTime, normalizeId, dayKey, dayLabel, timeLabel } from "../lib/utils";
import { apiFetch } from "../lib/api";

type ItineraryDetailItem = {
  presentation_id: string;
  title: string;
  room: string | null;
  presenter_names: string[];
  department_name: string;
  department_head_name: string;
  symposium_id: string;
  symposium_name: string;
  start_time: string | null;
  end_time: string | null;
};

function HomeContent({ isAttendee, attendeeId, authToken, onSignOut }: { isAttendee?: boolean; attendeeId?: string; authToken?: string; onSignOut?: () => void }) {
  const searchParams = useSearchParams();

  const [symposia, setSymposia] = useState<SymposiumOption[]>([]);
  const [selectedSymposiumId, setSelectedSymposiumId] = useState("");
  const [timeframes, setTimeframes] = useState<Timeframe[]>([]);
  const [departments, setDepartments] = useState<DepartmentRecord[]>([]);
  const [classes, setClasses] = useState<ClassRecord[]>([]);
  const [presentations, setPresentations] = useState<PresentationRecord[]>([]);
  const [roomsAvailable, setRoomsAvailable] = useState(1);
  const [selectedDay, setSelectedDay] = useState("");
  const [dayPage, setDayPage] = useState(0);
  const [searchQuery, setSearchQuery] = useState("");
  const [locationFilter, setLocationFilter] = useState("");
  const [professorFilter, setProfessorFilter] = useState("");
  const [departmentFilter, setDepartmentFilter] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [viewMode, setViewMode] = useState<"list" | "calendar">("list");
  const [itinerary, setItinerary] = useState<Set<string>>(new Set());
  const [showItinerary, setShowItinerary] = useState(false);
  const [itineraryDetails, setItineraryDetails] = useState<ItineraryDetailItem[] | null>(null);
  const [itineraryLoading, setItineraryLoading] = useState(false);

  const authHeaders = authToken ? { Authorization: `Bearer ${authToken}` } : {};

  // Load itinerary from DB on mount
  useEffect(() => {
    if (!attendeeId || !authToken) return;
    fetch(`/api/backend/api/auth/attendee/itinerary`, {
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${authToken}` },
    })
      .then((r) => r.json())
      .then((ids: unknown) => {
        if (Array.isArray(ids)) setItinerary(new Set(ids as string[]));
      })
      .catch(() => {});
  }, [attendeeId, authToken]);

  const toggleItinerary = (presentationId: string) => {
    const isBookmarked = itinerary.has(presentationId);
    // Optimistic update
    setItinerary((prev) => {
      const next = new Set(prev);
      if (isBookmarked) next.delete(presentationId);
      else next.add(presentationId);
      return next;
    });
    // Persist to DB
    const method = isBookmarked ? "DELETE" : "POST";
    fetch(`/api/backend/api/auth/attendee/itinerary/${presentationId}`, {
      method,
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${authToken}` },
    }).catch(() => {
      // Revert on failure
      setItinerary((prev) => {
        const next = new Set(prev);
        if (isBookmarked) next.add(presentationId);
        else next.delete(presentationId);
        return next;
      });
    });
  };

  const openItinerary = () => {
    setShowItinerary(true);
    setItineraryLoading(true);
    setItineraryDetails(null);
    fetch(`/api/backend/api/auth/attendee/itinerary/details`, {
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${authToken}` },
    })
      .then((r) => r.json())
      .then((data: unknown) => {
        if (Array.isArray(data)) setItineraryDetails(data as ItineraryDetailItem[]);
        else setItineraryDetails([]);
      })
      .catch(() => setItineraryDetails([]))
      .finally(() => setItineraryLoading(false));
  };

  const [popupCard, setPopupCard] = useState<{
    title: string;
    timeframe: Timeframe | null;
    room: string;
    presenterNames: string[];
    department: DepartmentRecord;
    presentationId: string;
  } | null>(null);

  const isLoggedIn = Boolean(
    searchParams.get("student_id") ||
      searchParams.get("professor_id") ||
      searchParams.get("department_id") ||
      searchParams.get("user_id")
  );

  useEffect(() => {
    async function loadSymposia() {
      try {
        const list = await apiFetch<SymposiumOption>("/api/events/symposiums");
        setSymposia(list);
        setSelectedSymposiumId(list[0]?.id ?? "");
      } catch (error) {
        const msg = error instanceof Error ? error.message : "Unknown error";
        setMessage(msg);
      }
    }
    void loadSymposia();
  }, []);

  // AI template: loads all symposium schedule data in parallel — departments, classes, presentations, and students — and joins them for display.
  useEffect(() => {
    async function loadSymposiumDetails() {
      if (!selectedSymposiumId) {
        setTimeframes([]);
        setDepartments([]);
        setClasses([]);
        setPresentations([]);
        setRoomsAvailable(1);
        setSelectedDay("");
        setDayPage(0);
        return;
      }

      try {
        setMessage(null);

        // Symposium detail returns { symposium, timeframes } — non-standard shape, so use apiFetch
        // for the departments call and a raw fetch for the symposium detail.
        const symposiumRes = await fetch(`/api/backend/api/events/symposiums/${selectedSymposiumId}`);
        const symposiumPayload = (await symposiumRes.json().catch(() => ({}))) as {
          detail?: string;
          symposium?: SymposiumDetails;
          timeframes?: Timeframe[];
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

        let departmentRows: DepartmentRecord[] = [];
        try {
          departmentRows = await apiFetch<DepartmentRecord>(
            `/api/events/departments?symposium_id=${encodeURIComponent(selectedSymposiumId)}`
          );
        } catch {
          // Departments endpoint failed gracefully — continue with empty list
        }

        if (departmentRows.length > 0) {
          setDepartments(departmentRows);

          const departmentIdParam = departmentRows.map((d) => d.id).join(",");
          let classRows: ClassRecord[] = [];
          try {
            classRows = await apiFetch<ClassRecord>(
              `/api/events/classes?department_id=${encodeURIComponent(departmentIdParam)}`
            );
          } catch {
            classRows = [];
          }
          setClasses(classRows);

          type RawPresentation = {
            id?: string;
            class_id?: string;
            title?: string;
            room?: number | null;
            presenting_students?: Array<{ id?: string; student_id?: string; name?: string }>;
          };
          type RawStudent = { id?: string; name?: string; class_id?: string };

          const classIdParam = classRows.map((c) => c.id).join(",");
          const [rawPresentations, rawStudents] = classIdParam
            ? await Promise.all([
                apiFetch<RawPresentation>(
                  `/api/events/presentations?class_id=${encodeURIComponent(classIdParam)}`
                ).catch(() => [] as RawPresentation[]),
                apiFetch<RawStudent>(
                  `/api/events/students?class_id=${encodeURIComponent(classIdParam)}`
                ).catch(() => [] as RawStudent[]),
              ])
            : [[] as RawPresentation[], [] as RawStudent[]];

          const studentRows = rawStudents
            .map((row) => ({
              id: row.id ?? "",
              name: row.name?.trim() ?? "",
            }))
            .filter((row): row is { id: string; name: string } => Boolean(row.id && row.name));
          const studentNameById = new Map(studentRows.map((row) => [normalizeId(row.id), row.name]));

          // Bulk-fetch scheduled timeframes for all presentations in a single call
          const presentationIdParam = rawPresentations
            .map((p) => p.id ?? "")
            .filter((id) => id.length > 0)
            .join(",");
          let allPresentationTimeframes: Timeframe[] = [];
          if (presentationIdParam) {
            try {
              allPresentationTimeframes = await apiFetch<Timeframe>(
                `/api/events/timeframes?linked_id=${encodeURIComponent(presentationIdParam)}`
              );
            } catch {
              allPresentationTimeframes = [];
            }
          }
          const timeframeByLinkedId = new Map<string, Timeframe>();
          for (const tf of allPresentationTimeframes) {
            const key = normalizeId(tf.linked_id ?? "");
            if (key && !timeframeByLinkedId.has(key)) {
              timeframeByLinkedId.set(key, tf);
            }
          }

          const presentationRows = rawPresentations
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
                room: row.room ?? null,
                timeframe: timeframeByLinkedId.get(normalizeId(row.id ?? "")) ?? null,
              };
            })
            .filter((row): row is PresentationRecord => Boolean(row.id && row.class_id));
          setPresentations(presentationRows);
        } else {
          setDepartments([]);
          setClasses([]);
          setPresentations([]);
        }

        const days = Array.from(new Set(list.map((item) => dayKey(parseBackendDateTime(item.start_time)))));
        setSelectedDay(days[0] ?? "");
        setDayPage(0);
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
  }, [selectedSymposiumId]);

  // AI template: derived state — groups presentations into display cards, builds filter options, and applies search/filter logic.
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
        .map((presentation) => {
          const departmentId = departmentIdByClassId.get(presentation.class_id);
          const department = departmentId ? departmentById.get(departmentId) : undefined;
          if (!department) return null;
          const scheduled = presentation.timeframe != null;
          const tf = presentation.timeframe ?? null;
          const room = presentation.room != null ? `Room ${presentation.room + 1}` : "Room TBD";
          return {
            department,
            timeframe: tf,
            room,
            title: presentation.title || `${department.department_name} Presentation`,
            presenterNames: Array.isArray(presentation.presenterNames) ? presentation.presenterNames : [],
            scheduled,
            presentationId: presentation.id,
          };
        })
        .filter(
          (
            card
          ): card is {
            department: DepartmentRecord;
            timeframe: Timeframe | null;
            room: string;
            title: string;
            presenterNames: string[];
            scheduled: boolean;
            presentationId: string;
          } => Boolean(card)
        );

      if (cardsFromPresentations.length > 0) return cardsFromPresentations;

      return departments.map((department) => ({
        department,
        timeframe: null as Timeframe | null,
        room: "Room TBD",
        title: `${department.department_name} Presentation`,
        presenterNames: [],
        scheduled: false,
        presentationId: "",
      }));
    },
    [classes, departments, presentations]
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
      // Filter by selected day using the card's own timeframe
      if (selectedDay && card.timeframe) {
        const cardDay = dayKey(parseBackendDateTime(card.timeframe.start_time));
        if (cardDay !== selectedDay) return false;
      }
      // Cards with no timeframe (unscheduled) always show
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
  }, [cards, departmentFilter, locationFilter, professorFilter, searchQuery, selectedDay]);


  return (
    <main className="min-h-screen bg-[#f5f5f5] px-4 py-6">
      <div className="mx-auto w-full max-w-6xl">
        <div className="relative mb-4 flex items-center justify-center">
          <h1 className="text-center text-4xl font-extrabold tracking-wide text-black md:text-6xl">OCC THESIS SYMPOSIUM</h1>
          <div className="absolute right-0 flex items-center gap-3">
            {isAttendee ? (
              <button
                type="button"
                onClick={onSignOut}
                className="rounded-md border border-[#0f33a8] bg-white px-4 py-2 text-sm font-semibold text-[#0f33a8] transition hover:bg-[#eef3ff] md:text-base"
              >
                Sign Out
              </button>
            ) : (
              <Link
                href="/pages?view=login"
                className="rounded-md border border-[#0f33a8] bg-[#0f33a8] px-6 py-2 text-sm font-semibold text-white transition hover:bg-[#1237af] md:text-base"
              >
                Sign In
              </Link>
            )}
          </div>
        </div>

        <div className="mb-4 rounded-xl border border-[#b9c6f8] bg-white p-4">
          <label className="block text-xs font-bold uppercase tracking-wide text-[#1b338f]">Select Symposium</label>
          <select
            value={selectedSymposiumId}
            onChange={(event) => setSelectedSymposiumId(event.target.value)}
            className="mt-2 w-full rounded-lg border-2 border-[#1635a7] bg-white px-3 py-2.5 text-xl text-black"
          >
            {symposia.length === 0 ? <option value="">Select an event...</option> : null}
            {symposia.map((symposium) => (
              <option key={symposium.id} value={symposium.id}>
                {symposium.name}
              </option>
            ))}
          </select>
        </div>
        {isAttendee ? (
          <button
            type="button"
            onClick={openItinerary}
            className="mb-4 flex w-full items-center justify-center gap-2 rounded-lg bg-[#1635a7] px-4 py-2.5 text-base font-semibold text-white transition hover:bg-[#0b2a8d]"
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor"><path d="M5 3h14a1 1 0 0 1 1 1v17l-8-4-8 4V4a1 1 0 0 1 1-1z"/></svg>
            My Itinerary{itinerary.size > 0 ? ` (${itinerary.size})` : ""}
          </button>
        ) : null}

        <div className="mt-2 grid grid-cols-1 gap-2 md:grid-cols-2">
          <input
            value={searchQuery}
            onChange={(event) => setSearchQuery(event.target.value)}
            placeholder="Search title, student, professor, or department"
            className="rounded-full border border-[#d7b980] bg-white px-4 py-2 text-xl text-[#111]"
          />
          <div className="rounded-3xl border border-[#d7b980] bg-white p-3 text-lg">
            <div className="grid grid-cols-1 gap-2 md:grid-cols-3">
              <select
                value={locationFilter}
                onChange={(event) => setLocationFilter(event.target.value)}
                className="rounded-md border border-[#ddd] bg-white px-2 py-2 text-base text-[#111]"
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
                className="rounded-md border border-[#ddd] bg-white px-2 py-2 text-base text-[#111]"
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
                className="rounded-md border border-[#ddd] bg-white px-2 py-2 text-base text-[#111]"
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

        <div className="mt-2 flex items-center justify-between">
          <p className="text-2xl font-semibold text-[#111]">Time Zone: {Intl.DateTimeFormat().resolvedOptions().timeZone}</p>
          <div className="flex items-center gap-2">
          {/* List / Calendar view toggle */}
          {selectedDay ? (
            <div className="flex overflow-hidden rounded-lg border-2 border-[#1635a7]">
              <button
                type="button"
                onClick={() => setViewMode("list")}
                className={`px-3 py-2 text-sm font-semibold ${
                  viewMode === "list" ? "bg-white text-[#111]" : "bg-[#1635a7] text-white hover:bg-[#0b2a8d]"
                }`}
                title="List view"
              >
                <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
                  <rect x="1" y="2" width="14" height="2" rx="1"/>
                  <rect x="1" y="7" width="14" height="2" rx="1"/>
                  <rect x="1" y="12" width="14" height="2" rx="1"/>
                </svg>
              </button>
              <button
                type="button"
                onClick={() => setViewMode("calendar")}
                className={`px-3 py-2 text-sm font-semibold ${
                  viewMode === "calendar" ? "bg-white text-[#111]" : "bg-[#1635a7] text-white hover:bg-[#0b2a8d]"
                }`}
                title="Calendar view"
              >
                <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
                  <rect x="1" y="1" width="6" height="6" rx="1"/>
                  <rect x="9" y="1" width="6" height="6" rx="1"/>
                  <rect x="1" y="9" width="6" height="6" rx="1"/>
                  <rect x="9" y="9" width="6" height="6" rx="1"/>
                </svg>
              </button>
            </div>
          ) : null}
          </div>
        </div>

        <section className="mt-2 overflow-hidden rounded-lg border-4 border-[#1635a7] bg-[#1635a7]">
          <div className="flex items-stretch">
            {days.length > 4 ? (
              <button
                type="button"
                onClick={() => setDayPage((p) => p - 1)}
                disabled={dayPage === 0}
                className="flex items-center justify-center px-3 text-white disabled:opacity-30 hover:bg-[#0b2a8d]"
                aria-label="Previous days"
              >
                &#8592;
              </button>
            ) : null}
            <div className="grid flex-1 grid-cols-1 md:grid-cols-4">
              {days.slice(dayPage * 4, (dayPage + 1) * 4).map((day) => {
                const active = day === selectedDay;
                return (
                  <button
                    key={day}
                    type="button"
                    onClick={() => setSelectedDay(day)}
                    className={`whitespace-nowrap border-b border-r border-[#1635a7] px-4 py-3 text-left text-lg leading-tight ${
                      active ? "bg-white text-[#111]" : "bg-[#1635a7] text-white"
                    }`}
                  >
                    {dayLabel(day)}
                  </button>
                );
              })}
            </div>
            {days.length > 4 ? (
              <button
                type="button"
                onClick={() => setDayPage((p) => p + 1)}
                disabled={(dayPage + 1) * 4 >= days.length}
                className="flex items-center justify-center px-3 text-white disabled:opacity-30 hover:bg-[#0b2a8d]"
                aria-label="Next days"
              >
                &#8594;
              </button>
            ) : null}
          </div>

        </section>

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

          {viewMode === "list" ? filteredCards.map(({ department, timeframe, room, title, presenterNames, presentationId }, index) => {
            const dept = department.department_name;
            const prof = department.department_head_name;
            const safePresenterNames = presenterNames ?? [];
            const cardKey = presentationId;
            const bookmarked = itinerary.has(cardKey);
            return (
              <article key={`${department.id}-${selectedDay || "no-day"}-${index}`} className="overflow-hidden rounded-md border border-[#d6b676] bg-white">
                <div className="bg-[#1635a7] px-4 py-2 text-2xl font-semibold text-white">
                  {timeframe ? timeLabel(timeframe.start_time, timeframe.end_time) : "Time TBD"}
                </div>
                <div className="flex items-start px-4 py-3">
                  <div className="flex-1">
                    <h3 className="text-3xl font-extrabold text-[#111]">
                      <button
                        type="button"
                        onClick={() => setPopupCard({ title, timeframe, room, presenterNames: safePresenterNames, department, presentationId })}
                        className="text-left underline hover:text-[#1635a7]"
                      >
                        {title}
                      </button>
                    </h3>
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
                  {isAttendee ? (
                    <button
                      type="button"
                      onClick={() => toggleItinerary(cardKey)}
                      title={bookmarked ? "Remove from itinerary" : "Add to itinerary"}
                      className="ml-4 mt-1 shrink-0 text-[#1635a7] transition hover:scale-110"
                    >
                      {bookmarked ? (
                        <svg width="28" height="28" viewBox="0 0 24 24" fill="currentColor"><path d="M5 3h14a1 1 0 0 1 1 1v17l-8-4-8 4V4a1 1 0 0 1 1-1z"/></svg>
                      ) : (
                        <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M5 3h14a1 1 0 0 1 1 1v17l-8-4-8 4V4a1 1 0 0 1 1-1z"/></svg>
                      )}
                    </button>
                  ) : null}
                </div>
              </article>
            );
          }) : null}

          {viewMode === "calendar" && selectedDay && visibleRows.length > 0 ? (() => {
            const SLOT_HEIGHT = 24;
            const BLOCK_COLORS = [
              { bg: "#1635a7", text: "#fff" },
              { bg: "#2e7d32", text: "#fff" },
              { bg: "#c62828", text: "#fff" },
              { bg: "#6a1b9a", text: "#fff" },
              { bg: "#ef6c00", text: "#fff" },
              { bg: "#00838f", text: "#fff" },
            ];

            const calendarRows = visibleRows;

            // Compute active slots from symposium timeframes for this day
            const activeSlots = new Set<number>();
            for (const tf of calendarRows) {
              const s = parseBackendDateTime(tf.start_time);
              const e = parseBackendDateTime(tf.end_time);
              const startSlot = Math.floor((s.getUTCHours() * 60 + s.getUTCMinutes() - 9 * 60) / 15);
              const endSlot = Math.ceil((e.getUTCHours() * 60 + e.getUTCMinutes() - 9 * 60) / 15);
              for (let i = startSlot; i < endSlot; i++) activeSlots.add(i);
            }
            const minSlot = activeSlots.size > 0 ? Math.min(...activeSlots) : 0;
            const maxSlot = activeSlots.size > 0 ? Math.max(...activeSlots) + 1 : 36;
            const visibleSlotCount = maxSlot - minSlot;

            const formatTimeLabel = (slotIndex: number) => {
              const totalMinutes = 9 * 60 + slotIndex * 15;
              const h = Math.floor(totalMinutes / 60);
              const m = totalMinutes % 60;
              const ampm = h >= 12 ? "PM" : "AM";
              const hour = h > 12 ? h - 12 : h === 0 ? 12 : h;
              return `${hour}:${String(m).padStart(2, "0")} ${ampm}`;
            };

            // Build color map by presentation id
            const colorMap = new Map<string, { bg: string; text: string }>();
            filteredCards.forEach((card, i) => {
              colorMap.set(card.title + card.department.id, BLOCK_COLORS[i % BLOCK_COLORS.length]);
            });

            const scheduledCards = filteredCards.filter((c) => {
              if (!c.timeframe || c.room === "Room TBD") return false;
              return true;
            });

            return (
              <div className="overflow-x-auto rounded-lg border border-[#d8e2ff] bg-white">
                <div
                  className="grid"
                  style={{
                    gridTemplateColumns: `72px repeat(${roomsAvailable}, minmax(140px, 1fr))`,
                    gridTemplateRows: `auto repeat(${visibleSlotCount}, ${SLOT_HEIGHT}px)`,
                  }}
                >
                  {/* Header row */}
                  <div
                    className="border-b border-r border-[#d8e2ff] bg-[#f0f4ff] px-2 py-2 text-xs font-bold uppercase text-[#2d3d7a]"
                    style={{ gridRow: 1, gridColumn: 1 }}
                  >
                    Time
                  </div>
                  {Array.from({ length: roomsAvailable }, (_, i) => (
                    <div
                      key={i}
                      className="whitespace-nowrap border-b border-r border-[#d8e2ff] bg-[#f0f4ff] px-2 py-2 text-center text-xs font-bold uppercase text-[#2d3d7a] last:border-r-0"
                      style={{ gridRow: 1, gridColumn: i + 2 }}
                    >
                      Room {i + 1}
                    </div>
                  ))}

                  {/* Time slot background cells */}
                  {Array.from({ length: visibleSlotCount }, (_, i) => {
                    const slotIndex = minSlot + i;
                    const showLabel = slotIndex % 2 === 0;
                    const gridRow = i + 2;
                    return (
                      <div key={`time-${slotIndex}`} className="contents">
                        <div
                          className={`flex items-center justify-end border-b border-r border-[#e5e7eb] px-1 text-[11px] leading-none text-[#888] ${
                            slotIndex % 4 === 0 ? "bg-[#f9fafb]" : "bg-white"
                          }`}
                          style={{ gridRow, gridColumn: 1 }}
                        >
                          {showLabel ? formatTimeLabel(slotIndex) : ""}
                        </div>
                        {Array.from({ length: roomsAvailable }, (_, roomIdx) => (
                          <div
                            key={roomIdx}
                            className={`border-b border-r border-[#e5e7eb] last:border-r-0 ${
                              slotIndex % 4 === 0 ? "bg-[#f9fafb]" : "bg-white"
                            }`}
                            style={{ gridRow, gridColumn: roomIdx + 2 }}
                          />
                        ))}
                      </div>
                    );
                  })}

                  {/* Presentation blocks */}
                  {scheduledCards.map((card, idx) => {
                    if (!card.timeframe) return null;
                    const roomNum = parseInt(card.room.replace(/\D/g, ""), 10) - 1;
                    if (isNaN(roomNum) || roomNum < 0) return null;

                    const start = parseBackendDateTime(card.timeframe.start_time);
                    const end = parseBackendDateTime(card.timeframe.end_time);
                    const startMinutes = start.getUTCHours() * 60 + start.getUTCMinutes();
                    const endMinutes = end.getUTCHours() * 60 + end.getUTCMinutes();
                    const startSlotRaw = (startMinutes - 9 * 60) / 15;
                    const endSlotRaw = (endMinutes - 9 * 60) / 15;

                    const gridRowStart = Math.floor(startSlotRaw - minSlot) + 2;
                    const gridRowEnd = Math.ceil(endSlotRaw - minSlot) + 2;
                    const gridCol = roomNum + 2;

                    const fracStart = (startSlotRaw - minSlot) - Math.floor(startSlotRaw - minSlot);
                    const verticalInset = 1;
                    const topOffset = fracStart * SLOT_HEIGHT + verticalInset;
                    const blockHeight = Math.max(8, (endSlotRaw - startSlotRaw) * SLOT_HEIGHT - verticalInset * 2);
                    const durationSlots = endSlotRaw - startSlotRaw;

                    const colorKey = card.title + card.department.id;
                    const color = colorMap.get(colorKey) ?? BLOCK_COLORS[idx % BLOCK_COLORS.length];
                    const safePresenterNames = card.presenterNames ?? [];

                    return (
                      <div
                        key={`${card.department.id}-${idx}`}
                        onClick={() => setPopupCard({ title: card.title, timeframe: card.timeframe, room: card.room, presenterNames: safePresenterNames, department: card.department, presentationId: card.presentationId })}
                        className="z-10 mx-[1px] cursor-pointer overflow-hidden rounded-md px-1.5 py-0.5 text-left shadow-sm transition hover:brightness-110 hover:shadow-md"
                        style={{
                          gridRow: `${gridRowStart} / ${gridRowEnd}`,
                          gridColumn: gridCol,
                          backgroundColor: color.bg,
                          color: color.text,
                          position: "relative",
                          top: `${topOffset}px`,
                          height: `${blockHeight}px`,
                          alignSelf: "start",
                        }}
                        title={`${card.title}\n${safePresenterNames.join(", ")}`}
                      >
                        <div className="truncate text-xs font-semibold leading-tight">{card.title}</div>
                        {durationSlots > 1 ? (
                          <div className="truncate text-[10px] leading-tight opacity-80">
                            {safePresenterNames.join(", ") || "No presenters"}
                          </div>
                        ) : null}
                      </div>
                    );
                  })}
                </div>
              </div>
            );
          })() : null}
        </div>
      </div>

      {popupCard ? (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 px-4"
          onClick={() => setPopupCard(null)}
        >
          <div
            className="w-full max-w-lg overflow-hidden rounded-xl border border-[#d6b676] bg-white shadow-2xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="bg-[#1635a7] px-5 py-3 text-xl font-semibold text-white">
              {popupCard.timeframe ? timeLabel(popupCard.timeframe.start_time, popupCard.timeframe.end_time) : "Time TBD"}
            </div>
            <div className="px-5 py-4 space-y-3">
              <h2 className="text-2xl font-extrabold text-[#111]">{popupCard.title}</h2>
              <div className="text-lg text-[#333] space-y-1">
                <p><span className="font-semibold">Location:</span> {popupCard.room}</p>
                <p><span className="font-semibold">Department:</span> {popupCard.department.department_name}</p>
                <p><span className="font-semibold">Advisor:</span> {popupCard.department.department_head_name}</p>
                <p>
                  <span className="font-semibold">Presenters:</span>{" "}
                  {popupCard.presenterNames.length > 0 ? popupCard.presenterNames.join(", ") : "TBD"}
                </p>
              </div>
              <div className="flex gap-3">
                {isAttendee ? (() => {
                  const cardKey = popupCard.presentationId;
                  const bookmarked = itinerary.has(cardKey);
                  return (
                    <button
                      type="button"
                      onClick={() => toggleItinerary(cardKey)}
                      className={`rounded-lg border px-4 py-2 text-sm font-semibold transition ${
                        bookmarked
                          ? "border-[#1635a7] bg-[#1635a7] text-white hover:bg-[#0b2a8d]"
                          : "border-[#1635a7] bg-white text-[#1635a7] hover:bg-[#eef3ff]"
                      }`}
                    >
                      {bookmarked ? "✓ Added to Itinerary" : "Add to Itinerary"}
                    </button>
                  );
                })() : null}
                <button
                  type="button"
                  onClick={() => setPopupCard(null)}
                  className="rounded-lg border border-[#ccc] bg-white px-4 py-2 text-sm font-semibold text-[#555] hover:bg-[#f5f5f5]"
                >
                  Close
                </button>
              </div>
            </div>
          </div>
        </div>
      ) : null}

      {showItinerary ? (
        <div
          className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/60 p-4 backdrop-blur-sm"
          onClick={() => setShowItinerary(false)}
        >
          <div
            className="my-8 w-full max-w-2xl overflow-hidden rounded-2xl bg-white shadow-2xl"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Header */}
            <div className="flex items-center justify-between bg-[#1635a7] px-6 py-4">
              <div className="flex items-center gap-3">
                <svg width="22" height="22" viewBox="0 0 24 24" fill="white"><path d="M5 3h14a1 1 0 0 1 1 1v17l-8-4-8 4V4a1 1 0 0 1 1-1z"/></svg>
                <h2 className="text-xl font-bold text-white">My Itinerary</h2>
                {itinerary.size > 0 ? (
                  <span className="rounded-full bg-white/20 px-2.5 py-0.5 text-sm font-semibold text-white">{itinerary.size}</span>
                ) : null}
              </div>
              <button
                type="button"
                onClick={() => setShowItinerary(false)}
                className="rounded-full p-1 text-white/80 transition hover:bg-white/20 hover:text-white"
                aria-label="Close"
              >
                <svg width="20" height="20" viewBox="0 0 20 20" fill="currentColor"><path fillRule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clipRule="evenodd"/></svg>
              </button>
            </div>

            {/* Body */}
            <div className="p-6">
              {itineraryLoading ? (
                <div className="flex items-center justify-center py-16 text-[#1635a7]">
                  <svg className="animate-spin" width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"/></svg>
                </div>
              ) : !itineraryDetails || itineraryDetails.length === 0 ? (
                <div className="flex flex-col items-center justify-center gap-3 py-16 text-center">
                  <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="#c5cfe8" strokeWidth="1.5"><path d="M5 3h14a1 1 0 0 1 1 1v17l-8-4-8 4V4a1 1 0 0 1 1-1z"/></svg>
                  <p className="text-lg font-semibold text-[#555]">No bookmarks yet</p>
                  <p className="text-sm text-[#888]">Tap the bookmark icon on any presentation to add it here.</p>
                </div>
              ) : (() => {
                // Group by symposium, then by day
                const bySymposium = new Map<string, { name: string; byDay: Map<string, ItineraryDetailItem[]> }>();
                for (const item of itineraryDetails) {
                  const sid = item.symposium_id;
                  if (!bySymposium.has(sid)) bySymposium.set(sid, { name: item.symposium_name, byDay: new Map() });
                  const dayK = item.start_time ? dayKey(parseBackendDateTime(item.start_time)) : "unscheduled";
                  const group = bySymposium.get(sid)!;
                  if (!group.byDay.has(dayK)) group.byDay.set(dayK, []);
                  group.byDay.get(dayK)!.push(item);
                }
                // Sort each day's presentations by start_time
                for (const { byDay } of bySymposium.values()) {
                  for (const items of byDay.values()) {
                    items.sort((a, b) => (a.start_time ?? "").localeCompare(b.start_time ?? ""));
                  }
                }
                return (
                  <div className="space-y-8">
                    {Array.from(bySymposium.values()).map(({ name: sympName, byDay }) => (
                      <div key={sympName}>
                        {bySymposium.size > 1 ? (
                          <h3 className="mb-4 border-b border-[#e5e9ff] pb-2 text-sm font-bold uppercase tracking-widest text-[#1635a7]">{sympName}</h3>
                        ) : null}
                        <div className="space-y-6">
                          {Array.from(byDay.entries()).sort(([a], [b]) => a.localeCompare(b)).map(([day, items]) => (
                            <div key={day}>
                              <div className="mb-3 flex items-center gap-2">
                                <span className="rounded-full bg-[#eef2ff] px-3 py-1 text-sm font-semibold text-[#1635a7]">
                                  {day === "unscheduled" ? "Time TBD" : dayLabel(day)}
                                </span>
                                <span className="text-xs text-[#aaa]">{items.length} presentation{items.length !== 1 ? "s" : ""}</span>
                              </div>
                              <div className="space-y-3">
                                {items.map((item) => (
                                  <div key={item.presentation_id} className="flex gap-3 rounded-xl border border-[#e5e9ff] bg-[#f8f9ff] p-4 transition hover:border-[#b9c6f8] hover:bg-[#eef2ff]">
                                    <div className="flex-1 min-w-0">
                                      {item.start_time && item.end_time ? (
                                        <p className="mb-1 text-xs font-semibold text-[#1635a7]">{timeLabel(item.start_time, item.end_time)}</p>
                                      ) : null}
                                      <p className="font-bold text-[#111] leading-snug">{item.title}</p>
                                      <div className="mt-1.5 flex flex-wrap gap-x-4 gap-y-0.5 text-sm text-[#555]">
                                        {item.room ? <span>{item.room}</span> : null}
                                        {item.presenter_names.length > 0 ? <span>{item.presenter_names.join(", ")}</span> : null}
                                        <span>{item.department_name}</span>
                                        <span>{item.department_head_name}</span>
                                      </div>
                                    </div>
                                    <button
                                      type="button"
                                      onClick={() => toggleItinerary(item.presentation_id)}
                                      title="Remove from itinerary"
                                      className="shrink-0 self-start text-[#1635a7] transition hover:text-[#c0392b] hover:scale-110"
                                    >
                                      <svg width="22" height="22" viewBox="0 0 24 24" fill="currentColor"><path d="M5 3h14a1 1 0 0 1 1 1v17l-8-4-8 4V4a1 1 0 0 1 1-1z"/></svg>
                                    </button>
                                  </div>
                                ))}
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                    ))}
                  </div>
                );
              })()}
            </div>
          </div>
        </div>
      ) : null}
    </main>
  );
}

export default function Home({ isAttendee, attendeeId, authToken, onSignOut }: { isAttendee?: boolean; attendeeId?: string; authToken?: string; onSignOut?: () => void } = {}) {
  return (
    <Suspense fallback={<main className="min-h-screen bg-[#f5f5f5] px-4 py-8">Loading...</main>}>
      <HomeContent isAttendee={isAttendee} attendeeId={attendeeId} authToken={authToken} onSignOut={onSignOut} />
    </Suspense>
  );
}
