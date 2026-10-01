import { describe, expect, it, vi } from "vitest";

const { contextBridge, ipcRenderer, webUtils } = vi.hoisted(() => ({
  contextBridge: { exposeInMainWorld: vi.fn() },
  ipcRenderer: { invoke: vi.fn(async () => undefined), send: vi.fn() },
  webUtils: { getPathForFile: vi.fn(() => "/docs/Linchpin/Act I/Opening.md") },
}));

vi.mock("electron", () => ({ contextBridge, ipcRenderer, webUtils }));

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
describe("preload path bridge", () => {
  it("exposes getPathForFile on the dockb bridge", () => {
    const exposed = contextBridge.exposeInMainWorld.mock.calls[0][1] as {
      getPathForFile: (file: File) => string;
    };
    expect(typeof exposed.getPathForFile).toBe("function");
  });

  it("getPathForFile asks webUtils for the file's absolute path", () => {
    const exposed = contextBridge.exposeInMainWorld.mock.calls[0][1] as {
      getPathForFile: (file: File) => string;
    };
    const file = new File(["x"], "Opening.md");
    expect(exposed.getPathForFile(file)).toBe("/docs/Linchpin/Act I/Opening.md");
    expect(webUtils.getPathForFile).toHaveBeenCalledWith(file);
  });

  it("getPathForFile passes through the empty path of a file not on disk", () => {
    const exposed = contextBridge.exposeInMainWorld.mock.calls[0][1] as {
      getPathForFile: (file: File) => string;
    };
    webUtils.getPathForFile.mockReturnValueOnce("");
    expect(exposed.getPathForFile(new File(["x"], "made-up.md"))).toBe("");
  });
});
