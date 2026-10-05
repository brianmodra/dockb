import { afterEach, describe, expect, it, vi } from "vitest";
import { openChangePasswordDialog } from "../src/renderer/layout/changePasswordDialog";
import type { ApiClient } from "../src/renderer/api/client";
import { ApiError } from "../src/renderer/api/http";

function fakeApi(overrides: Record<string, unknown> = {}): ApiClient {
  return {
    changePassword: vi.fn(async () => undefined),
    logout: vi.fn(async () => undefined),
    ...overrides,
  } as never;
}

async function flush(): Promise<void> {
  await new Promise((r) => setTimeout(r, 0));
}

function field(testid: string): HTMLInputElement {
  return document.querySelector<HTMLInputElement>(`[data-testid='${testid}']`)!;
}

function errorLine(): HTMLElement {
  return document.querySelector<HTMLElement>("[data-testid='change-password-error']")!;
}

function errorText(): string {
  return errorLine().textContent ?? "";
}

async function submit(current: string, next: string): Promise<void> {
  field("change-password-current").value = current;
  field("change-password-new").value = next;
  document.querySelector<HTMLElement>("[data-testid='change-password-submit']")!.click();
  await flush();
}

afterEach(() => {
  document.body.replaceChildren();
  vi.restoreAllMocks();
});

describe("openChangePasswordDialog", () => {
  it("asks for the current password and its replacement", async () => {
    openChangePasswordDialog(fakeApi());
    await flush();

    expect(field("change-password-current").type).toBe("password");
    expect(field("change-password-new").type).toBe("password");
    expect(field("change-password-current").autocomplete).toBe("current-password");
    expect(field("change-password-new").autocomplete).toBe("new-password");
  });

  it("offers no way to dismiss it without choosing", async () => {
    openChangePasswordDialog(fakeApi());
    await flush();

    // No cancel button: every manuscript route is closed until this is done.
    expect(document.querySelector("[data-testid='change-password-cancel']")).toBeNull();
  });

  it("changes the password and reports that it did", async () => {
    const api = fakeApi();
    const promise = openChangePasswordDialog(api);
    await flush();
    await submit("temporary", "a long enough password");

    expect(api.changePassword).toHaveBeenCalledWith("temporary", "a long enough password");
    expect(await promise).toBe("changed");
    expect(document.querySelector("[data-testid='modal']")).toBeNull();
  });

  it("keeps the dialog open and explains a refused current password", async () => {
    const api = fakeApi({
      changePassword: vi.fn(async () => {
        throw new ApiError(401, "invalid_username_or_password");
      }),
    });
    const promise = openChangePasswordDialog(api);
    await flush();
    await submit("wrong", "a long enough password");

    expect(errorText()).toContain("invalid_username_or_password");
    expect(errorLine().hidden).toBe(false);
    expect(document.querySelector("[data-testid='modal']")).not.toBeNull();
    expect(field("change-password-current").value).toBe("");
    document.querySelector<HTMLElement>("[data-testid='change-password-sign-out']")!.click();
    expect(await promise).toBe("signed-out");
  });

  it("shows the policy's reason for a rejected new password", async () => {
    const api = fakeApi({
      changePassword: vi.fn(async () => {
        throw new ApiError(400, "password_too_short: at least 12 characters");
      }),
    });
    openChangePasswordDialog(api);
    await flush();
    await submit("temporary", "short");

    // The reason travels with the refusal, so the dialog need not re-derive the policy.
    expect(errorText()).toContain("password_too_short");
  });

  it("lets somebody on the wrong account sign out and get back to the gate", async () => {
    const api = fakeApi();
    const promise = openChangePasswordDialog(api);
    await flush();
    document.querySelector<HTMLElement>("[data-testid='change-password-sign-out']")!.click();

    expect(api.logout).toHaveBeenCalled();
    expect(await promise).toBe("signed-out");
    expect(document.querySelector("[data-testid='modal']")).toBeNull();
  });

  it("stays open when signing out fails, rather than claiming it worked", async () => {
    const api = fakeApi({
      logout: vi.fn(async () => {
        throw new ApiError(503, "auth_service_unavailable");
      }),
    });
    openChangePasswordDialog(api);
    await flush();
    document.querySelector<HTMLElement>("[data-testid='change-password-sign-out']")!.click();
    await flush();

    expect(errorText()).toContain("auth_service_unavailable");
    expect(errorLine().hidden).toBe(false);
    expect(document.querySelector("[data-testid='modal']")).not.toBeNull();
  });
});