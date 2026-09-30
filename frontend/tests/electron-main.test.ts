import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { BrowserWindow, app, ipcMain, Menu } = vi.hoisted(() => {
  const instances: Array<Record<string, unknown>> = [];
  const BrowserWindow = vi.fn(() => {
    const win: Record<string, unknown> = {
      loadURL: vi.fn(() => Promise.resolve()),
      loadFile: vi.fn(() => Promise.resolve()),
    };
    instances.push(win);
    return win;
  });
  BrowserWindow.getAllWindows = vi.fn(() => instances);
  return {
    BrowserWindow,
    app: {
      whenReady: vi.fn(() => Promise.resolve()),
      on: vi.fn(),
      quit: vi.fn(),
    },
    Menu: { setApplicationMenu: vi.fn() },
    ipcMain: { handle: vi.fn(), removeHandler: vi.fn(), on: vi.fn() },
    instances,
  };
});

vi.mock("electron", () => ({ app, BrowserWindow, ipcMain, Menu }));

import { createWindow, editorUrl, onAppReady } from "../src/main/main";
import type { BrowserWindow as BrowserWindowType } from "electron";

beforeEach(() => {
  vi.clearAllMocks();
  delete process.env.VITE_DEV_SERVER_URL;
  delete process.env.DOCKB_API_ORIGIN;
});

afterEach(() => {
  delete process.env.VITE_DEV_SERVER_URL;
  delete process.env.DOCKB_API_ORIGIN;
});

describe("electron main", () => {
  it("creates a full-size window with the renderer isolated", () => {
    const win = createWindow();
    expect(win).toBeDefined();
    const options = BrowserWindow.mock.calls[0][0] as {
      width: number;
      height: number;
      webPreferences: { preload: string; contextIsolation: boolean; nodeIntegration: boolean };
    };
    expect(options.width).toBeGreaterThanOrEqual(800);
    expect(options.height).toBeGreaterThanOrEqual(600);
    expect(options.webPreferences.preload).toContain("preload");
    expect(options.webPreferences.contextIsolation).toBe(true);
    expect(options.webPreferences.nodeIntegration).toBe(false);
  });

  it("loads the vite dev server when it is running", async () => {
    process.env.VITE_DEV_SERVER_URL = "http://localhost:3000";
    const win = createWindow() as BrowserWindowType;
    await vi.waitFor(() => expect((win.loadURL as ReturnType<typeof vi.fn>).mock.calls.length).toBeGreaterThan(0));
    expect((win.loadURL as ReturnType<typeof vi.fn>).mock.calls[0][0]).toBe(
      "http://localhost:3000",
    );
  });

  it("loads the backend's editor shell rather than a local file", async () => {
    const win = createWindow() as BrowserWindowType;
    await vi.waitFor(() =>
      expect((win.loadURL as ReturnType<typeof vi.fn>).mock.calls.length).toBeGreaterThan(0),
    );
    expect((win.loadURL as ReturnType<typeof vi.fn>).mock.calls[0][0]).toBe(
      "http://localhost:8000/editor/",
    );
  });

  it("loads the shell from a configured API origin", async () => {
    process.env.DOCKB_API_ORIGIN = "http://dockb.test:9000";
    const win = createWindow() as BrowserWindowType;
    await vi.waitFor(() =>
      expect((win.loadURL as ReturnType<typeof vi.fn>).mock.calls.length).toBeGreaterThan(0),
    );
    expect((win.loadURL as ReturnType<typeof vi.fn>).mock.calls[0][0]).toBe(
      "http://dockb.test:9000/editor/",
    );
  });

  it("removes the default application menu so the in-window menubar stands alone", () => {
    onAppReady();
    expect(Menu.setApplicationMenu).toHaveBeenCalledWith(null);
  });
});

describe("editorUrl", () => {
  it("defaults to the loopback backend", () => {
    expect(editorUrl({})).toBe("http://localhost:8000/editor/");
  });

  it("honours a configured origin", () => {
    expect(editorUrl({ DOCKB_API_ORIGIN: "http://dockb.test:9000" })).toBe(
      "http://dockb.test:9000/editor/",
    );
  });

  it("does not double the slash when the origin has a trailing one", () => {
    expect(editorUrl({ DOCKB_API_ORIGIN: "http://dockb.test:9000/" })).toBe(
      "http://dockb.test:9000/editor/",
    );
  });

  it("ignores an empty origin rather than producing a relative url", () => {
    expect(editorUrl({ DOCKB_API_ORIGIN: "" })).toBe("http://localhost:8000/editor/");
  });
});