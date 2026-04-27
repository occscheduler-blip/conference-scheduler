"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

type DepartmentRow = {
  id?: string;
  department_name?: string;
  department_head_name?: string;
  email?: string;
  symposium_id?: string;
};

type ProfessorRow = {
  id?: string;
  name?: string;
  email?: string;
  class_id?: string;
};

type StudentRow = {
  id?: string;
  name?: string;
  email?: string;
  class_id?: string;
};

type ClassRow = {
  id?: string;
  department_id?: string;
};

type TimeframeRow = {
  linked_id?: string;
  start_time?: string;
  end_time?: string;
};

type LoginResult = {
  roleLabel: "Admin" | "Faculty" | "Professor" | "Student";
  name: string;
  path: string;
};

type AdminSession = {
  email: string;
  token: string;
};

const inputClass =
  "w-full rounded-lg border-2 border-[#2f53c4] bg-white px-3 py-2.5 text-base text-black shadow-sm outline-none transition focus:border-[#1237af] focus:ring-2 focus:ring-[#c7d4ff] placeholder:text-[#6b6b6b]";

function normalizeEmail(value: string) {
  return value.trim().toLowerCase();
}

function toArray<T>(payload: unknown): T[] {
  if (Array.isArray(payload)) return payload as T[];
  if (payload && typeof payload === "object" && Array.isArray((payload as { data?: unknown[] }).data)) {
    return (payload as { data: T[] }).data;
  }
  return [];
}

async function fetchRows<T>(url: string, headers?: HeadersInit): Promise<T[]> {
  const response = await fetch(url, { headers, cache: "no-store" });
  const payload = (await response.json().catch(() => ({}))) as { detail?: unknown; data?: T[] } | T[];
  if (!response.ok) {
    const detail = typeof (payload as { detail?: unknown }).detail === "string" ? (payload as { detail: string }).detail : "Login lookup failed.";
    throw new Error(detail);
  }
  return toArray<T>(payload);
}

function parseBackendDateTime(value: string) {
  const hasExplicitTimezone = /(?:Z|[+\-]\d{2}:\d{2})$/i.test(value);
  return new Date(hasExplicitTimezone ? value : `${value}Z`);
}

function getActiveSymposiumIds(timeframes: TimeframeRow[]) {
  const now = Date.now();
  const activeIds = new Set<string>();

  for (const timeframe of timeframes) {
    const linkedId = (timeframe.linked_id ?? "").trim();
    const startTime = (timeframe.start_time ?? "").trim();
    if (!linkedId || !startTime) continue;

    const start = parseBackendDateTime(startTime);
    const end = timeframe.end_time?.trim() ? parseBackendDateTime(timeframe.end_time) : start;
    if (Number.isNaN(start.getTime()) || Number.isNaN(end.getTime())) continue;

    if (end.getTime() >= now) {
      activeIds.add(linkedId);
    }
  }

  return activeIds;
}

