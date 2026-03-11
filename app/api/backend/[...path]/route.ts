import { NextRequest, NextResponse } from "next/server";

export const dynamic = "force-dynamic";

const hopByHopHeaders = new Set([
  "connection",
  "content-length",
  "host",
  "keep-alive",
  "proxy-authenticate",
  "proxy-authorization",
  "te",
  "trailer",
  "transfer-encoding",
  "upgrade",
]);

function getBackendUrl() {
  return process.env.BACKEND_URL?.replace(/\/+$/, "") ?? "";
}

function buildTargetUrl(request: NextRequest, path: string[]) {
  const targetPath = path.join("/");
  const url = new URL(`${getBackendUrl()}/${targetPath}`);
  url.search = request.nextUrl.search;
  return url;
}

function buildRequestHeaders(request: NextRequest) {
  const headers = new Headers();

  request.headers.forEach((value, key) => {
    const lowerKey = key.toLowerCase();
    if (hopByHopHeaders.has(lowerKey) || lowerKey === "x-api-key") return;
    headers.set(key, value);
  });

  const backendApiKey = process.env.BACKEND_API_KEY;
  if (backendApiKey) {
    headers.set("X-API-Key", backendApiKey);
  }

  return headers;
}

function buildResponseHeaders(response: Response) {
  const headers = new Headers();

  response.headers.forEach((value, key) => {
    if (hopByHopHeaders.has(key.toLowerCase())) return;
    headers.set(key, value);
  });

  return headers;
}

async function forwardRequest(
  request: NextRequest,
  context: { params: Promise<{ path: string[] }> }
) {
  const { path } = await context.params;
  const backendUrl = process.env.BACKEND_URL;
  if (!backendUrl) {
    return NextResponse.json(
      { detail: "BACKEND_URL is not configured." },
      { status: 500 }
    );
  }
  if (!process.env.BACKEND_API_KEY) {
    return NextResponse.json(
      { detail: "BACKEND_API_KEY is not configured." },
      { status: 500 }
    );
  }

  const method = request.method.toUpperCase();
  const body =
    method === "GET" || method === "HEAD"
      ? undefined
      : await request.arrayBuffer();

  const targetUrl = buildTargetUrl(request, path);
  let upstreamResponse: Response;
  try {
    upstreamResponse = await fetch(targetUrl, {
      method,
      headers: buildRequestHeaders(request),
      body,
      cache: "no-store",
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unknown upstream error";
    return NextResponse.json(
      {
        detail: `Proxy failed to reach backend at ${targetUrl.origin}. ${message}`,
      },
      { status: 502 }
    );
  }

  return new NextResponse(upstreamResponse.body, {
    status: upstreamResponse.status,
    headers: buildResponseHeaders(upstreamResponse),
  });
}

export async function GET(
  request: NextRequest,
  context: { params: Promise<{ path: string[] }> }
) {
  return forwardRequest(request, context);
}

export async function POST(
  request: NextRequest,
  context: { params: Promise<{ path: string[] }> }
) {
  return forwardRequest(request, context);
}

export async function PUT(
  request: NextRequest,
  context: { params: Promise<{ path: string[] }> }
) {
  return forwardRequest(request, context);
}

export async function PATCH(
  request: NextRequest,
  context: { params: Promise<{ path: string[] }> }
) {
  return forwardRequest(request, context);
}

export async function DELETE(
  request: NextRequest,
  context: { params: Promise<{ path: string[] }> }
) {
  return forwardRequest(request, context);
}
