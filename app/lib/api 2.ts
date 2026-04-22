import { toMessage } from "./utils";

const BACKEND_URL = "/api/backend";

type ApiPayload<T> = { detail?: unknown; data?: T[] } | T[];

export async function apiFetch<T = Record<string, unknown>>(
  path: string,
  options?: RequestInit
): Promise<T[]> {
  const res = await fetch(`${BACKEND_URL}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...options?.headers,
    },
  });
  const payload = (await res.json().catch(() => ({}))) as ApiPayload<T>;
  if (!res.ok) {
    const detail = Array.isArray(payload) ? undefined : payload.detail;
    throw new Error(toMessage(detail, "Request failed"));
  }
  return Array.isArray(payload) ? payload : (payload.data ?? []);
}

export async function apiPost<T = Record<string, unknown>>(
  path: string,
  body: unknown,
  authHeaders?: Record<string, string>
): Promise<{ raw: Record<string, unknown>; rows: T[] }> {
  const res = await fetch(`${BACKEND_URL}${path}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(authHeaders ?? {}),
    },
    body: JSON.stringify(body),
  });
  const payload = (await res.json().catch(() => ({}))) as Record<string, unknown>;
  if (!res.ok) {
    throw new Error(toMessage(payload.detail, "Request failed"));
  }
  const rows = Array.isArray(payload) ? payload : ((payload.data as T[]) ?? []);
  return { raw: payload, rows };
}

export async function apiPut(
  path: string,
  body: unknown,
  authHeaders?: Record<string, string>
): Promise<Record<string, unknown>> {
  const res = await fetch(`${BACKEND_URL}${path}`, {
    method: "PUT",
    headers: {
      "Content-Type": "application/json",
      ...(authHeaders ?? {}),
    },
    body: JSON.stringify(body),
  });
  const payload = (await res.json().catch(() => ({}))) as Record<string, unknown>;
  if (!res.ok) {
    throw new Error(toMessage(payload.detail, "Request failed"));
  }
  return payload;
}

export async function apiDelete(
  path: string,
  authHeaders?: Record<string, string>
): Promise<Record<string, unknown>> {
  const res = await fetch(`${BACKEND_URL}${path}`, {
    method: "DELETE",
    headers: authHeaders ?? {},
  });
  const payload = (await res.json().catch(() => ({}))) as Record<string, unknown>;
  if (!res.ok) {
    throw new Error(toMessage(payload.detail, "Request failed"));
  }
  return payload;
}
