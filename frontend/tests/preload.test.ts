import { describe, expect, it, vi } from "vitest";

const { contextBridge, ipcRenderer } = vi.hoisted(() => ({
  contextBridge: { exposeInMainWorld: vi.fn() },
  ipcRenderer: { invoke: vi.fn(async () => undefined) },
}));

vi.mock("electron", () => ({ contextBridge, ipcRenderer }));

import "../src/main/preload";

describe("preload bridge", () => {
  it("exposes the dockb bridge with platform and openExternal", () => {
    expect(contextBridge.exposeInMainWorld).toHaveBeenCalledWith("dockb", expect.any(Object));
    const exposed = contextBridge.exposeInMainWorld.mock.calls[0][1] as {
      platform: string;
      openExternal: (url: string) => Promise<void>;
    };
    expect(typeof exposed.platform).toBe("string");
    expect(typeof exposed.openExternal).toBe("function");
  });

  it("openExternal forwards the URL over the open-external channel", async () => {
    const exposed = contextBridge.exposeInMainWorld.mock.calls[0][1] as {
      openExternal: (url: string) => Promise<void>;
    };
    await exposed.openExternal("https://example.com/login");
    expect(ipcRenderer.invoke).toHaveBeenCalledWith("open-external", "https://example.com/login");
  });
});