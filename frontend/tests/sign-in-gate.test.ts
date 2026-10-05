import { afterEach, describe, expect, it, vi } from "vitest";
import { openSignInGate } from "../src/renderer/layout/signInGate";
import type { ApiClient } from "../src/renderer/api/client";
import { ApiError } from "../src/renderer/api/http";

function fakeApi(overrides: Record<string, unknown> = {}): ApiClient {
  return {
    loginWithPassword: vi.fn(async () => ({
      user: { id: "u-1", username: "abby", email: "a@b.c", display_name: "A", avatar_url: "" },
      passwordChangeRequired: false,
    })),
    ...overrides,
  } as never;
}

async function flush(): Promise<void> {
  await new Promise((r) => setTimeout(r, 0));
}

function modal(): HTMLElement | null {
  return document.querySelector("[data-testid='modal']");
}

function field(testid: string): HTMLInputElement {
  return document.querySelector<HTMLInputElement>(`[data-testid='${testid}']`)!;
}

function errorLine(): HTMLElement {
  return document.querySelector<HTMLElement>("[data-testid='sign-in-error']")!;
}

function errorText(): string {
  return errorLine().textContent ?? "";
}

function set(testid: string, value: string): void {
  document.querySelector<HTMLInputElement>(`[data-testid='${testid}']`)!.value = value;
}

async function submit(username: string, password: string): Promise<void> {
  set("sign-in-username", username);
  set("sign-in-password", password);
  document.querySelector<HTMLElement>("[data-testid='sign-in-submit']")!.click();
  await flush();
}

afterEach(() => {
  document.body.replaceChildren();
  vi.restoreAllMocks();
});

describe("openSignInGate", () => {
  it("asks for a username and a password, and offers no provider buttons", async () => {
    openSignInGate(fakeApi());
    await flush();

    expect(field("sign-in-username")).not.toBeNull();
    expect(field("sign-in-password")).not.toBeNull();
    // OAuth is not offered here; an OAuth-only account needs `dockb users set-password`.
    expect(document.body.textContent).not.toMatch(/google|github|continue with/i);
  });

  it("masks the password and labels it for a password manager", async () => {
    openSignInGate(fakeApi());
    await flush();

    expect(field("sign-in-password").type).toBe("password");
    expect(field("sign-in-password").autocomplete).toBe("current-password");
    expect(field("sign-in-username").autocomplete).toBe("username");
  });

  it("resolves false when the user cancels", async () => {
    const promise = openSignInGate(fakeApi());
    await flush();
    document.querySelector<HTMLElement>("[data-testid='sign-in-cancel']")!.click();
    expect(await promise).toBe(false);
    expect(modal()).toBeNull();
  });

  it("signs in with what was typed and resolves true", async () => {
    const api = fakeApi();
    const promise = openSignInGate(api);
    await flush();
    await submit("abby", "hunter2");

    expect(api.loginWithPassword).toHaveBeenCalledWith("abby", "hunter2");
    expect(await promise).toBe(true);
    expect(modal()).toBeNull();
  });

  it("has no error line showing before anything has gone wrong", async () => {
    openSignInGate(fakeApi());
    await flush();
    expect(errorLine().hidden).toBe(true);
    expect(errorText()).toBe("");
  });

  it("shows the server's own refusal and stays open", async () => {
    const api = fakeApi({
      loginWithPassword: vi.fn(async () => {
        throw new ApiError(401, "invalid_username_or_password");
      }),
    });
    const promise = openSignInGate(api);
    await flush();
    await submit("abby", "wrong");

    // The same message for a wrong password, an unknown user and a blocked account.
    expect(errorText()).toContain("invalid_username_or_password");
    expect(errorLine().hidden).toBe(false);
    expect(modal()).not.toBeNull();
    document.querySelector<HTMLElement>("[data-testid='sign-in-cancel']")!.click();
    expect(await promise).toBe(false);
  });

  it("clears the password after a refusal so it does not sit in the DOM", async () => {
    const api = fakeApi({
      loginWithPassword: vi.fn(async () => {
        throw new ApiError(401, "invalid_username_or_password");
      }),
    });
    openSignInGate(api);
    await flush();
    await submit("abby", "wrong");

    expect(field("sign-in-password").value).toBe("");
    // The username survives: a mistyped password is not a reason to retype the name.
    expect(field("sign-in-username").value).toBe("abby");
  });

  it("says to wait when the attempt is throttled, rather than that the password is wrong", async () => {
    const api = fakeApi({
      loginWithPassword: vi.fn(async () => {
        throw new ApiError(429, "too_many_attempts");
      }),
    });
    openSignInGate(api);
    await flush();
    await submit("abby", "hunter2");

    expect(errorText()).toMatch(/wait/i);
    expect(errorText()).not.toMatch(/invalid_username_or_password/);
  });

  it("disables the submit button while the attempt is in flight", async () => {
    let release: (() => void) | undefined;
    const api = fakeApi({
      loginWithPassword: vi.fn(
        () =>
          new Promise((resolve) => {
            release = () =>
              resolve({
                user: { id: "u-1", username: "abby", email: "", display_name: "", avatar_url: "" },
                passwordChangeRequired: false,
              });
          }),
      ),
    });
    const promise = openSignInGate(api);
    await flush();
    const submitButton = document.querySelector<HTMLButtonElement>("[data-testid='sign-in-submit']")!;
    submitButton.click();
    await flush();

    expect(submitButton.disabled).toBe(true);
    release!();
    expect(await promise).toBe(true);
  });

  it("submits on Enter, since a login form is expected to", async () => {
    const api = fakeApi();
    const promise = openSignInGate(api);
    await flush();
    set("sign-in-username", "abby");
    set("sign-in-password", "hunter2");
    document
      .querySelector<HTMLFormElement>("[data-testid='sign-in-form']")!
      .dispatchEvent(new Event("submit", { cancelable: true }));
    await flush();

    expect(api.loginWithPassword).toHaveBeenCalledWith("abby", "hunter2");
    expect(await promise).toBe(true);
  });

  it("never echoes the typed password back into the page", async () => {
    const api = fakeApi({
      loginWithPassword: vi.fn(async () => {
        throw new ApiError(401, "invalid_username_or_password");
      }),
    });
    openSignInGate(api);
    await flush();
    await submit("abby", "hunter2");

    // The refusal names the problem, never the value that was typed.
    expect(document.body.textContent).toContain("invalid_username_or_password");
    expect(document.body.textContent).not.toContain("hunter2");
  });
});