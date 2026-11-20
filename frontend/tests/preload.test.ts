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

describe("preload file cache bridge", () => {
  type CacheBridge = {
    isElectron: boolean;
    chooseCacheDirectory(): Promise<string | null>;
    setCacheRoot(directory: string): Promise<void>;
    cacheRead(relativePath: string): Promise<string | null>;
    cacheWrite(relativePath: string, content: string): Promise<void>;
    cacheDelete(relativePath: string): Promise<void>;
    cacheRename(from: string, to: string): Promise<void>;
    cacheMoveDirectory(from: string, to: string): Promise<void>;
    cacheList(): Promise<string[]>;
  };

  function exposed(): CacheBridge {
    return contextBridge.exposeInMainWorld.mock.calls[0][1] as CacheBridge;
  }

  it("announces that it is running inside Electron", () => {
    expect(exposed().isElectron).toBe(true);
  });

  it("forwards the native directory chooser", async () => {
    await exposed().chooseCacheDirectory();
    expect(ipcRenderer.invoke).toHaveBeenCalledWith("cache-choose-directory");
  });

  it("forwards the cache root and each filesystem operation", async () => {
    const bridge = exposed();
    await bridge.setCacheRoot("/home/me/cache");
    await bridge.cacheRead("Doc/Opening.md");
    await bridge.cacheWrite("Doc/Opening.md", "# Opening");
    await bridge.cacheDelete("Doc/Opening.md");
    await bridge.cacheRename("Doc/Old.md", "Doc/New.md");
    await bridge.cacheMoveDirectory("Old Doc", "New Doc");
    await bridge.cacheList();
    expect(ipcRenderer.invoke).toHaveBeenCalledWith("cache-set-root", "/home/me/cache");
    expect(ipcRenderer.invoke).toHaveBeenCalledWith("cache-read", "Doc/Opening.md");
    expect(ipcRenderer.invoke).toHaveBeenCalledWith("cache-write", "Doc/Opening.md", "# Opening");
    expect(ipcRenderer.invoke).toHaveBeenCalledWith("cache-delete", "Doc/Opening.md");
    expect(ipcRenderer.invoke).toHaveBeenCalledWith("cache-rename", "Doc/Old.md", "Doc/New.md");
    expect(ipcRenderer.invoke).toHaveBeenCalledWith("cache-move-directory", "Old Doc", "New Doc");
    expect(ipcRenderer.invoke).toHaveBeenCalledWith("cache-list");
  });
});
