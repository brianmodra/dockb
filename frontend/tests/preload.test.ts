import { describe, expect, it, vi } from "vitest";

const { contextBridge, ipcRenderer } = vi.hoisted(() => ({
  contextBridge: { exposeInMainWorld: vi.fn() },
  ipcRenderer: { invoke: vi.fn(async () => undefined), send: vi.fn() },
}));

vi.mock("electron", () => ({ contextBridge, ipcRenderer }));

import "../src/main/preload";

describe("preload bridge", () => {
  it("exposes the dockb bridge with platform, openExternal, and quit", () => {
    expect(contextBridge.exposeInMainWorld).toHaveBeenCalledWith("dockb", expect.any(Object));
    const exposed = contextBridge.exposeInMainWorld.mock.calls[0][1] as {
      platform: string;
      openExternal: (url: string) => Promise<void>;
      quit: () => void;
    };
    expect(typeof exposed.platform).toBe("string");
    expect(typeof exposed.openExternal).toBe("function");
    expect(typeof exposed.quit).toBe("function");
  });

  it("openExternal forwards the URL over the open-external channel", async () => {
    const exposed = contextBridge.exposeInMainWorld.mock.calls[0][1] as {
      openExternal: (url: string) => Promise<void>;
    };
    await exposed.openExternal("https://example.com/login");
    expect(ipcRenderer.invoke).toHaveBeenCalledWith("open-external", "https://example.com/login");
  });

  it("quit sends over the quit channel", () => {
    const exposed = contextBridge.exposeInMainWorld.mock.calls[0][1] as {
      quit: () => void;
    };
    exposed.quit();
    expect(ipcRenderer.send).toHaveBeenCalledWith("quit");
  });
});