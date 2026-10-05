import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../src/renderer/api/http";
import { ApiClient } from "../src/renderer/api/client";
import { changePassword, checkSession, signInWithPassword, signOut } from "../src/renderer/api/session";

function mockFetch(status: number, body: unknown): void {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => new Response(JSON.stringify(body), { status })),
  );
}

function fetchCalls(): Array<{ url: string; init: RequestInit }> {
  return vi
    .mocked(globalThis.fetch)
    .mock.calls.map(([url, init]) => ({ url: String(url), init: (init ?? {}) as RequestInit }));
}

function bodyOf(call: { init: RequestInit }): Record<string, unknown> {
  return JSON.parse(String(call.init.body)) as Record<string, unknown>;
}

const profile = { id: "u-1", username: "abby", email: "a@b.c", display_name: "A", avatar_url: "" };

beforeEach(() => {
  vi.clearAllMocks();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("checkSession", () => {
  it("returns the user and whether a change is pending when /api/auth/me succeeds", async () => {
    mockFetch(200, { user: profile, password_change_required: true });
    const session = await checkSession(new ApiClient());
    expect(session?.user.username).toBe("abby");
    expect(session?.passwordChangeRequired).toBe(true);
  });

  it("reports no pending change for an ordinary session", async () => {
    mockFetch(200, { user: profile, password_change_required: false });
    const session = await checkSession(new ApiClient());
    expect(session?.passwordChangeRequired).toBe(false);
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

describe("signInWithPassword", () => {
  it("posts the credentials and returns the session", async () => {
    mockFetch(200, { user: profile, password_change_required: true });
    const session = await signInWithPassword(new ApiClient(), "abby", "hunter2");

    const call = fetchCalls()[0];
    expect(call.url).toBe("/api/auth/login/password");
    expect(call.init.method).toBe("POST");
    expect(bodyOf(call)).toEqual({ username: "abby", password: "hunter2" });
    expect(session.user.username).toBe("abby");
    expect(session.passwordChangeRequired).toBe(true);
  });

  it("surfaces the server's generic refusal", async () => {
    mockFetch(401, { detail: "invalid_username_or_password" });
    await expect(signInWithPassword(new ApiClient(), "abby", "wrong")).rejects.toThrow(
      "invalid_username_or_password",
    );
  });

  it("distinguishes a throttle from a wrong password", async () => {
    mockFetch(429, { detail: "too_many_attempts" });
    await expect(signInWithPassword(new ApiClient(), "abby", "wrong")).rejects.toMatchObject({
      status: 429,
    });
  });
});

describe("changePassword", () => {
  it("posts both passwords", async () => {
    mockFetch(200, { status: "ok", signed_out: true });
    await changePassword(new ApiClient(), "temporary", "a long enough password");

    const call = fetchCalls()[0];
    expect(call.url).toBe("/api/auth/change-password");
    expect(bodyOf(call)).toEqual({
      current_password: "temporary",
      new_password: "a long enough password",
    });
  });

  it("reports a refused current password", async () => {
    mockFetch(401, { detail: "invalid_username_or_password" });
    await expect(changePassword(new ApiClient(), "wrong", "a long enough password")).rejects.toThrow(
      "invalid_username_or_password",
    );
  });

  it("reports the policy's own reason for a bad new password", async () => {
    mockFetch(400, { detail: "password_too_short: at least 12 characters" });
    await expect(changePassword(new ApiClient(), "temporary", "short")).rejects.toThrow(
      "password_too_short",
    );
  });
});

describe("signOut", () => {
  it("posts to the logout route", async () => {
    mockFetch(200, { status: "ok" });
    await signOut(new ApiClient());
    const call = fetchCalls()[0];
    expect(call.url).toBe("/api/auth/logout");
    expect(call.init.method).toBe("POST");
  });
});