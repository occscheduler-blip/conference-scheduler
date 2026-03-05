# How the API Proxy Works

This document explains the proxy setup in plain terms, assuming you know Python/FastAPI but not Next.js.

---

## The Problem It Solves

Before the proxy, the browser (the user's computer) was making HTTP requests directly to the FastAPI backend. That means the API key had to be sent to the browser so it could include it in requests. Anyone who opened DevTools in their browser could read it.

**Before:**
```
Browser → (X-API-Key: secret) → FastAPI backend
```
The key was visible to anyone who knew where to look.

**After:**
```
Browser → Next.js server → (X-API-Key: secret) → FastAPI backend
```
The key never leaves the server. The browser never sees it.

---

## What Is a Next.js "Route Handler"?

Think of it like a mini FastAPI router living inside the Next.js project. When the browser makes a request to a URL starting with `/api/proxy/...`, Next.js intercepts it and runs server-side code before anything reaches the user's browser.

In FastAPI terms: it's like adding a router to your app that acts as a forwarding proxy to another service.

---

## The Proxy File

**Location:** `app/api/proxy/[...path]/route.ts`

The `[...path]` in the folder name is Next.js syntax for a "catch-all" route — it matches any URL segment after `/api/proxy/`. This is equivalent to a FastAPI route like:

```python
@router.get("/api/proxy/{path:path}")
```

Here is the full file, annotated:

```typescript
// These are read from environment variables — server-side only.
// BACKEND_API_KEY is never sent to the browser.
const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:8000";
const API_KEY = process.env.BACKEND_API_KEY ?? "";

// Builds the real FastAPI URL from whatever path was requested.
// e.g. /api/proxy/symposiums → http://localhost:8000/api/events/symposiums
function targetUrl(path: string[], search: string): string {
  return `${BACKEND_URL}/api/events/${path.join("/")}${search}`;
}

// Handles GET requests. The browser calls /api/proxy/symposiums,
// this function calls http://localhost:8000/api/events/symposiums
// and attaches the API key — which the browser never sees.
export async function GET(req, context) {
  const { path } = await context.params;
  const res = await fetch(targetUrl(path, req.nextUrl.search), {
    headers: { "X-API-Key": API_KEY },   // <-- injected server-side
  });
  const data = await res.json();
  return NextResponse.json(data, { status: res.status });
}

// POST, PUT, DELETE follow the same pattern — forward the request body
// and inject the API key, then return whatever FastAPI responds with.
```

The proxy handlers for POST/PUT also forward the request body (JSON) unchanged. The proxy is transparent — it just adds the API key and passes everything else through.

---

## URL Mapping

| Browser requests | Proxy calls |
|---|---|
| `GET /api/proxy/symposiums` | `GET http://localhost:8000/api/events/symposiums` |
| `GET /api/proxy/students?class_id=CS101` | `GET http://localhost:8000/api/events/students?class_id=CS101` |
| `POST /api/proxy/presentations` | `POST http://localhost:8000/api/events/presentations` |
| `DELETE /api/proxy/students/42` | `DELETE http://localhost:8000/api/events/students/42` |

Query parameters (the `?key=value` part) are forwarded automatically via `req.nextUrl.search`.

---

## Environment Variables

Two env vars are involved. They go in a `.env` file at the project root (same level as `package.json`):

```
NEXT_PUBLIC_BACKEND_URL=http://localhost:8000
BACKEND_API_KEY=your-api-key-here
```

**Why does one have `NEXT_PUBLIC_` and the other doesn't?**

- `NEXT_PUBLIC_*` variables are bundled into the browser JavaScript. Anyone can see them.
- Variables without that prefix are server-only. They are never sent to the browser.

`BACKEND_API_KEY` has no `NEXT_PUBLIC_` prefix, so Next.js keeps it secret. It only exists in the server process — the same environment where the proxy code runs.

`NEXT_PUBLIC_BACKEND_URL` is technically visible to the browser, but that's fine — it's just a hostname, not a secret. (In production this URL would be your deployed backend URL.)

---

## How the Frontend Pages Call the Proxy

Each frontend page (admin, professor, student, etc.) makes fetch calls like this:

```typescript
// No API key, no backend URL — just a relative path
fetch("/api/proxy/symposiums")
fetch(`/api/proxy/students?class_id=${id}`)
```

Because the path starts with `/`, the browser sends the request to the same host serving the Next.js app (e.g. `https://your-app.vercel.app/api/proxy/symposiums`). Next.js catches it, runs the proxy handler on the server, injects the key, calls FastAPI, and returns the result.

---

## Summary

| Concern | Where it lives |
|---|---|
| API key storage | `.env` file, never in browser |
| API key injection | `route.ts` proxy handler, runs server-side |
| Backend URL | `.env` file (`NEXT_PUBLIC_BACKEND_URL`) |
| Frontend calls | Relative URLs like `/api/proxy/...`, no key needed |
| FastAPI | Unchanged — still requires `X-API-Key` on every request |

The FastAPI backend did not need any changes. The proxy is entirely a frontend concern — it just acts as a gatekeeper that holds the secret and forwards requests on the browser's behalf.
