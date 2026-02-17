"use client";

import { useEffect, useMemo, useState } from "react";

type AdminTab = "create" | "edit";

const fieldClass =
  "w-full rounded-lg border-2 border-[#2f53c4] bg-white px-3 py-2.5 text-base text-black shadow-sm outline-none transition focus:border-[#1237af] focus:ring-2 focus:ring-[#c7d4ff] placeholder:text-[#6b6b6b]";

const totalSlots = 32; // 9:00 AM to 5:00 PM in 15-minute increments
const weekDays = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const fixedSymposiumId = "9e1fd0da-ea43-48f2-85df-5281a495f054";

function formatTimeLabel(slotIndex: number) {
  const totalMinutes = 9 * 60 + slotIndex * 15;
  const hour24 = Math.floor(totalMinutes / 60);
  const minutes = totalMinutes % 60;
  const suffix = hour24 >= 12 ? "PM" : "AM";
  const hour12 = hour24 % 12 === 0 ? 12 : hour24 % 12;
  const minutePart = minutes.toString().padStart(2, "0");
  return `${hour12}:${minutePart} ${suffix}`;
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

    setIsSaving(true);
    try {
      const response = await fetch(`${backendUrl}/api/events/add_symposium`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          symposium_id: fixedSymposiumId,
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

      setSaveMessage(`Saved symposium ${payload.symposium_id ?? fixedSymposiumId} with ${timeframes.length} timeframes.`);
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
            onClick={() => setActiveTab("create")}
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
            onClick={() => setActiveTab("edit")}
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

                <div className="mt-5 grid grid-cols-1 gap-4 md:grid-cols-2">
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

                <p className="mb-3 text-sm font-semibold text-[#444] md:text-base">
                  Click and drag to toggle availability.
                </p>

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

              <div className="lg:col-span-2">
                <button
                  type="submit"
                  disabled={isSaving}
                  className="rounded-lg bg-[#0f33a8] px-5 py-2.5 text-sm font-semibold text-white shadow-[0_8px_18px_rgba(15,51,168,0.25)] transition hover:bg-[#0b2a8d] disabled:cursor-not-allowed disabled:opacity-60 md:text-base"
                >
                  {isSaving ? "Saving..." : "Save Event"}
                </button>
                {saveMessage ? <p className="mt-2 text-sm font-semibold text-[#222]">{saveMessage}</p> : null}
              </div>
            </form>
          </section>
        ) : (
          <section className="rounded-2xl border border-[#d7bf92] bg-white p-4 shadow-[0_16px_30px_rgba(80,60,20,0.08)] md:p-6">
            <h2 className="mb-4 text-xl font-bold text-[#111] md:text-2xl">Edit Existing Event</h2>
            <div className="max-w-2xl space-y-3 rounded-xl border border-[#e6ecff] bg-[#fdfdff] p-4 md:p-5">
              <label className="flex flex-col gap-1.5">
                <span className="text-xs font-bold uppercase tracking-wide text-[#2d3d7a] md:text-sm">Select Event</span>
                <select className="w-full rounded-lg border border-[#c7c7c7] bg-white px-3 py-2.5 text-black shadow-sm outline-none transition focus:border-[#1237af] focus:ring-2 focus:ring-[#c7d4ff]">
                  <option>Coloring Inside the Lines: Racial Identity in the World of PWIs</option>
                  <option>OCC Conference Scheduler</option>
                </select>
              </label>
              <div className="rounded-lg border border-[#e0e0e0] bg-[#f9f9f9] p-3 text-sm text-[#333]">
                Choose an event to load and edit its details.
              </div>
              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  className="rounded-lg bg-[#0f33a8] px-4 py-2 text-sm font-semibold text-white shadow-[0_8px_18px_rgba(15,51,168,0.25)] transition hover:bg-[#0b2a8d] md:text-base"
                >
                  Load Event
                </button>
                <button
                  type="button"
                  className="rounded-lg border border-[#b7b7b7] bg-white px-4 py-2 text-sm font-semibold text-[#222] transition hover:bg-[#f7f7f7] md:text-base"
                >
                  Delete Event
                </button>
              </div>
            </div>
          </section>
        )}
      </div>
    </main>
  );
}
