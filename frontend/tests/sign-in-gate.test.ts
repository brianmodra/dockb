import { afterEach, describe, expect, it, vi } from "vitest";
import { openSignInGate } from "../src/renderer/layout/signInGate";
import type { ApiClient } from "../src/renderer/api/client";
import type { DockbBridge } from "../src/renderer/api/bridge";
import { ApiError } from "../src/renderer/api/http";

function user(): { id: string; email: string; display_name: string; avatar_url: string } {
  return { id: "u-1", email: "a@b.c", display_name: "A", avatar_url: "" };
}

function fakeApi(overrides: Record<string, unknown> = {}): ApiClient {
  return {
    getLoginUrl: vi.fn(async () => "https://accounts.google.com/oauth?x=1"),
    getMe: vi.fn(async () => user()),
    ...overrides,
  } as never;
}

const bridge = (): DockbBridge =>
  ({ platform: "linux", openExternal: vi.fn(async () => undefined), quit: vi.fn() }) as DockbBridge;

function modal(): HTMLElement | null {
  return document.querySelector("[data-testid='modal']");
}

async function flush(): Promise<void> {
  await new Promise((r) => setTimeout(r, 0));
}

afterEach(() => {
  document.body.replaceChildren();
  vi.restoreAllMocks();
});

describe("openSignInGate", () => {
  it("shows Sign in and Cancel buttons", async () => {
    openSignInGate(fakeApi(), bridge());
    await flush();
    expect(document.querySelector("[data-testid='sign-in']")).not.toBeNull();
    expect(document.querySelector("[data-testid='sign-in-cancel']")).not.toBeNull();
  });

  it("resolves false when the user cancels", async () => {
    const promise = openSignInGate(fakeApi(), bridge());
    await flush();
    const cancel = document.querySelector<HTMLElement>("[data-testid='sign-in-cancel']")!;
    cancel.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    expect(await promise).toBe(false);
    expect(modal()).toBeNull();
  });

  it("starts the OAuth login and resolves true when the session appears", async () => {
    const api = fakeApi();
    const b = bridge();
    const promise = openSignInGate(api, b);
    await flush();
    document.querySelector<HTMLElement>("[data-testid='sign-in']")!.click();

    expect(await promise).toBe(true);
    expect(b.openExternal).toHaveBeenCalledWith("https://accounts.google.com/oauth?x=1");
    expect(modal()).toBeNull();
  });

  it("stays open and reports when the session has not appeared yet", async () => {
    const onMessage = vi.fn();
    const api = fakeApi({
      getMe: vi.fn(async () => {
        throw new ApiError(401, "not_authenticated");
      }),
    });
    const promise = openSignInGate(api, bridge(), { onMessage });
    await flush();
    document.querySelector<HTMLElement>("[data-testid='sign-in']")!.click();
    await flush();

    expect(onMessage).toHaveBeenCalledWith(expect.stringMatching(/did not complete/i));
    expect(modal()).not.toBeNull();
    document.querySelector<HTMLElement>("[data-testid='sign-in-cancel']")!.click();
    expect(await promise).toBe(false);
  });

  it("routes a failed login into the message panel and stays open", async () => {
    const onMessage = vi.fn();
    const api = fakeApi({
      getLoginUrl: vi.fn(async () => {
        throw new ApiError(503, "auth_service_unavailable");
      }),
    });
    const promise = openSignInGate(api, bridge(), { onMessage });
    await flush();
    document.querySelector<HTMLElement>("[data-testid='sign-in']")!.click();
    await flush();

    expect(onMessage).toHaveBeenCalledWith(expect.stringContaining("auth_service_unavailable"));
    expect(modal()).not.toBeNull();
    document.querySelector<HTMLElement>("[data-testid='sign-in-cancel']")!.click();
    expect(await promise).toBe(false);
  });
});