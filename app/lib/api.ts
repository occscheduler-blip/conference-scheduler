import { toMessage } from "./utils";

export const BACKEND_URL = (
  process.env.NEXT_PUBLIC_BACKEND_URL ?? "/api/backend"
).replace(/\/+$/, "");

type ApiPayload<T> = { detail?: unknown; data?: T[] } | T[];

/**
 * Error thrown by API helpers on non-OK responses. Exposes the HTTP status
 * and the parsed response body so callers can branch on 409 (stale) and 423
 * (busy) without parsing message strings.
 */
export class ApiError extends Error {
  status: number;
  body: Record<string, unknown> | unknown[];
  code: string | null;
  constructor(message: string, status: number, body: Record<string, unknown> | unknown[]) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.body = body;
    const detail = !Array.isArray(body) ? (body.detail as Record<string, unknown> | string | undefined) : undefined;
    this.code =
      detail && typeof detail === "object" && typeof (detail as Record<string, unknown>).code === "string"
        ? ((detail as Record<string, unknown>).code as string)
        : null;
  }
  isStale(): boolean { return this.status === 409 && this.code === "stale"; }
  isBusy(): boolean { return this.status === 423; }
  isSchedulerBusy(): boolean { return this.status === 409 && this.code === "scheduler_busy"; }
}

function _throwForResponse(res: Response, payload: Record<string, unknown> | unknown[]): never {
  const detail = Array.isArray(payload) ? undefined : payload.detail;
  throw new ApiError(toMessage(detail, "Request failed"), res.status, payload);
}

/** Result type for apiMutate — never throws, branch on .ok. */
export type ApiResult<T = Record<string, unknown>> =
  | { ok: true; data: T }
  | { ok: false; status: number; error: string; body: Record<string, unknown> | unknown[]; code: string | null };

/**
 * Mutating request helper that returns a typed ApiResult instead of throwing.
 * Pair with useSubmitGuard for buttons. Recognizes AbortError as a non-error.
 */
export async function apiMutate<T = Record<string, unknown>>(
  method: "POST" | "PUT" | "DELETE",
  path: string,
  body?: unknown,
  opts?: { authHeaders?: Record<string, string>; signal?: AbortSignal },
): Promise<ApiResult<T>> {
  try {
    const res = await fetch(`${BACKEND_URL}${path}`, {
      method,
      headers: {
        "Content-Type": "application/json",
        ...(opts?.authHeaders ?? {}),
      },
      body: body == null ? undefined : JSON.stringify(body),
      signal: opts?.signal,
    });
    const payload = (await res.json().catch(() => ({}))) as Record<string, unknown> | unknown[];
    if (!res.ok) {
      const detail = Array.isArray(payload) ? undefined : (payload as Record<string, unknown>).detail;
      const code =
        detail && typeof detail === "object" && typeof (detail as Record<string, unknown>).code === "string"
          ? ((detail as Record<string, unknown>).code as string)
          : null;
      return {
        ok: false,
        status: res.status,
        error: toMessage(detail, "Request failed"),
        body: payload,
        code,
      };
    }
    return { ok: true, data: payload as T };
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") {
      return { ok: false, status: 0, error: "aborted", body: {}, code: "aborted" };
    }
    throw err;
  }
}

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
  if (!res.ok) _throwForResponse(res, payload as Record<string, unknown> | unknown[]);
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
  if (!res.ok) _throwForResponse(res, payload);
  const rows = Array.isArray(payload) ? payload : ((payload.data as T[]) ?? []);
  return { raw: payload, rows };
}

export async function apiGet(
  path: string,
  authHeaders?: Record<string, string>
): Promise<Record<string, unknown>> {
  const res = await fetch(`${BACKEND_URL}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...(authHeaders ?? {}),
    },
  });
  const payload = (await res.json().catch(() => ({}))) as Record<string, unknown>;
  if (!res.ok) _throwForResponse(res, payload);
  return payload;
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
  if (!res.ok) _throwForResponse(res, payload);
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
  if (!res.ok) _throwForResponse(res, payload);
  return payload;
}
