import { app, BrowserWindow, Menu } from "electron";
import * as path from "path";
import { registerOpenExternal, registerQuit } from "./ipc";

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
    void win.loadFile(path.join(__dirname, "../dist/index.html"));
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