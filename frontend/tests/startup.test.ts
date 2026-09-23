import { afterEach, describe, expect, it, vi } from "vitest";
import { runStartup } from "../src/renderer/state/startup";
import type { AppState } from "../src/renderer/api/types";
import { mountShell } from "../src/renderer/main";

function state(overrides: Partial<AppState> = {}): AppState {
  return { last_document_id: null, panel_widths: null, edit_mode: null, ...overrides };
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
      getAppState: vi.fn(async () => state()),
      listDocuments: vi.fn(async () => []),
      listChapters: vi.fn(async () => []),
    } as never;
    const layout = mountShell(document.body, { api });
    await new Promise((r) => setTimeout(r, 0));
    expect(layout).toBeDefined();
    expect(document.querySelector("[data-testid='app-shell']")).not.toBeNull();
  });
});