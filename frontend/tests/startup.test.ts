import { afterEach, describe, expect, it, vi } from "vitest";
import { runStartup } from "../src/renderer/state/startup";
import type { AppState } from "../src/renderer/api/types";
import { mountShell } from "../src/renderer/main";
import { ApiError } from "../src/renderer/api/http";

function state(overrides: Partial<AppState> = {}): AppState {
  return { last_document_id: null, panel_widths: null, edit_mode: null, ...overrides };
}

function user(): { id: string; username: string; email: string; display_name: string; avatar_url: string } {
  return { id: "u-1", username: "abby", email: "a@b.c", display_name: "A", avatar_url: "" };
}

afterEach(() => {
  document.body.replaceChildren();
  vi.restoreAllMocks();
});

describe("runStartup", () => {
  it("opens the saved document when app state has a last document", async () => {
    const loadDocument = vi.fn(async () => undefined);
    const pickDocument = vi.fn(async () => "picked");
    await runStartup({
      loadDocument,
      pickDocument,
      restoreView: vi.fn(),
      savedState: state({ last_document_id: "d1" }),
    });
    expect(loadDocument).toHaveBeenCalledWith("d1");
    expect(pickDocument).not.toHaveBeenCalled();
  });

  it("opens the document picker when app state has no last document", async () => {
    const loadDocument = vi.fn(async () => undefined);
    const pickDocument = vi.fn(async () => "picked");
    await runStartup({
      loadDocument,
      pickDocument,
      restoreView: vi.fn(),
      savedState: state({ last_document_id: null }),
    });
    expect(pickDocument).toHaveBeenCalledTimes(1);
    expect(loadDocument).toHaveBeenCalledWith("picked");
  });

  it("does nothing when the picker is cancelled and no document is chosen", async () => {
    const loadDocument = vi.fn(async () => undefined);
    const pickDocument = vi.fn(async () => null);
    await runStartup({
      loadDocument,
      pickDocument,
      restoreView: vi.fn(),
      savedState: state({ last_document_id: null }),
    });
    expect(loadDocument).not.toHaveBeenCalled();
  });

  it("restores panel widths and edit mode from app state", async () => {
    const restoreView = vi.fn();
    await runStartup({
      loadDocument: vi.fn(async () => undefined),
      pickDocument: vi.fn(async () => null),
      restoreView,
      savedState: state({ panel_widths: { left: 320 }, edit_mode: "raw" }),
    });
    expect(restoreView).toHaveBeenCalledWith({ left: 320 }, "raw");
  });
});

describe("mountShell startup integration", () => {
  it("mounts the shell, restoring the saved document", async () => {
    const api = {
      getMe: vi.fn(async () => user()),
      getAppState: vi.fn(async () => state()),
      listDocuments: vi.fn(async () => []),
      listChapters: vi.fn(async () => []),
    } as never;
    const bridge = { openExternal: vi.fn(async () => undefined) } as never;
    const layout = mountShell(document.body, { api, bridge });
    await new Promise((r) => setTimeout(r, 0));
    expect(layout).toBeDefined();
    expect(document.querySelector("[data-testid='app-shell']")).not.toBeNull();
  });

  it("shows the sign-in gate when there is no session", async () => {
    const api = {
      getMe: vi.fn(async () => {
        throw new ApiError(401, "not_authenticated");
      }),
      getAppState: vi.fn(async () => state()),
      listDocuments: vi.fn(async () => []),
      listChapters: vi.fn(async () => []),
    } as never;
    const bridge = { openExternal: vi.fn(async () => undefined) } as never;
    mountShell(document.body, { api, bridge });
    await new Promise((r) => setTimeout(r, 0));
    expect(document.querySelector("[data-testid='sign-in']")).not.toBeNull();
  });

  it("stays idle when the sign-in gate is cancelled", async () => {
    const api = {
      getMe: vi.fn(async () => {
        throw new ApiError(401, "not_authenticated");
      }),
      getAppState: vi.fn(async () => state()),
      listDocuments: vi.fn(async () => []),
      listChapters: vi.fn(async () => []),
      getChapterDocument: vi.fn(async () => ({ content: "", summary: null })),
    } as never;
    const bridge = { openExternal: vi.fn(async () => undefined) } as never;
    mountShell(document.body, { api, bridge });
    await new Promise((r) => setTimeout(r, 0));
    const cancel = document.querySelector<HTMLElement>("[data-testid='sign-in-cancel']")!;
    cancel.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    await new Promise((r) => setTimeout(r, 0));
    expect(api.listChapters).not.toHaveBeenCalled();
  });
});