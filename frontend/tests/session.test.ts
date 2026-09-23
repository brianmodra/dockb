import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../src/renderer/api/http";
import { ApiClient } from "../src/renderer/api/client";
import { checkSession, login } from "../src/renderer/api/session";

function mockFetch(status: number, body: unknown): void {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => new Response(JSON.stringify(body), { status })),
  );
}

const bridge = { openExternal: vi.fn(async () => undefined) };

beforeEach(() => {
  vi.clearAllMocks();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("checkSession", () => {
  it("returns the user when /api/auth/me succeeds", async () => {
    mockFetch(200, {
      user: { id: "u-1", email: "a@b.c", display_name: "A", avatar_url: "" },
    });
    const user = await checkSession(new ApiClient());
    expect(user?.id).toBe("u-1");
  });

  it("returns null on 401 (no session)", async () => {
    mockFetch(401, { detail: "not_authenticated" });
    const user = await checkSession(new ApiClient());
    expect(user).toBeNull();
  });

  it("rethrows other errors", async () => {
    mockFetch(503, { detail: "auth_service_unavailable" });
    await expect(checkSession(new ApiClient())).rejects.toBeInstanceOf(ApiError);
  });
});

describe("login", () => {
  it("fetches the authorization URL and opens the system browser", async () => {
    mockFetch(200, { authorization_url: "https://accounts.google.com/oauth?x=1" });
    const client = new ApiClient();
    await login(client, bridge, "google");
    expect(bridge.openExternal).toHaveBeenCalledWith("https://accounts.google.com/oauth?x=1");
  });
});