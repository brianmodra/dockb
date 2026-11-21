import { afterEach, describe, expect, it, vi } from "vitest";
import type { ApiClient } from "../src/renderer/api/client";
import { ApiError } from "../src/renderer/api/http";
import type { TwoFactorChallenge } from "../src/renderer/api/types";
import { offerTwoFactorEnrollment, openTwoFactorChallenge } from "../src/renderer/layout/twoFactor";

const profile = { id: "u-1", username: "abby", email: "abby@example.com", display_name: "A", avatar_url: "" };
const challenge: TwoFactorChallenge = {
  twoFactorRequired: true,
  challenge: "challenge-1",
  method: "totp",
  twoFactorEnabled: true,
  twoFactorMethod: "totp",
};

function fakeApi(overrides: Record<string, unknown> = {}): ApiClient {
  return {
    verifyTwoFactor: vi.fn(async () => ({
      user: profile,
      passwordChangeRequired: false,
      twoFactorEnabled: true,
      twoFactorMethod: "totp",
    })),
    beginTwoFactorEnrollment: vi.fn(async (method: string) => ({
      method,
      secret: method === "totp" ? "JBSWY3DPEHPK3PXP" : null,
      provisioningUri: method === "totp" ? "otpauth://totp/DockB:abby?secret=JBSWY3DPEHPK3PXP" : null,
    })),
    confirmTwoFactorEnrollment: vi.fn(async () => undefined),
    resendEmailOtp: vi.fn(async () => undefined),
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
  testid(id).querySelector("input")?.setAttribute("value", value);
  const input = document.querySelector<HTMLInputElement>(`[data-testid='${id}']`)!;
  input.value = value;
}

afterEach(() => {
  document.body.replaceChildren();
  vi.restoreAllMocks();
});

describe("openTwoFactorChallenge", () => {
  it("asks for the code and verifies the challenge", async () => {
    const api = fakeApi();
    const promise = openTwoFactorChallenge(api, challenge);
    await flush();
    set("two-factor-code", "123456");
    testid("two-factor-verify").click();

    expect(await promise).toBe(true);
    expect(api.verifyTwoFactor).toHaveBeenCalledWith("challenge-1", "123456");
    expect(document.querySelector("[data-testid='modal']")).toBeNull();
  });

  it("explains which second factor is being checked", async () => {
    openTwoFactorChallenge(fakeApi(), { ...challenge, method: "email", twoFactorMethod: "email" });
    await flush();
    expect(document.body.textContent).toMatch(/email/i);
  });

  it("shows a refused code and stays open", async () => {
    const api = fakeApi({
      verifyTwoFactor: vi.fn(async () => {
        throw new ApiError(400, "invalid_two_factor_code");
      }),
    });
    const promise = openTwoFactorChallenge(api, challenge);
    await flush();
    set("two-factor-code", "000000");
    testid("two-factor-verify").click();
    await flush();

    expect(document.querySelector("[data-testid='two-factor-error']")?.textContent).toContain(
      "invalid_two_factor_code",
    );
    expect(document.querySelector("[data-testid='modal']")).not.toBeNull();
    testid("two-factor-cancel").click();
    expect(await promise).toBe(false);
  });

  it("resolves false when the user cancels", async () => {
    const promise = openTwoFactorChallenge(fakeApi(), challenge);
    await flush();
    testid("two-factor-cancel").click();
    expect(await promise).toBe(false);
  });
});

describe("offerTwoFactorEnrollment", () => {
  it("can be skipped without changing anything", async () => {
    const api = fakeApi();
    const promise = offerTwoFactorEnrollment(api);
    await flush();
    testid("two-factor-skip").click();
    expect(await promise).toBe(false);
    expect(api.beginTwoFactorEnrollment).not.toHaveBeenCalled();
  });

  it("shows the TOTP secret and provisioning URI before confirming", async () => {
    const api = fakeApi();
    void offerTwoFactorEnrollment(api);
    await flush();
    testid("two-factor-method-totp").click();
    await flush();

    expect(api.beginTwoFactorEnrollment).toHaveBeenCalledWith("totp");
    expect(document.body.textContent).toContain("JBSWY3DPEHPK3PXP");
    expect(document.body.textContent).toContain("otpauth://totp/DockB:abby");
    expect(document.querySelector("[data-testid='two-factor-qr']")).not.toBeNull();
  });

  it("confirms TOTP enrollment with the code the user typed", async () => {
    const api = fakeApi();
    const promise = offerTwoFactorEnrollment(api);
    await flush();
    testid("two-factor-method-totp").click();
    await flush();
    set("two-factor-code", "654321");
    testid("two-factor-confirm").click();

    expect(await promise).toBe(true);
    expect(api.confirmTwoFactorEnrollment).toHaveBeenCalledWith("totp", "654321");
  });

  it("sends and resends an email code", async () => {
    const api = fakeApi();
    const promise = offerTwoFactorEnrollment(api);
    await flush();
    testid("two-factor-method-email").click();
    await flush();
    expect(api.beginTwoFactorEnrollment).toHaveBeenCalledWith("email");

    testid("two-factor-resend").click();
    await flush();
    expect(api.resendEmailOtp).toHaveBeenCalledTimes(1);
    expect(document.querySelector("[data-testid='two-factor-error']")?.textContent ?? "").not.toMatch(
      /email_unavailable/,
    );

    set("two-factor-code", "123456");
    testid("two-factor-confirm").click();
    expect(await promise).toBe(true);
    expect(api.confirmTwoFactorEnrollment).toHaveBeenCalledWith("email", "123456");
  });

  it("keeps the dialog open after a bad code", async () => {
    const api = fakeApi({
      confirmTwoFactorEnrollment: vi.fn(async () => {
        throw new ApiError(400, "invalid_two_factor_code");
      }),
    });
    const promise = offerTwoFactorEnrollment(api);
    await flush();
    testid("two-factor-method-email").click();
    await flush();
    set("two-factor-code", "000000");
    testid("two-factor-confirm").click();
    await flush();

    expect(document.querySelector("[data-testid='two-factor-error']")?.textContent).toContain(
      "invalid_two_factor_code",
    );
    expect(document.querySelector("[data-testid='modal']")).not.toBeNull();
    testid("two-factor-skip").click();
    expect(await promise).toBe(false);
  });
});
