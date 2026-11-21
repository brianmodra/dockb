import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../src/renderer/api/http";
import { ApiClient } from "../src/renderer/api/client";
import {
  beginTwoFactorEnrollment,
  changePassword,
  checkSession,
  confirmPasswordReset,
  confirmTwoFactorEnrollment,
  requestPasswordReset,
  resendEmailOtp,
  signInWithPassword,
  signOut,
  verifyTwoFactor,
} from "../src/renderer/api/session";

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

  it("returns a two-factor challenge instead of a session when one is required", async () => {
    mockFetch(200, {
      two_factor_required: true,
      challenge: "challenge-1",
      method: "email",
      two_factor_enabled: true,
      two_factor_method: "email",
    });
    const result = await signInWithPassword(new ApiClient(), "abby", "hunter2");

    expect(result).toMatchObject({
      twoFactorRequired: true,
      challenge: "challenge-1",
      method: "email",
    });
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

describe("two-factor and recovery helpers", () => {
  it("reads 2FA state from the session response", async () => {
    mockFetch(200, {
      user: profile,
      password_change_required: false,
      two_factor_enabled: true,
      two_factor_method: "totp",
    });
    const session = await checkSession(new ApiClient());
    expect(session?.twoFactorEnabled).toBe(true);
    expect(session?.twoFactorMethod).toBe("totp");
  });

  it("verifies a challenge and returns the session", async () => {
    mockFetch(200, {
      user: profile,
      password_change_required: false,
      two_factor_enabled: true,
      two_factor_method: "totp",
    });
    const session = await verifyTwoFactor(new ApiClient(), "challenge-1", "123456");

    const call = fetchCalls()[0];
    expect(call.url).toBe("/api/auth/2fa/verify");
    expect(bodyOf(call)).toEqual({ challenge: "challenge-1", code: "123456" });
    expect(session.twoFactorEnabled).toBe(true);
  });

  it("asks for a password-reset email", async () => {
    mockFetch(202, { status: "accepted" });
    await requestPasswordReset(new ApiClient(), "abby@example.com");
    expect(fetchCalls()[0].url).toBe("/api/auth/password-reset/request");
    expect(bodyOf(fetchCalls()[0])).toEqual({ email: "abby@example.com" });
  });

  it("confirms a password reset", async () => {
    mockFetch(200, { status: "ok" });
    await confirmPasswordReset(new ApiClient(), "reset-token", "a new password");
    expect(fetchCalls()[0].url).toBe("/api/auth/password-reset/confirm");
    expect(bodyOf(fetchCalls()[0])).toEqual({ token: "reset-token", new_password: "a new password" });
  });

  it("begins TOTP enrollment", async () => {
    mockFetch(200, { method: "totp", secret: "SECRET", provisioning_uri: "otpauth://totp/x" });
    const enrollment = await beginTwoFactorEnrollment(new ApiClient(), "totp");
    expect(fetchCalls()[0].url).toBe("/api/auth/2fa/enroll");
    expect(bodyOf(fetchCalls()[0])).toEqual({ method: "totp" });
    expect(enrollment.secret).toBe("SECRET");
  });

  it("confirms enrollment and resends an email code", async () => {
    mockFetch(200, { status: "ok" });
    await confirmTwoFactorEnrollment(new ApiClient(), "email", "123456");
    expect(fetchCalls()[0].url).toBe("/api/auth/2fa/confirm");
    expect(bodyOf(fetchCalls()[0])).toEqual({ method: "email", code: "123456" });

    await resendEmailOtp(new ApiClient());
    expect(fetchCalls()[1].url).toBe("/api/auth/2fa/resend");
    expect(fetchCalls()[1].init.method).toBe("POST");
  });
});