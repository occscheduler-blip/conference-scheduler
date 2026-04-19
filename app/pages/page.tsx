"use client";

import Link from "next/link";
import { Suspense, useState } from "react";
import { useSearchParams } from "next/navigation";
import { apiPost } from "../lib/api";
import AdminPage from "./admin";
import DepartmentHeadPage from "./department-head";
import HomePage from "./home";
import ProfessorPage from "./professor";
import StudentPage from "./student";
import { FIELD_CLASS as fieldClass } from "../lib/styles";

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
  attendee: "attendee",
};

function LoginScreen({ onLogin }: { onLogin: (auth: AuthState) => void }) {
  const [mode, setMode] = useState<"admin" | "otp">("otp");

  // Admin login
  const [adminEmail, setAdminEmail] = useState("");
  const [adminPassword, setAdminPassword] = useState("");

  // OTP login
  const [otpEmail, setOtpEmail] = useState("");
  const [otpRole, setOtpRole] = useState<string>("attendee");
  const [otpCode, setOtpCode] = useState("");
  const [otpSent, setOtpSent] = useState(false);

  // Shared
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [showPassword, setShowPassword] = useState(false);

  const handleAdminLogin = async () => {
    setLoading(true);
    setError("");
    try {
      const { raw } = await apiPost("/api/auth/admin/login", { email: adminEmail, password: adminPassword });
      onLogin({
        token: (raw.access_token as string) ?? "",
        role: (raw.role as string) ?? "admin",
        entityId: (raw.entity_id as string) ?? "",
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not reach the server.");
    } finally {
      setLoading(false);
    }
  };

  const handleRequestOtp = async () => {
    setLoading(true);
    setError("");
    try {
      if (otpRole === "attendee") {
        await apiPost("/api/auth/attendee/register", { email: otpEmail });
      } else {
        await apiPost("/api/auth/otp/request", { email: otpEmail, role: otpRole });
      }
      setOtpSent(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not reach the server.");
    } finally {
      setLoading(false);
    }
  };

  const handleVerifyOtp = async () => {
    setLoading(true);
    setError("");
    try {
      const { raw } = await apiPost("/api/auth/otp/verify", { email: otpEmail, role: otpRole, otp: otpCode });
      onLogin({
        token: (raw.access_token as string) ?? "",
        role: (raw.role as string) ?? otpRole,
        entityId: (raw.entity_id as string) ?? "",

      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not reach the server.");
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
            <div className="relative">
              <input
                type={showPassword ? "text" : "password"}
                placeholder="Password"
                value={adminPassword}
                onChange={(e) => setAdminPassword(e.target.value)}
                className={fieldClass + " pr-10"}
                onKeyDown={(e) => e.key === "Enter" && handleAdminLogin()}
              />
              <button
                type="button"
                onClick={() => setShowPassword(!showPassword)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-[#2d3d7a] hover:text-[#0f33a8]"
                tabIndex={-1}
              >
                {showPassword ? (
                  <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94"/><path d="M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19"/><line x1="1" y1="1" x2="23" y2="23"/></svg>
                ) : (
                  <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>
                )}
              </button>
            </div>
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
                <option value="attendee">Attendee</option>
                <option value="student">Student</option>
                <option value="professor">Professor</option>
                <option value="department_head">Department Head</option>
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
  if (roleView === "attendee") return <HomePage isAttendee={true} attendeeId={auth.entityId} authToken={auth.token} onSignOut={handleSignOut} />;
  return <HomePage />;
}

export default function PagesRouter() {
  return (
    <Suspense fallback={<HomePage />}>
      <PagesRouterContent />
    </Suspense>
  );
}
