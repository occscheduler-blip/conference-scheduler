"use client";

import { useEffect, useState } from "react";

type FacultyTab = "availability" | "students";

const weekDays = ["Mon", "Tue", "Wed", "Thu", "Fri"];
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

export default function FacultyPage() {
  const [activeTab, setActiveTab] = useState<FacultyTab>("availability");
  const [availability, setAvailability] = useState<boolean[][]>(() =>
    weekDays.map(() => Array.from({ length: totalSlots }, () => false))
  );
  const [isDragging, setIsDragging] = useState(false);
  const [dragValue, setDragValue] = useState<boolean | null>(null);
  const [csvFile, setCsvFile] = useState<File | null>(null);
  const [csvUploading, setCsvUploading] = useState(false);
  const [csvMessage, setCsvMessage] = useState<string | null>(null);

  const isAvailabilityTab = activeTab === "availability";
  const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:8000";

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

  async function handleCsvUpload(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!csvFile) {
      setCsvMessage("Select a CSV file before uploading.");
      return;
    }

    const formData = new FormData();
    formData.append("file", csvFile);
    setCsvUploading(true);
    setCsvMessage("Uploading CSV...");

    try {
      const response = await fetch(`${backendUrl}/api/events/upload-students-csv`, {
        method: "POST",
        body: formData,
      });
      const payload = (await response.json()) as {
        detail?: string;
        rows_inserted?: number;
        rows_received?: number;
      };

      if (!response.ok) {
        setCsvMessage(payload.detail ?? "CSV upload failed.");
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
        <header className="mb-5 rounded-2xl border border-[#d8e2ff] bg-white/90 px-5 py-5 shadow-[0_10px_30px_rgba(20,44,120,0.08)] backdrop-blur">
          <h1 className="text-center text-2xl font-extrabold tracking-wide text-black md:text-4xl">
            OCC THESIS SYMPOSIUM - FACULTY
          </h1>
        </header>

        <nav className="mb-4 grid grid-cols-1 gap-3 md:grid-cols-2">
          <button
            type="button"
            onClick={() => setActiveTab("availability")}
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
            className={`rounded-xl border-2 px-4 py-3 text-lg font-semibold transition md:text-xl ${
              isAvailabilityTab
                ? "border-[#c6d2f6] bg-white text-[#111] hover:border-[#0f33a8]"
                : "border-[#0f33a8] bg-[#0f33a8] text-white shadow-[0_8px_20px_rgba(15,51,168,0.25)]"
            }`}
          >
            Add Students
          </button>
        </nav>

        <section className="rounded-2xl border border-[#d7bf92] bg-white p-4 shadow-[0_16px_30px_rgba(80,60,20,0.08)] md:p-6">
          <h2 className="text-xl font-bold text-[#111] md:text-2xl">
            {isAvailabilityTab ? "Update Availability" : "Add Students"}
          </h2>

          {isAvailabilityTab ? (
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
                  <div className="grid grid-cols-[90px_repeat(5,1fr)] text-center text-2xl font-bold text-[#222]">
                    <div />
                    {weekDays.map((day) => (
                      <div key={day} className="border-b border-[#777] pb-1">
                        {day}
                      </div>
                    ))}
                  </div>

                  <div className="grid grid-cols-[90px_repeat(5,1fr)]">
                    {Array.from({ length: totalSlots }, (_, slotIndex) => (
                      <div key={slotIndex} className="contents">
                        <div className="pr-2 pt-1 text-right text-sm font-semibold text-[#444]">
                          {slotIndex % 4 === 0 ? formatTimeLabel(slotIndex) : ""}
                        </div>

                        {weekDays.map((_, dayIndex) => {
                          const available = availability[dayIndex][slotIndex];
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
                              aria-label={`${weekDays[dayIndex]} ${formatTimeLabel(slotIndex)}`}
                            />
                          );
                        })}
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          ) : (
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
          )}
        </section>
      </div>
    </main>
  );
}
