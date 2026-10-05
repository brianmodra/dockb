import { afterEach, describe, expect, it, vi } from "vitest";
import { ensureSignedIn } from "../src/renderer/layout/signInFlow";
import type { ApiClient } from "../src/renderer/api/client";
import type { Session } from "../src/renderer/api/session";
import { ApiError } from "../src/renderer/api/http";

const profile = { id: "u-1", username: "abby", email: "a@b.c", display_name: "A", avatar_url: "" };

function fakeApi(options: {
  me: () => Promise<Session>;
  login?: ReturnType<typeof vi.fn>;
  change?: ReturnType<typeof vi.fn>;
  logout?: ReturnType<typeof vi.fn>;
}): ApiClient {
  return {
    getMe: vi.fn(options.me),
    loginWithPassword:
      options.login ?? vi.fn(async () => ({ user: profile, passwordChangeRequired: false })),
    changePassword: options.change ?? vi.fn(async () => undefined),
    logout: options.logout ?? vi.fn(async () => undefined),
  } as never;
}

async function flush(): Promise<void> {
  await new Promise((r) => setTimeout(r, 0));
}

function click(testid: string): void {
  document.querySelector<HTMLElement>(`[data-testid='${testid}']`)!.click();
}

function set(testid: string, value: string): void {
  document.querySelector<HTMLInputElement>(`[data-testid='${testid}']`)!.value = value;
}

const signedIn = (): Promise<Session> =>
  Promise.resolve({ user: profile, passwordChangeRequired: false });

const pending = (): Promise<Session> =>
  Promise.resolve({ user: profile, passwordChangeRequired: true });

afterEach(() => {
  document.body.replaceChildren();
  vi.restoreAllMocks();
});

describe("ensureSignedIn", () => {
  it("does nothing when the session is already good", async () => {
    const api = fakeApi({ me: signedIn });
    const session = await ensureSignedIn(api);

    expect(session?.user.username).toBe("abby");
    expect(document.querySelector("[data-testid='modal']")).toBeNull();
  });

  it("shows the gate when there is no session", async () => {
    // 401 until the gate has been answered, then a session — the real order.
    let calls = 0;
    const api = fakeApi({
      me: async () => {
        calls += 1;
        if (calls === 1) {
          throw new ApiError(401, "not_authenticated");
        }
        return signedIn();
      },
    });
    const promise = ensureSignedIn(api);
    await flush();

    expect(document.querySelector("[data-testid='sign-in-submit']")).not.toBeNull();
    set("sign-in-username", "abby");
    set("sign-in-password", "hunter2");
    click("sign-in-submit");
    await flush();

    expect((await promise)?.user.username).toBe("abby");
  });

  it("returns null when the user cancels the gate", async () => {
    const api = fakeApi({
      me: async () => {
        throw new ApiError(401, "not_authenticated");
      },
    });
    const promise = ensureSignedIn(api);
    await flush();
    click("sign-in-cancel");

    expect(await promise).toBeNull();
  });

  it("asks for the change before loading anything, when one is pending", async () => {
    const api = fakeApi({ me: () => pending() });
    const promise = ensureSignedIn(api);
    await flush();

    expect(document.querySelector("[data-testid='change-password-submit']")).not.toBeNull();
    set("change-password-current", "temporary");
    set("change-password-new", "a long enough password");
    click("change-password-submit");
    await flush();

    // Changing ends the session, so the gate comes back for the new password.
    expect(document.querySelector("[data-testid='sign-in-submit']")).not.toBeNull();
    set("sign-in-username", "abby");
    set("sign-in-password", "a long enough password");
    click("sign-in-submit");
    await flush();

    expect((await promise)?.user.username).toBe("abby");
    expect(api.loginWithPassword).toHaveBeenLastCalledWith("abby", "a long enough password");
  });

  it("says the password changed when it asks for the new one", async () => {
    const onMessage = vi.fn();
    let calls = 0;
    const api = fakeApi({
      me: async () => {
        calls += 1;
        // First call reports the pending change; the one after the gate answers clean.
        return calls === 1 ? { user: profile, passwordChangeRequired: true } : signedIn();
      },
      login: vi.fn(async () => {
        calls += 1;
        return { user: profile, passwordChangeRequired: false };
      }),
    });
    const promise = ensureSignedIn(api, { onMessage });
    await flush();
    set("change-password-current", "temporary");
    set("change-password-new", "a long enough password");
    click("change-password-submit");
    await flush();
    set("sign-in-username", "abby");
    set("sign-in-password", "a long enough password");
    click("sign-in-submit");
    await flush();

    await promise;
    expect(onMessage).toHaveBeenCalledWith(expect.stringMatching(/password (has )?changed/i));
  });

  it("stops at the sign-in gate when the user signs out of the change dialog", async () => {
    const api = fakeApi({ me: () => pending() });
    const promise = ensureSignedIn(api);
    await flush();
    click("change-password-sign-out");

    expect(await promise).toBeNull();
    expect(api.logout).toHaveBeenCalled();
  });

  it("does not sign the user back in by itself after a change", async () => {
    const api = fakeApi({ me: () => pending() });
    const promise = ensureSignedIn(api);
    await flush();
    set("change-password-current", "temporary");
    set("change-password-new", "a long enough password");
    click("change-password-submit");
    await flush();

    // The new password is not held in memory to be posted a second time.
    expect(api.loginWithPassword).not.toHaveBeenCalled();
    click("sign-in-cancel");
    expect(await promise).toBeNull();
  });
});