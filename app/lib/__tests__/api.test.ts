import { describe, it, expect, vi, beforeEach } from "vitest";
import { apiFetch, apiPost, apiGet, apiPut, apiDelete } from "../api";

function mockFetch(ok: boolean, body: unknown) {
  return vi.fn().mockResolvedValue({
    ok,
    json: () => Promise.resolve(body),
  });
}

beforeEach(() => {
  vi.restoreAllMocks();
});

// ---------------------------------------------------------------------------
// apiFetch
// ---------------------------------------------------------------------------
describe("apiFetch", () => {
  it("returns a plain array response directly", async () => {
    global.fetch = mockFetch(true, [{ id: "1" }]);
    const result = await apiFetch("/items");
    expect(result).toEqual([{ id: "1" }]);
  });

  it("unwraps { data: [...] } response", async () => {
    global.fetch = mockFetch(true, { data: [{ id: "2" }] });
    const result = await apiFetch("/items");
    expect(result).toEqual([{ id: "2" }]);
  });

  it("returns empty array when data key is absent", async () => {
    global.fetch = mockFetch(true, { meta: "info" });
    const result = await apiFetch("/items");
    expect(result).toEqual([]);
  });

  it("throws with the detail message on non-ok response", async () => {
    global.fetch = mockFetch(false, { detail: "Not found" });
    await expect(apiFetch("/missing")).rejects.toThrow("Not found");
  });

  it("throws generic message when no detail provided", async () => {
    global.fetch = mockFetch(false, {});
    await expect(apiFetch("/error")).rejects.toThrow("Request failed");
  });

  it("throws when JSON parsing fails on error response", async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      json: () => Promise.reject(new Error("bad json")),
    });
    await expect(apiFetch("/broken")).rejects.toThrow("Request failed");
  });
});

// ---------------------------------------------------------------------------
// apiPost
// ---------------------------------------------------------------------------
describe("apiPost", () => {
  it("returns raw payload and rows array on success", async () => {
    global.fetch = mockFetch(true, { id: "new", data: [{ id: "r1" }] });
    const result = await apiPost("/items", { name: "Test" });
    expect(result.raw).toMatchObject({ id: "new" });
    expect(result.rows).toEqual([{ id: "r1" }]);
  });

  it("unwraps a plain array body", async () => {
    global.fetch = mockFetch(true, [{ id: "r1" }]);
    const result = await apiPost("/items", {});
    expect(result.rows).toEqual([{ id: "r1" }]);
  });

  it("throws with detail message on failure", async () => {
    global.fetch = mockFetch(false, { detail: "Validation error" });
    await expect(apiPost("/items", {})).rejects.toThrow("Validation error");
  });

  it("sends the body as JSON", async () => {
    global.fetch = mockFetch(true, {});
    await apiPost("/items", { foo: "bar" });
    const [, opts] = (global.fetch as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(JSON.parse(opts.body)).toEqual({ foo: "bar" });
  });
});

// ---------------------------------------------------------------------------
// apiGet
// ---------------------------------------------------------------------------
describe("apiGet", () => {
  it("returns the response payload on success", async () => {
    global.fetch = mockFetch(true, { name: "conf" });
    const result = await apiGet("/conf/1");
    expect(result).toEqual({ name: "conf" });
  });

  it("throws with detail on failure", async () => {
    global.fetch = mockFetch(false, { detail: "Forbidden" });
    await expect(apiGet("/admin")).rejects.toThrow("Forbidden");
  });
});

// ---------------------------------------------------------------------------
// apiPut
// ---------------------------------------------------------------------------
describe("apiPut", () => {
  it("returns the response payload on success", async () => {
    global.fetch = mockFetch(true, { updated: true });
    const result = await apiPut("/items/1", { name: "New" });
    expect(result).toEqual({ updated: true });
  });

  it("uses PUT method", async () => {
    global.fetch = mockFetch(true, {});
    await apiPut("/items/1", {});
    const [, opts] = (global.fetch as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(opts.method).toBe("PUT");
  });

  it("throws on failure", async () => {
    global.fetch = mockFetch(false, { detail: "Not found" });
    await expect(apiPut("/items/99", {})).rejects.toThrow("Not found");
  });
});

// ---------------------------------------------------------------------------
// apiDelete
// ---------------------------------------------------------------------------
describe("apiDelete", () => {
  it("returns the response payload on success", async () => {
    global.fetch = mockFetch(true, { deleted: true });
    const result = await apiDelete("/items/1");
    expect(result).toEqual({ deleted: true });
  });

  it("uses DELETE method", async () => {
    global.fetch = mockFetch(true, {});
    await apiDelete("/items/1");
    const [, opts] = (global.fetch as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(opts.method).toBe("DELETE");
  });

  it("throws on failure", async () => {
    global.fetch = mockFetch(false, { detail: "Unauthorized" });
    await expect(apiDelete("/items/1")).rejects.toThrow("Unauthorized");
  });
});
