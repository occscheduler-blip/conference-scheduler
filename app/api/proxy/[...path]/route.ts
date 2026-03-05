import { type NextRequest, NextResponse } from "next/server";

const BACKEND_URL = process.env.BACKEND_URL ?? "http://localhost:8000";
const API_KEY = process.env.BACKEND_API_KEY ?? "";

type RouteContext = { params: Promise<{ path: string[] }> };

function targetUrl(path: string[], search: string): string {
  return `${BACKEND_URL}/api/events/${path.join("/")}${search}`;
}

export async function GET(req: NextRequest, context: RouteContext) {
  const { path } = await context.params;
  const res = await fetch(targetUrl(path, req.nextUrl.search), {
    headers: { "X-API-Key": API_KEY },
  });
  const data = await res.json();
  return NextResponse.json(data, { status: res.status });
}

export async function POST(req: NextRequest, context: RouteContext) {
  const { path } = await context.params;
  const body = await req.text();
  const res = await fetch(targetUrl(path, req.nextUrl.search), {
    method: "POST",
    headers: { "X-API-Key": API_KEY, "Content-Type": "application/json" },
    body,
  });
  const data = await res.json();
  return NextResponse.json(data, { status: res.status });
}

export async function PUT(req: NextRequest, context: RouteContext) {
  const { path } = await context.params;
  const body = await req.text();
  const res = await fetch(targetUrl(path, req.nextUrl.search), {
    method: "PUT",
    headers: { "X-API-Key": API_KEY, "Content-Type": "application/json" },
    body,
  });
  const data = await res.json();
  return NextResponse.json(data, { status: res.status });
}

export async function DELETE(req: NextRequest, context: RouteContext) {
  const { path } = await context.params;
  const res = await fetch(targetUrl(path, req.nextUrl.search), {
    method: "DELETE",
    headers: { "X-API-Key": API_KEY },
  });
  if (res.status === 204 || res.headers.get("content-length") === "0") {
    return new NextResponse(null, { status: res.status });
  }
  const data = await res.json();
  return NextResponse.json(data, { status: res.status });
}
