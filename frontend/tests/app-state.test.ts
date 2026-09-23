import { afterEach, describe, expect, it, vi } from "vitest";
import { AppStateController } from "../src/renderer/state/appState";
import type { AppState, AppStatePatch } from "../src/renderer/api/types";

function state(overrides: Partial<AppState> = {}): AppState {
  return { last_document_id: null, panel_widths: null, edit_mode: null, ...overrides };
}

function fakeApi(overrides: Partial<Record<"getAppState" | "putAppState", ReturnType<typeof vi.fn>>> = {}) {
  return {
    getAppState: vi.fn(async (): Promise<AppState> => state()),
    putAppState: vi.fn(async (patch: AppStatePatch): Promise<AppState> => state({ ...patch })),
    ...overrides,
  };
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("AppStateController", () => {
  it("restores the saved state unchanged", async () => {
    const api = fakeApi({
      getAppState: vi.fn(async () => state({ last_document_id: "d1", edit_mode: "raw", panel_widths: { left: 300 } })),
    });
    const controller = new AppStateController(api);
    const restored = await controller.load();
    expect(restored.last_document_id).toBe("d1");
    expect(restored.edit_mode).toBe("raw");
    expect(restored.panel_widths).toEqual({ left: 300 });
  });

  it("returns a default empty state when nothing is stored", async () => {
    const controller = new AppStateController(fakeApi());
    const restored = await controller.load();
    expect(restored).toEqual(state());
  });

  it("persists the last document id", async () => {
    const api = fakeApi();
    const controller = new AppStateController(api);
    await controller.saveLastDocument("d2");
    expect(api.putAppState).toHaveBeenCalledWith({ last_document_id: "d2" });
  });

  it("persists the edit mode", async () => {
    const api = fakeApi();
    const controller = new AppStateController(api);
    await controller.saveEditMode("raw");
    expect(api.putAppState).toHaveBeenCalledWith({ edit_mode: "raw" });
  });

  it("persists panel widths", async () => {
    const api = fakeApi();
    const controller = new AppStateController(api);
    await controller.savePanelWidths({ left: 240, right: 120, message: 40 });
    expect(api.putAppState).toHaveBeenCalledWith({
      panel_widths: { left: 240, right: 120, message: 40 },
    });
  });

  it("reports persistence failures through the message panel", async () => {
    const onMessage = vi.fn();
    const api = fakeApi({
      putAppState: vi.fn(async () => {
        throw new Error("state write failed");
      }),
    });
    const controller = new AppStateController(api, { onMessage });
    await controller.saveEditMode("raw");
    expect(onMessage).toHaveBeenCalledWith(expect.stringContaining("state write failed"));
    expect(onMessage).toHaveBeenCalledWith(expect.stringMatching(/app state/i));
  });
});