import { afterEach, describe, expect, it, vi } from "vitest";

import { request, setNetworkFailureHandler } from "../src/renderer/api/http";

type FetchInit = { headers?: Record<string, string> };

function sentHeaders(): Record<string, string> {
  const calls = vi.mocked(globalThis.fetch).mock.calls;
  const init = (calls[0][1] ?? {}) as FetchInit;
  return (init.headers ?? {}) as Record<string, string>;
}

function mockOk(): void {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => new Response(JSON.stringify({ ok: true }), { status: 200 })),
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
  setNetworkFailureHandler(null);
});

describe("request headers", () => {
  it("labels a JSON body as JSON", async () => {
    mockOk();
    await request("/api/thing", { method: "POST", body: JSON.stringify({ a: 1 }) });
    expect(sentHeaders()["Content-Type"]).toBe("application/json");
  });

  it("leaves a GET without a body labelled as JSON", async () => {
    mockOk();
    await request("/api/thing");
    expect(sentHeaders()["Content-Type"]).toBe("application/json");
  });

  it("sends no Content-Type for a FormData body so the browser sets the boundary", async () => {
    mockOk();
    const form = new FormData();
    form.append("files", new Blob(["body"]), "Doc/Act I/Opening.md");
    await request("/api/import", { method: "POST", body: form });
    expect(sentHeaders()["Content-Type"]).toBeUndefined();
  });

  it("sends no Content-Type for an empty FormData body", async () => {
    mockOk();
    await request("/api/import", { method: "POST", body: new FormData() });
    expect(sentHeaders()["Content-Type"]).toBeUndefined();
  });

  it("still honours a Content-Type the caller set on a FormData body", async () => {
    mockOk();
    const form = new FormData();
    await request("/api/import", {
      method: "POST",
      body: form,
      headers: { "Content-Type": "multipart/form-data" },
    });
    expect(sentHeaders()["Content-Type"]).toBe("multipart/form-data");
  });

  it("still lets a caller override the JSON default", async () => {
    mockOk();
    await request("/api/thing", {
      method: "POST",
      body: JSON.stringify({ a: 1 }),
      headers: { "Content-Type": "application/merge-patch+json" },
    });
    expect(sentHeaders()["Content-Type"]).toBe("application/merge-patch+json");
  });

  it("labels a plain string body as JSON", async () => {
    mockOk();
    await request("/api/thing", { method: "POST", body: "raw" });
    expect(sentHeaders()["Content-Type"]).toBe("application/json");
  });

  it("exempts only FormData, leaving other body types on the JSON default", async () => {
    mockOk();
    await request("/api/thing", { method: "POST", body: new URLSearchParams({ a: "1" }) });
    expect(sentHeaders()["Content-Type"]).toBe("application/json");
  });
});

describe("network failures", () => {
  it("reports a failed fetch to the network failure handler before rethrowing", async () => {
    const failure = new TypeError("Failed to fetch");
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw failure;
      }),
    );
    const onFailure = vi.fn();
    setNetworkFailureHandler(onFailure);

    await expect(request("/api/thing")).rejects.toBe(failure);
    expect(onFailure).toHaveBeenCalledTimes(1);
    expect(onFailure).toHaveBeenCalledWith(failure);
  });

  it("does not report an HTTP error as a network failure", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(JSON.stringify({ detail: "nope" }), { status: 400 })),
    );
    const onFailure = vi.fn();
    setNetworkFailureHandler(onFailure);

    await expect(request("/api/thing")).rejects.toMatchObject({ status: 400 });
    expect(onFailure).not.toHaveBeenCalled();
  });
});
