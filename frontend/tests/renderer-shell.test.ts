import { afterEach, describe, expect, it, vi } from "vitest";
import { mountShell } from "../src/renderer/main";
import { ApiError } from "../src/renderer/api/http";

afterEach(() => {
  document.body.replaceChildren();
  vi.restoreAllMocks();
});

describe("renderer shell", () => {
  it("mounts an empty shell window with a menubar placeholder", () => {
    mountShell(document.body);
    const shell = document.querySelector("[data-testid='app-shell']");
    expect(shell).not.toBeNull();
    expect(shell?.querySelector("[data-testid='menubar']")).not.toBeNull();
  });

  it("is idempotent — mounting again replaces, not duplicates", () => {
    mountShell(document.body);
    mountShell(document.body);
    expect(document.querySelectorAll("[data-testid='app-shell']")).toHaveLength(1);
  });

  it("shows the signed-in username in the menubar after boot", async () => {
    const api = {
      getMe: vi.fn(async () => ({ id: "u-1", username: "brian", email: "a@b.c", display_name: "Brian", avatar_url: "" })),
      getAppState: vi.fn(async () => ({ last_document_id: null, panel_widths: null, edit_mode: null })),
      listDocuments: vi.fn(async () => []),
      listChapters: vi.fn(async () => []),
    } as never;
    const bridge = { openExternal: vi.fn(async () => undefined) };
    mountShell(document.body, { api, bridge });
    await new Promise((r) => setTimeout(r, 0));
    const label = document.querySelector<HTMLElement>("[data-testid='user-label']");
    expect(label).not.toBeNull();
    expect(label?.textContent).toBe("brian");
  });

  it("does not render the username when not signed in", async () => {
    const api = {
      getMe: vi.fn(async () => {
        throw new ApiError(401, "not_authenticated");
      }),
      getAppState: vi.fn(async () => ({ last_document_id: null, panel_widths: null, edit_mode: null })),
      listDocuments: vi.fn(async () => []),
      listChapters: vi.fn(async () => []),
    } as never;
    const bridge = { openExternal: vi.fn(async () => undefined) };
    mountShell(document.body, { api, bridge });
    await new Promise((r) => setTimeout(r, 0));
    const label = document.querySelector<HTMLElement>("[data-testid='user-label']");
    expect(label).not.toBeNull();
    expect(label?.hidden).toBe(true);
  });
});