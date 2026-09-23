import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { ipcMain, shell } = vi.hoisted(() => ({
  ipcMain: {
    handle: vi.fn(),
    removeHandler: vi.fn(),
    on: vi.fn(),
  },
  shell: { openExternal: vi.fn(async () => undefined) },
}));

vi.mock("electron", () => ({ ipcMain, shell, app: { quit: vi.fn() } }));

import { registerOpenExternal, registerQuit } from "../src/main/ipc";

beforeEach(() => {
  vi.clearAllMocks();
  registerOpenExternal();
  registerQuit();
});

afterEach(() => {
  ipcMain.removeHandler();
});

function handler(): (event: unknown, url: unknown) => Promise<void> {
  return ipcMain.handle.mock.calls[0][1] as (event: unknown, url: unknown) => Promise<void>;
}

describe("open-external handler", () => {
  it("registers the open-external channel", () => {
    expect(ipcMain.handle).toHaveBeenCalledWith("open-external", expect.any(Function));
  });

  it("opens an https URL via the system browser", async () => {
    const url = "https://accounts.google.com/oauth?x=1";
    const fn = handler();
    await fn({ sender: {} }, url);
    expect(shell.openExternal).toHaveBeenCalledWith(url);
  });

  it("opens an http URL", async () => {
    const fn = handler();
    await fn({ sender: {} }, "http://localhost:1234/callback?code=x");
    expect(shell.openExternal).toHaveBeenCalledWith("http://localhost:1234/callback?code=x");
  });

  it("rejects non-http(s) URLs rather than opening them", async () => {
    const fn = handler();
    await expect(fn({ sender: {} }, "file:///etc/passwd")).rejects.toThrow();
    await expect(fn({ sender: {} }, "smb://host/share")).rejects.toThrow();
    await expect(fn({ sender: {} }, "javascript:alert(1)")).rejects.toThrow();
    expect(shell.openExternal).not.toHaveBeenCalled();
  });

  it("rejects non-string payloads", async () => {
    const fn = handler();
    await expect(fn({ sender: {} }, 42)).rejects.toThrow();
    expect(shell.openExternal).not.toHaveBeenCalled();
  });
});

describe("quit handler", () => {
  it("registers the quit channel", () => {
    expect(ipcMain.on).toHaveBeenCalledWith("quit", expect.any(Function));
  });
});