export default function HomePage() {
  const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:8000";
  const backendApiKey = process.env.NEXT_PUBLIC_BACKEND_API_KEY ?? "";
  const authHeaders = useMemo(() => (backendApiKey ? { "X-API-Key": backendApiKey } : undefined), [backendApiKey]);

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [isAdmin, setIsAdmin] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState("");
  const [loginResult, setLoginResult] = useState<LoginResult | null>(null);
  const [adminSession, setAdminSession] = useState<AdminSession | null>(null);
  const [newAdminEmail, setNewAdminEmail] = useState("");
  const [newAdminPassword, setNewAdminPassword] = useState("");
  const [isCreatingAdmin, setIsCreatingAdmin] = useState(false);
  const [createAdminMessage, setCreateAdminMessage] = useState("");

  useEffect(() => {
    if (typeof window === "undefined") return;
    const storedToken = window.localStorage.getItem("admin_auth_token");
    const storedEmail = window.localStorage.getItem("admin_auth_email");
    if (storedToken && storedEmail) {
      setAdminSession({ email: storedEmail, token: storedToken });
    }
  }, []);

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setErrorMessage("");
    setLoginResult(null);

    const normalizedEmail = normalizeEmail(email);
    if (!normalizedEmail) {
      setErrorMessage("Enter your email address.");
      return;
    }

    if (isAdmin) {
      if (!password) {
        setErrorMessage("Enter the admin password.");
        return;
      }
      setIsSubmitting(true);
      try {
        const response = await fetch(`${backendUrl}/api/auth/admin/login`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            email: normalizedEmail,
            password,
          }),
        });
        const payload = (await response.json().catch(() => ({}))) as {
          detail?: unknown;
          access_token?: string;
          token?: string;
          entity_id?: string;
        };
        if (!response.ok) {
          const detail = payload.detail;
          const message =
            typeof detail === "string"
              ? detail
              : Array.isArray(detail)
                ? detail
                    .map((item) => (typeof item === "string" ? item : (item as { msg?: unknown })?.msg))
                    .filter((item): item is string => typeof item === "string" && item.trim().length > 0)
                    .join("; ")
                : "Invalid admin email or password.";
          throw new Error(message || "Invalid admin email or password.");
        }
        const token = typeof payload.access_token === "string" ? payload.access_token : payload.token;
        if (token && typeof window !== "undefined") {
          window.localStorage.setItem("admin_auth_token", token);
          window.localStorage.setItem("admin_auth_email", normalizedEmail);
          setAdminSession({ email: normalizedEmail, token });
        }
        setCreateAdminMessage("");
      } catch (error) {
        setErrorMessage(error instanceof Error ? error.message : "Admin login failed.");
        setIsSubmitting(false);
        return;
      }
      setLoginResult({
        roleLabel: "Admin",
        name: normalizedEmail,
        path: "/pages?view=admin",
      });
      setIsSubmitting(false);
      return;
    }

    setIsSubmitting(true);
    try {
      const [departments, professors, students, classes, timeframes] = await Promise.all([
        fetchRows<DepartmentRow>(`${backendUrl}/api/events/departments`, authHeaders),
        fetchRows<ProfessorRow>(`${backendUrl}/api/events/professors`, authHeaders),
        fetchRows<StudentRow>(`${backendUrl}/api/events/students`, authHeaders),
        fetchRows<ClassRow>(`${backendUrl}/api/events/classes`, authHeaders),
        fetchRows<TimeframeRow>(`${backendUrl}/api/events/timeframes`, authHeaders),
      ]);

      const departmentsById = new Map(
        departments
          .filter((row): row is DepartmentRow & { id: string; symposium_id: string } => Boolean(row.id && row.symposium_id))
          .map((row) => [row.id, row])
      );
      const classesById = new Map(
        classes.filter((row): row is ClassRow & { id: string; department_id: string } => Boolean(row.id && row.department_id)).map((row) => [row.id, row])
      );
      const activeSymposiumIds = getActiveSymposiumIds(timeframes);

      const faculty = departments.find(
        (row) => normalizeEmail(row.email ?? "") === normalizedEmail && activeSymposiumIds.has(row.symposium_id ?? "")
      );
      if (faculty?.id && faculty.symposium_id) {
        setLoginResult({
          roleLabel: "Faculty",
          name: faculty.department_head_name?.trim() || faculty.department_name?.trim() || normalizedEmail,
          path: `/pages?view=department-head&symposium_id=${encodeURIComponent(faculty.symposium_id)}&department_id=${encodeURIComponent(faculty.id)}`,
        });
        return;
      }

      const professor = professors.find((row) => {
        if (normalizeEmail(row.email ?? "") !== normalizedEmail) return false;
        const classRow = classesById.get(row.class_id ?? "");
        const departmentRow = classRow ? departmentsById.get(classRow.department_id) : undefined;
        return Boolean(departmentRow?.symposium_id && activeSymposiumIds.has(departmentRow.symposium_id));
      });
      if (professor?.id) {
        setLoginResult({
          roleLabel: "Professor",
          name: professor.name?.trim() || normalizedEmail,
          path: `/pages?view=professor&professor_id=${encodeURIComponent(professor.id)}`,
        });
        return;
      }

      const student = students.find((row) => {
        if (normalizeEmail(row.email ?? "") !== normalizedEmail) return false;
        const classRow = classesById.get(row.class_id ?? "");
        const departmentRow = classRow ? departmentsById.get(classRow.department_id) : undefined;
        return Boolean(departmentRow?.symposium_id && activeSymposiumIds.has(departmentRow.symposium_id));
      });
      if (student?.id) {
        setLoginResult({
          roleLabel: "Student",
          name: student.name?.trim() || normalizedEmail,
          path: `/pages?view=student&student_id=${encodeURIComponent(student.id)}`,
        });
        return;
      }

      setErrorMessage("This email is not registered under an active symposium.");
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "Login lookup failed.");
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleCreateAdmin = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setCreateAdminMessage("");

    const normalizedNewAdminEmail = normalizeEmail(newAdminEmail);
    if (!adminSession?.token) {
      setCreateAdminMessage("Log in as an admin first.");
      return;
    }
    if (!normalizedNewAdminEmail) {
      setCreateAdminMessage("Enter the new admin email.");
      return;
    }
    if (!newAdminPassword) {
      setCreateAdminMessage("Enter the new admin password.");
      return;
    }

    setIsCreatingAdmin(true);
    try {
      const response = await fetch(`${backendUrl}/api/auth/admin/create`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${adminSession.token}`,
        },
        body: JSON.stringify({
          email: normalizedNewAdminEmail,
          password: newAdminPassword,
        }),
      });
      const payload = (await response.json().catch(() => ({}))) as {
        detail?: unknown;
        admin_id?: string;
      };
      if (!response.ok) {
        const detail = payload.detail;
        const message =
          typeof detail === "string"
            ? detail
            : Array.isArray(detail)
              ? detail
                  .map((item) => (typeof item === "string" ? item : (item as { msg?: unknown })?.msg))
                  .filter((item): item is string => typeof item === "string" && item.trim().length > 0)
                  .join("; ")
              : "Unable to create admin.";
        if (response.status === 401 && typeof window !== "undefined") {
          window.localStorage.removeItem("admin_auth_token");
          window.localStorage.removeItem("admin_auth_email");
          setAdminSession(null);
        }
        throw new Error(message || "Unable to create admin.");
      }

      setCreateAdminMessage(`Admin created: ${normalizedNewAdminEmail}`);
      setNewAdminEmail("");
      setNewAdminPassword("");
    } catch (error) {
      setCreateAdminMessage(error instanceof Error ? error.message : "Unable to create admin.");
    } finally {
      setIsCreatingAdmin(false);
    }
  };

  const handleAdminLogout = () => {
    if (typeof window !== "undefined") {
      window.localStorage.removeItem("admin_auth_token");
      window.localStorage.removeItem("admin_auth_email");
    }
    setAdminSession(null);
    setCreateAdminMessage("");
    setNewAdminEmail("");
    setNewAdminPassword("");
  };

  const resolvedHref = loginResult?.path ?? "";

  return (
    <main className="min-h-screen bg-[#f5f5f5] px-4 py-6 text-[#111]">
      <div className="mx-auto w-full max-w-6xl">
        <div className="mb-4 flex justify-end">
          <Link
            href="/pages?view=home"
            className="rounded-md border border-[#9ca3af] bg-[#e5e7eb] px-4 py-2 text-sm font-semibold text-[#1f2937] transition hover:border-[#0f33a8] hover:bg-[#0f33a8] hover:text-white"
          >
            Home
          </Link>
        </div>

        <section className="overflow-hidden rounded-lg border-4 border-[#1635a7] bg-[#1635a7]">
          <div className="grid gap-0 lg:grid-cols-[1.1fr_0.9fr]">
            <div className="border-b-4 border-[#1635a7] bg-[#1635a7] px-6 py-8 text-white lg:border-b-0 lg:border-r-4">
              <h1 className="text-3xl font-extrabold tracking-wide md:text-5xl">Sign in using your Hamilton email!</h1>
              <p className="mt-4 max-w-xl text-lg leading-8 text-[#edf2ff]">
                Make sure to check your email inbox for your individual log-in link!
              </p>
            </div>

            <div className="bg-white p-6 sm:p-8">
          <form className="space-y-5" onSubmit={handleSubmit}>
            <div>
              <h2 className="text-3xl font-extrabold text-black">Login:</h2>
            </div>

            <label className="block">
              <span className="mb-2 block text-xs font-bold uppercase tracking-wide text-[#1b338f]">Email</span>
              <input
                type="email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                className={inputClass}
                placeholder="name@hamilton.edu"
                autoComplete="email"
              />
            </label>

            <label className="flex items-center gap-3 rounded-lg border border-[#b9c6f8] bg-[#f3f6ff] px-4 py-3 text-sm font-semibold text-[#1f2937]">
              <input
                type="checkbox"
                checked={isAdmin}
                onChange={(event) => {
                  setIsAdmin(event.target.checked);
                  setPassword("");
                  setErrorMessage("");
                  setLoginResult(null);
                }}
                className="h-4 w-4 rounded border-[#5d77d8] text-[#1635a7] focus:ring-[#1635a7]"
              />
              I am an admin
            </label>

            {isAdmin ? (
              <label className="block">
                <span className="mb-2 block text-xs font-bold uppercase tracking-wide text-[#1b338f]">Password</span>
                <input
                  type="password"
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  className={inputClass}
                  placeholder="Enter admin password"
                  autoComplete="current-password"
                />
              </label>
            ) : null}

            <button
              type="submit"
              disabled={isSubmitting}
              className="w-full rounded-md border border-[#1635a7] bg-[#1635a7] px-5 py-3 text-base font-semibold text-white transition hover:border-[#0f33a8] hover:bg-[#0f33a8] disabled:cursor-not-allowed disabled:border-[#9ca3af] disabled:bg-[#9ca3af]"
            >
              {isSubmitting ? "Checking your email..." : "Continue"}
            </button>
          </form>

          {errorMessage ? (
            <div className="mt-5 rounded-lg border border-[#e1b5b5] bg-[#fff5f5] px-4 py-3 text-sm font-semibold text-[#9a1f1f]">
              {errorMessage}
            </div>
          ) : null}

          {loginResult ? (
            <div className="mt-5 rounded-xl border border-[#b9c6f8] bg-[#f8faff] p-5 text-[#111]">
              <p className="text-xs font-bold uppercase tracking-wide text-[#1b338f]">{loginResult.roleLabel} link ready</p>
              <p className="mt-2 text-lg font-semibold">{loginResult.name}</p>
              <p className="mt-1 text-sm text-[#444]">Open the page below to go directly to your symposium view.</p>
              <div className="mt-4 break-all rounded-lg border border-[#d7b980] bg-white px-4 py-3 text-sm text-[#444]">{resolvedHref}</div>
              <div className="mt-4 flex flex-wrap gap-3">
                <Link
                  href={resolvedHref}
                  className="rounded-md border border-[#1635a7] bg-[#1635a7] px-4 py-3 text-sm font-semibold text-white transition hover:border-[#0f33a8] hover:bg-[#0f33a8]"
                >
                  Open my page
                </Link>
                <button
                  type="button"
                  onClick={async () => {
                    if (!resolvedHref || typeof window === "undefined") return;
                    await navigator.clipboard.writeText(`${window.location.origin}${resolvedHref}`);
                  }}
                  className="rounded-md border border-[#9ca3af] bg-[#e5e7eb] px-4 py-3 text-sm font-semibold text-[#1f2937] transition hover:border-[#0f33a8] hover:bg-[#0f33a8] hover:text-white"
                >
                  Copy full link
                </button>
              </div>
            </div>
          ) : null}

          {adminSession ? (
            <section className="mt-5 rounded-xl border border-[#b9c6f8] bg-[#f8faff] p-5 text-[#111]">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <p className="text-xs font-bold uppercase tracking-wide text-[#1b338f]">Admin session</p>
                  <p className="mt-2 text-sm text-[#444]">Logged in as {adminSession.email}</p>
                </div>
                <button
                  type="button"
                  onClick={handleAdminLogout}
                  className="rounded-md border border-[#9ca3af] bg-[#e5e7eb] px-3 py-2 text-sm font-semibold text-[#1f2937] transition hover:border-[#0f33a8] hover:bg-[#0f33a8] hover:text-white"
                >
                  Log out
                </button>
              </div>

              <form className="mt-5 space-y-4" onSubmit={handleCreateAdmin}>
                <div>
                  <h3 className="text-xl font-extrabold text-black">Create admin</h3>
                </div>

                <label className="block">
                  <span className="mb-2 block text-xs font-bold uppercase tracking-wide text-[#1b338f]">Admin email</span>
                  <input
                    type="email"
                    value={newAdminEmail}
                    onChange={(event) => setNewAdminEmail(event.target.value)}
                    className={inputClass}
                    placeholder="newadmin@hamilton.edu"
                    autoComplete="email"
                  />
                </label>

                <label className="block">
                  <span className="mb-2 block text-xs font-bold uppercase tracking-wide text-[#1b338f]">Admin password</span>
                  <input
                    type="password"
                    value={newAdminPassword}
                    onChange={(event) => setNewAdminPassword(event.target.value)}
                    className={inputClass}
                    placeholder="Set a password"
                    autoComplete="new-password"
                  />
                </label>

                <button
                  type="submit"
                  disabled={isCreatingAdmin}
                  className="w-full rounded-md border border-[#1635a7] bg-[#1635a7] px-5 py-3 text-base font-semibold text-white transition hover:border-[#0f33a8] hover:bg-[#0f33a8] disabled:cursor-not-allowed disabled:border-[#9ca3af] disabled:bg-[#9ca3af]"
                >
                  {isCreatingAdmin ? "Creating admin..." : "Create admin"}
                </button>
              </form>

              {createAdminMessage ? (
                <div className="mt-4 rounded-lg border border-[#d7b980] bg-white px-4 py-3 text-sm font-semibold text-[#444]">
                  {createAdminMessage}
                </div>
              ) : null}
            </section>
          ) : null}
            </div>
          </div>
        </section>
      </div>
    </main>
  );
}
