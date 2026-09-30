import { app, BrowserWindow, Menu } from "electron";
import * as path from "path";
import { registerOpenExternal, registerQuit } from "./ipc";

/** Where the backend serves the built editor, relative to its origin. */
const EDITOR_PATH = "/editor/";

const DEFAULT_API_ORIGIN = "http://localhost:8000";

/** The URL the window loads: the backend's editor shell.
 *
 * Loading a URL rather than a local file is what makes the renderer
 * same-origin with the API, so the SameSite=lax session cookie is sent
 * and no CORS grant is needed.
 */
export function editorUrl(env: NodeJS.ProcessEnv = process.env): string {
  const configured = env.DOCKB_API_ORIGIN;
  const origin = (configured && configured.trim() ? configured : DEFAULT_API_ORIGIN).replace(
    /\/+$/,
    "",
  );
  return `${origin}${EDITOR_PATH}`;
}

export function createWindow(): BrowserWindow {
  const win = new BrowserWindow({
    width: 1200,
    height: 800,
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });

  if (process.env.VITE_DEV_SERVER_URL) {
    void win.loadURL(process.env.VITE_DEV_SERVER_URL);
  } else {
    void win.loadURL(editorUrl());
  }
  return win;
}

export function onAppReady(): void {
  Menu.setApplicationMenu(null);
  registerOpenExternal();
  registerQuit();
  createWindow();
}

app.whenReady().then(onAppReady);

app.on("activate", () => {
  if (BrowserWindow.getAllWindows().length === 0) {
    createWindow();
  }
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") {
    app.quit();
  }
});