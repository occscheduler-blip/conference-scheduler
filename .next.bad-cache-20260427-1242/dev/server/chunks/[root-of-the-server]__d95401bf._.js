module.exports = [
"[externals]/next/dist/compiled/next-server/app-route-turbo.runtime.dev.js [external] (next/dist/compiled/next-server/app-route-turbo.runtime.dev.js, cjs)", ((__turbopack_context__, module, exports) => {

const mod = __turbopack_context__.x("next/dist/compiled/next-server/app-route-turbo.runtime.dev.js", () => require("next/dist/compiled/next-server/app-route-turbo.runtime.dev.js"));

module.exports = mod;
}),
"[externals]/next/dist/compiled/@opentelemetry/api [external] (next/dist/compiled/@opentelemetry/api, cjs)", ((__turbopack_context__, module, exports) => {

const mod = __turbopack_context__.x("next/dist/compiled/@opentelemetry/api", () => require("next/dist/compiled/@opentelemetry/api"));

module.exports = mod;
}),
"[externals]/next/dist/compiled/next-server/app-page-turbo.runtime.dev.js [external] (next/dist/compiled/next-server/app-page-turbo.runtime.dev.js, cjs)", ((__turbopack_context__, module, exports) => {

const mod = __turbopack_context__.x("next/dist/compiled/next-server/app-page-turbo.runtime.dev.js", () => require("next/dist/compiled/next-server/app-page-turbo.runtime.dev.js"));

module.exports = mod;
}),
"[externals]/next/dist/server/app-render/work-unit-async-storage.external.js [external] (next/dist/server/app-render/work-unit-async-storage.external.js, cjs)", ((__turbopack_context__, module, exports) => {

const mod = __turbopack_context__.x("next/dist/server/app-render/work-unit-async-storage.external.js", () => require("next/dist/server/app-render/work-unit-async-storage.external.js"));

module.exports = mod;
}),
"[externals]/next/dist/server/app-render/work-async-storage.external.js [external] (next/dist/server/app-render/work-async-storage.external.js, cjs)", ((__turbopack_context__, module, exports) => {

const mod = __turbopack_context__.x("next/dist/server/app-render/work-async-storage.external.js", () => require("next/dist/server/app-render/work-async-storage.external.js"));

module.exports = mod;
}),
"[externals]/next/dist/shared/lib/no-fallback-error.external.js [external] (next/dist/shared/lib/no-fallback-error.external.js, cjs)", ((__turbopack_context__, module, exports) => {

const mod = __turbopack_context__.x("next/dist/shared/lib/no-fallback-error.external.js", () => require("next/dist/shared/lib/no-fallback-error.external.js"));

module.exports = mod;
}),
"[externals]/next/dist/server/app-render/after-task-async-storage.external.js [external] (next/dist/server/app-render/after-task-async-storage.external.js, cjs)", ((__turbopack_context__, module, exports) => {

const mod = __turbopack_context__.x("next/dist/server/app-render/after-task-async-storage.external.js", () => require("next/dist/server/app-render/after-task-async-storage.external.js"));

module.exports = mod;
}),
"[project]/app/api/backend/[...path]/route.ts [app-route] (ecmascript)", ((__turbopack_context__) => {
"use strict";

__turbopack_context__.s([
    "DELETE",
    ()=>DELETE,
    "GET",
    ()=>GET,
    "PATCH",
    ()=>PATCH,
    "POST",
    ()=>POST,
    "PUT",
    ()=>PUT,
    "dynamic",
    ()=>dynamic
]);
var __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$server$2e$js__$5b$app$2d$route$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/node_modules/next/server.js [app-route] (ecmascript)");
;
const dynamic = "force-dynamic";
const hopByHopHeaders = new Set([
    "connection",
    "content-encoding",
    "content-length",
    "host",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade"
]);
function getBackendUrl() {
    return process.env.BACKEND_URL?.replace(/\/+$/, "") ?? "";
}
function buildTargetUrl(request, path) {
    const targetPath = path.join("/");
    const url = new URL(`${getBackendUrl()}/${targetPath}`);
    url.search = request.nextUrl.search;
    return url;
}
function buildRequestHeaders(request) {
    const headers = new Headers();
    request.headers.forEach((value, key)=>{
        const lowerKey = key.toLowerCase();
        if (hopByHopHeaders.has(lowerKey)) return;
        headers.set(key, value);
    });
    return headers;
}
function buildResponseHeaders(response) {
    const headers = new Headers();
    response.headers.forEach((value, key)=>{
        if (hopByHopHeaders.has(key.toLowerCase())) return;
        headers.set(key, value);
    });
    return headers;
}
async function forwardRequest(request, context) {
    const { path } = await context.params;
    const backendUrl = process.env.BACKEND_URL;
    if (!backendUrl) {
        return __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$server$2e$js__$5b$app$2d$route$5d$__$28$ecmascript$29$__["NextResponse"].json({
            detail: "BACKEND_URL is not configured."
        }, {
            status: 500
        });
    }
    const method = request.method.toUpperCase();
    const body = method === "GET" || method === "HEAD" ? undefined : await request.arrayBuffer();
    const targetUrl = buildTargetUrl(request, path);
    let upstreamResponse;
    try {
        upstreamResponse = await fetch(targetUrl, {
            method,
            headers: buildRequestHeaders(request),
            body,
            cache: "no-store"
        });
    } catch (error) {
        const message = error instanceof Error ? error.message : "Unknown upstream error";
        return __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$server$2e$js__$5b$app$2d$route$5d$__$28$ecmascript$29$__["NextResponse"].json({
            detail: `Proxy failed to reach backend at ${targetUrl.origin}. ${message}`
        }, {
            status: 502
        });
    }
    return new __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$server$2e$js__$5b$app$2d$route$5d$__$28$ecmascript$29$__["NextResponse"](upstreamResponse.body, {
        status: upstreamResponse.status,
        headers: buildResponseHeaders(upstreamResponse)
    });
}
async function GET(request, context) {
    return forwardRequest(request, context);
}
async function POST(request, context) {
    return forwardRequest(request, context);
}
async function PUT(request, context) {
    return forwardRequest(request, context);
}
async function PATCH(request, context) {
    return forwardRequest(request, context);
}
async function DELETE(request, context) {
    return forwardRequest(request, context);
}
}),
];

//# sourceMappingURL=%5Broot-of-the-server%5D__d95401bf._.js.map