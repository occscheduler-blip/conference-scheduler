"use client";

import Link from "next/link";
import { Suspense, useState } from "react";
import { useSearchParams } from "next/navigation";
import AdminPage from "./admin";
import DepartmentHeadPage from "./department-head";
import HomePage from "./home";
import ProfessorPage from "./professor";
import StudentPage from "./student";

const fieldClass =
  "w-full rounded-lg border-2 border-[#2f53c4] bg-white px-3 py-2.5 text-base text-black shadow-sm outline-none transition focus:border-[#1237af] focus:ring-2 focus:ring-[#c7d4ff] placeholder:text-[#6b6b6b]";

type AuthState = {
  token: string;
  role: string;
  entityId: string;
};

const ROLE_VIEW: Record<string, string> = {
  admin: "admin",
  department_head: "department-head",
  professor: "professor",
  student: "student",
};

function LoginScreen({ onLogin }: { onLogin: (auth: AuthState) => void }) {
  const backendUrl = "/api/backend";
  const [mode, setMode] = useState<"admin" | "otp">("otp");

  // Admin login
  const [adminEmail, setAdminEmail] = useState("");
  const [adminPassword, setAdminPassword] = useState("");

  // OTP login
  const [otpEmail, setOtpEmail] = useState("");
  const [otpRole, setOtpRole] = useState<string>("professor");
  const [otpCode, setOtpCode] = useState("");
  const [otpSent, setOtpSent] = useState(false);

  // Shared
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const handleAdminLogin = async () => {
    setLoading(true);
    setError("");
    try {
      const res = await fetch(`${backendUrl}/api/auth/admin/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: adminEmail, password: adminPassword }),
      });
      const data = (await res.json().catch(() => ({}))) as {
        access_token?: string;
        role?: string;
        entity_id?: string;
        detail?: string;
      };
      if (!res.ok) {
        setError(data.detail ?? "Login failed.");
        return;
      }
      onLogin({
        token: data.access_token ?? "",
        role: data.role ?? "admin",
        entityId: data.entity_id ?? "",
      });
    } catch {
      setError("Could not reach the server.");
    } finally {
      setLoading(false);
    }
  };

  const handleRequestOtp = async () => {
    setLoading(true);
    setError("");
    try {
      const res = await fetch(`${backendUrl}/api/auth/otp/request`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: otpEmail, role: otpRole }),
      });
      const data = (await res.json().catch(() => ({}))) as { detail?: string };
      if (!res.ok) {
        setError(data.detail ?? "Failed to send code.");
        return;
      }
      setOtpSent(true);
    } catch {
      setError("Could not reach the server.");
    } finally {
      setLoading(false);
    }
  };

  const handleVerifyOtp = async () => {
    setLoading(true);
    setError("");
    try {
      const res = await fetch(`${backendUrl}/api/auth/otp/verify`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: otpEmail, role: otpRole, otp: otpCode }),
      });
      const data = (await res.json().catch(() => ({}))) as {
        access_token?: string;
        role?: string;
        entity_id?: string;
        detail?: string;
      };
      if (!res.ok) {
        setError(data.detail ?? "Verification failed.");
        return;
      }
      onLogin({
        token: data.access_token ?? "",
        role: data.role ?? otpRole,
        entityId: data.entity_id ?? "",
      });
    } catch {
      setError("Could not reach the server.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <main className="flex min-h-screen items-center justify-center bg-[linear-gradient(180deg,#f7f9ff_0%,#f4f4f4_55%,#f1f1f1_100%)] px-4">
      <div className="w-full max-w-md rounded-2xl border border-[#d8e2ff] bg-white/90 p-8 shadow-[0_10px_30px_rgba(20,44,120,0.08)]">
        <h1 className="mb-6 text-center text-2xl font-extrabold tracking-wide text-black">
          OCC Thesis Symposium
        </h1>

        {/* Mode tabs */}
        <div className="mb-6 grid grid-cols-2 gap-2">
          <button
            type="button"
            onClick={() => { setMode("otp"); setError(""); }}
            className={`rounded-lg px-3 py-2 text-sm font-semibold transition ${
              mode === "otp"
                ? "bg-[#0f33a8] text-white"
                : "border border-[#c6d2f6] bg-white text-[#111] hover:border-[#0f33a8]"
            }`}
          >
            Sign In with Email
          </button>
          <button
            type="button"
            onClick={() => { setMode("admin"); setError(""); }}
            className={`rounded-lg px-3 py-2 text-sm font-semibold transition ${
              mode === "admin"
                ? "bg-[#0f33a8] text-white"
                : "border border-[#c6d2f6] bg-white text-[#111] hover:border-[#0f33a8]"
            }`}
          >
            Admin Sign In
          </button>
        </div>

        {mode === "admin" ? (
          <div className="space-y-4">
            <input
              type="email"
              placeholder="Admin email"
              value={adminEmail}
              onChange={(e) => setAdminEmail(e.target.value)}
              className={fieldClass}
              onKeyDown={(e) => e.key === "Enter" && handleAdminLogin()}
            />
            <input
              type="password"
              placeholder="Password"
              value={adminPassword}
              onChange={(e) => setAdminPassword(e.target.value)}
              className={fieldClass}
              onKeyDown={(e) => e.key === "Enter" && handleAdminLogin()}
            />
            <button
              type="button"
              onClick={handleAdminLogin}
              disabled={loading || !adminEmail || !adminPassword}
              className="w-full rounded-xl bg-[#0f33a8] px-4 py-3 text-lg font-semibold text-white shadow transition hover:bg-[#1237af] disabled:opacity-50"
            >
              {loading ? "Signing in..." : "Sign In"}
            </button>
          </div>
        ) : (
          <div className="space-y-4">
            <label className="block">
              <span className="text-xs font-bold uppercase tracking-wide text-[#2d3d7a]">I am a...</span>
              <select
                value={otpRole}
                onChange={(e) => { setOtpRole(e.target.value); setOtpSent(false); setOtpCode(""); setError(""); }}
                className={fieldClass}
                disabled={otpSent}
              >
                <option value="professor">Professor</option>
                <option value="department_head">Department Head</option>
                <option value="student">Student</option>
              </select>
            </label>
            <input
              type="email"
              placeholder="Email"
              value={otpEmail}
              onChange={(e) => setOtpEmail(e.target.value)}
              disabled={otpSent}
              className={fieldClass}
              onKeyDown={(e) => e.key === "Enter" && !otpSent && handleRequestOtp()}
            />
            {!otpSent ? (
              <button
                type="button"
                onClick={handleRequestOtp}
                disabled={loading || !otpEmail}
                className="w-full rounded-xl bg-[#0f33a8] px-4 py-3 text-lg font-semibold text-white shadow transition hover:bg-[#1237af] disabled:opacity-50"
              >
                {loading ? "Sending..." : "Send One-Time Password"}
              </button>
            ) : (
              <>
                <p className="text-center text-sm text-green-700">A code was sent to your email.</p>
                <input
                  type="text"
                  placeholder="Enter 6-digit code"
                  value={otpCode}
                  onChange={(e) => setOtpCode(e.target.value)}
                  className={fieldClass}
                  onKeyDown={(e) => e.key === "Enter" && handleVerifyOtp()}
                  autoFocus
                />
                <button
                  type="button"
                  onClick={handleVerifyOtp}
                  disabled={loading || !otpCode}
                  className="w-full rounded-xl bg-[#0f33a8] px-4 py-3 text-lg font-semibold text-white shadow transition hover:bg-[#1237af] disabled:opacity-50"
                >
                  {loading ? "Verifying..." : "Verify & Sign In"}
                </button>
                <button
                  type="button"
                  onClick={() => { setOtpSent(false); setOtpCode(""); setError(""); }}
                  className="w-full text-sm text-[#0f33a8] underline"
                >
                  Use a different email
                </button>
              </>
            )}
          </div>
        )}

        {error && <p className="mt-4 text-center text-sm text-red-600">{error}</p>}

        <div className="mt-6 text-center">
          <Link href="/pages?view=home" className="text-sm text-[#0f33a8] underline hover:text-[#1237af]">
            View Public Schedule
          </Link>
        </div>
      </div>
    </main>
  );
}

function PagesRouterContent() {
  const searchParams = useSearchParams();
  const view = (searchParams.get("view") ?? "home").toLowerCase();
  const [auth, setAuth] = useState<AuthState | null>(null);

  const handleSignOut = () => setAuth(null);

  // Public home page
  if (view === "home" && !auth) return <HomePage />;

  // Show login if not authenticated (any non-home view, or explicit "login")
  if (!auth) return <LoginScreen onLogin={setAuth} />;

  // Authenticated — render the page matching the user's role
  const roleView = ROLE_VIEW[auth.role] ?? "home";
  if (roleView === "admin") return <AdminPage token={auth.token} onSignOut={handleSignOut} />;
  if (roleView === "department-head") return <DepartmentHeadPage token={auth.token} onSignOut={handleSignOut} entityId={auth.entityId} />;
  if (roleView === "professor") return <ProfessorPage token={auth.token} onSignOut={handleSignOut} entityId={auth.entityId} />;
  if (roleView === "student") return <StudentPage token={auth.token} onSignOut={handleSignOut} entityId={auth.entityId} />;
  return <HomePage />;
}

export default function PagesRouter() {
  return (
    <Suspense fallback={<HomePage />}>
      <PagesRouterContent />
    </Suspense>
  );
}
