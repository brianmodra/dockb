import { afterEach, describe, expect, it, vi } from "vitest";
import type { ApiClient } from "../src/renderer/api/client";
import { ApiError } from "../src/renderer/api/http";
import { openSignInGate } from "../src/renderer/layout/signInGate";
import { openPasswordResetDialog } from "../src/renderer/layout/passwordReset";

function fakeApi(overrides: Record<string, unknown> = {}): ApiClient {
  return {
    loginWithPassword: vi.fn(async () => ({
      user: { id: "u-1", username: "abby", email: "a@b.c", display_name: "A", avatar_url: "" },
      passwordChangeRequired: false,
      twoFactorEnabled: false,
      twoFactorMethod: null,
    })),
    requestPasswordReset: vi.fn(async () => undefined),
    confirmPasswordReset: vi.fn(async () => undefined),
    ...overrides,
  } as never;
}

async function flush(): Promise<void> {
  await new Promise((resolve) => setTimeout(resolve, 0));
}

function testid(id: string): HTMLElement {
  return document.querySelector<HTMLElement>(`[data-testid='${id}']`)!;
}

function set(id: string, value: string): void {
  document.querySelector<HTMLInputElement>(`[data-testid='${id}']`)!.value = value;
}

afterEach(() => {
  document.body.replaceChildren();
  vi.restoreAllMocks();
});

describe("password reset request", () => {
  it("is offered from the sign-in gate", async () => {
    openSignInGate(fakeApi());
    await flush();
    expect(testid("sign-in-forgot-password")).not.toBeNull();
  });

  it("posts the typed email and says to check the inbox", async () => {
    const api = fakeApi();
    openSignInGate(api);
    await flush();
    testid("sign-in-forgot-password").click();
    await flush();
    set("password-reset-email", "abby@example.com");
    testid("password-reset-send").click();
    await flush();

    expect(api.requestPasswordReset).toHaveBeenCalledWith("abby@example.com");
    expect(document.body.textContent).toMatch(/check your email/i);
    expect(testid("password-reset-done")).not.toBeNull();
    testid("password-reset-done").click();
    expect(document.querySelector("[data-testid='password-reset-done']")).toBeNull();
  });

  it("says so when email delivery is not configured", async () => {
    const api = fakeApi({
      requestPasswordReset: vi.fn(async () => {
        throw new ApiError(503, "email_unavailable");
      }),
    });
    openSignInGate(api);
    await flush();
    testid("sign-in-forgot-password").click();
    await flush();
    set("password-reset-email", "abby@example.com");
    testid("password-reset-send").click();
    await flush();

    expect(document.querySelector("[data-testid='password-reset-error']")?.textContent).toContain(
      "email_unavailable",
    );
    expect(document.querySelector("[data-testid='modal']")).not.toBeNull();
  });
});

describe("password reset confirmation", () => {
  it("posts the token and both copies of the new password", async () => {
    const api = fakeApi();
    const onMessage = vi.fn();
    const promise = openPasswordResetDialog(api, "reset-token", onMessage);
    await flush();
    set("password-reset-new", "a long enough password");
    set("password-reset-confirm", "a long enough password");
    testid("password-reset-submit").click();

    expect(await promise).toBe(true);
    expect(api.confirmPasswordReset).toHaveBeenCalledWith("reset-token", "a long enough password");
    expect(onMessage).toHaveBeenCalledWith(expect.stringMatching(/password changed/i));
    expect(document.querySelector("[data-testid='modal']")).toBeNull();
  });

  it("refuses mismatched passwords before calling the server", async () => {
    const api = fakeApi();
    const promise = openPasswordResetDialog(api, "reset-token");
    await flush();
    set("password-reset-new", "one password");
    set("password-reset-confirm", "another password");
    testid("password-reset-submit").click();
    await flush();

    expect(api.confirmPasswordReset).not.toHaveBeenCalled();
    expect(document.querySelector("[data-testid='password-reset-error']")?.textContent).toMatch(/match/i);
    expect(document.querySelector("[data-testid='modal']")).not.toBeNull();
    testid("password-reset-cancel").click();
    expect(await promise).toBe(false);
  });

  it("shows an invalid token and stays open", async () => {
    const api = fakeApi({
      confirmPasswordReset: vi.fn(async () => {
        throw new ApiError(400, "invalid_reset_token");
      }),
    });
    const promise = openPasswordResetDialog(api, "old-token");
    await flush();
    set("password-reset-new", "a long enough password");
    set("password-reset-confirm", "a long enough password");
    testid("password-reset-submit").click();
    await flush();

    expect(document.querySelector("[data-testid='password-reset-error']")?.textContent).toContain(
      "invalid_reset_token",
    );
    expect(document.querySelector("[data-testid='modal']")).not.toBeNull();
    testid("password-reset-cancel").click();
    expect(await promise).toBe(false);
  });
});
