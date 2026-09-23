import { app, ipcMain, shell } from "electron";

const OPEN_EXTERNAL_CHANNEL = "open-external";
const QUIT_CHANNEL = "quit";

const ALLOWED_PROTOCOLS = new Set(["http:", "https:"]);

export function registerOpenExternal(): void {
  ipcMain.handle(OPEN_EXTERNAL_CHANNEL, async (_event, raw: unknown) => {
    if (typeof raw !== "string") {
      throw new Error("open-external: payload must be a string");
    }
    let parsed: URL;
    try {
      parsed = new URL(raw);
    } catch {
      throw new Error("open-external: payload is not a valid URL");
    }
    if (!ALLOWED_PROTOCOLS.has(parsed.protocol)) {
      throw new Error(`open-external: protocol "${parsed.protocol}" is not allowed`);
    }
    await shell.openExternal(raw);
  });
}

export function registerQuit(): void {
  ipcMain.on(QUIT_CHANNEL, () => {
    app.quit();
  });
}