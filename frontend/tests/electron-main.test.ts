import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { BrowserWindow, app } = vi.hoisted(() => {
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
    instances,
  };
});

vi.mock("electron", () => ({ app, BrowserWindow }));

import { createWindow } from "../src/main/main";
import type { BrowserWindow as BrowserWindowType } from "electron";

beforeEach(() => {
  vi.clearAllMocks();
  delete process.env.VITE_DEV_SERVER_URL;
});

afterEach(() => {
  delete process.env.VITE_DEV_SERVER_URL;
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

  it("loads the built files otherwise", async () => {
    const win = createWindow() as BrowserWindowType;
    await vi.waitFor(() => expect((win.loadFile as ReturnType<typeof vi.fn>).mock.calls.length).toBeGreaterThan(0));
    expect((win.loadFile as ReturnType<typeof vi.fn>).mock.calls[0][0]).toContain("index.html");
  });
});