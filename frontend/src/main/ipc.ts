import { app, dialog, ipcMain, shell } from "electron";
import * as fs from "fs/promises";
import * as path from "path";

const OPEN_EXTERNAL_CHANNEL = "open-external";
const QUIT_CHANNEL = "quit";
const CACHE_CHOOSE_DIRECTORY_CHANNEL = "cache-choose-directory";
const CACHE_SET_ROOT_CHANNEL = "cache-set-root";
const CACHE_READ_CHANNEL = "cache-read";
const CACHE_WRITE_CHANNEL = "cache-write";
const CACHE_DELETE_CHANNEL = "cache-delete";
const CACHE_RENAME_CHANNEL = "cache-rename";
const CACHE_MOVE_DIRECTORY_CHANNEL = "cache-move-directory";
const CACHE_LIST_CHANNEL = "cache-list";

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

let cacheRoot: string | null = null;

function hasControlCharacters(value: string): boolean {
  for (let index = 0; index < value.length; index += 1) {
    const code = value.charCodeAt(index);
    if (code < 32 || code === 127) {
      return true;
    }
  }
  return false;
}

export function resolveCachePath(relative: string): string {
  if (cacheRoot === null) {
    throw new Error("file cache root has not been set");
  }
  if (typeof relative !== "string" || relative.length === 0) {
    throw new Error("file cache path must be a non-empty string");
  }
  const parts = relative.split(/[\\/]/);
  if (
    parts.some(
      (part) =>
        part.length === 0 ||
        part === "." ||
        part === ".." ||
        /^[A-Za-z]:$/.test(part) ||
        hasControlCharacters(part),
    )
  ) {
    throw new Error(`file cache path escapes the cache directory: ${relative}`);
  }
  const resolved = path.resolve(cacheRoot, ...parts);
  if (resolved !== cacheRoot && !resolved.startsWith(cacheRoot + path.sep)) {
    throw new Error(`file cache path escapes the cache directory: ${relative}`);
  }
  return resolved;
}

function errorCode(error: unknown): string | undefined {
  return (error as NodeJS.ErrnoException).code;
}

function allowedCacheOrigins(): Set<string> {
  const configured = process.env.DOCKB_API_ORIGIN;
  const origin = (configured && configured.trim() ? configured : "http://localhost:8000").replace(
    /\/+$/,
    "",
  );
  const allowed = new Set<string>([new URL(origin).origin]);
  if (process.env.VITE_DEV_SERVER_URL) {
    allowed.add(new URL(process.env.VITE_DEV_SERVER_URL).origin);
  }
  return allowed;
}

function assertCacheSender(event: unknown): void {
  const sender = (event as { sender?: { getURL?: () => string } })?.sender;
  let origin: string;
  try {
    origin = new URL(sender?.getURL?.() ?? "").origin;
  } catch {
    throw new Error("cache IPC: sender has no valid origin");
  }
  if (!allowedCacheOrigins().has(origin)) {
    throw new Error(`cache IPC: disallowed sender origin ${origin}`);
  }
}

async function assertRealPathWithinRoot(target: string): Promise<void> {
  const root = cacheRoot as string;
  let realRoot: string;
  try {
    realRoot = await fs.realpath(root);
  } catch (error) {
    if (errorCode(error) === "ENOENT") {
      return;
    }
    throw error;
  }
  let anchor = target;
  for (;;) {
    try {
      const realAnchor = await fs.realpath(anchor);
      if (realAnchor !== realRoot && !realAnchor.startsWith(realRoot + path.sep)) {
        throw new Error(`file cache path escapes the cache directory: ${target}`);
      }
      return;
    } catch (error) {
      if (errorCode(error) !== "ENOENT") {
        throw error;
      }
      const parent = path.dirname(anchor);
      if (parent === anchor) {
        return;
      }
      anchor = parent;
    }
  }
}

async function pruneEmptyParents(directory: string): Promise<void> {
  const root = cacheRoot as string;
  let current = directory;
  while (current !== root && current.startsWith(root + path.sep)) {
    try {
      await fs.rmdir(current);
    } catch (error) {
      const code = errorCode(error);
      if (code === "ENOTEMPTY" || code === "EEXIST" || code === "ENOENT") {
        return;
      }
      throw error;
    }
    current = path.dirname(current);
  }
}

async function collectMarkdown(directory: string, prefix: string, found: string[]): Promise<void> {
  let entries: string[];
  try {
    entries = await fs.readdir(directory);
  } catch (error) {
    if (errorCode(error) === "ENOENT") {
      return;
    }
    throw error;
  }
  for (const entry of entries) {
    const absolute = path.join(directory, entry);
    const info = await fs.lstat(absolute);
    if (info.isSymbolicLink()) {
      continue;
    }
    const relative = prefix === "" ? entry : `${prefix}/${entry}`;
    if (info.isDirectory()) {
      await collectMarkdown(absolute, relative, found);
    } else if (entry.toLowerCase().endsWith(".md")) {
      found.push(relative);
    }
  }
}

export function registerFileCache(): void {
  ipcMain.handle(CACHE_CHOOSE_DIRECTORY_CHANNEL, async (event) => {
    assertCacheSender(event);
    const result = await dialog.showOpenDialog({
      title: "Choose the file cache directory",
      buttonLabel: "Choose",
      properties: ["openDirectory"],
    });
    if (result.canceled) {
      return null;
    }
    return result.filePaths[0] ?? null;
  });

  ipcMain.handle(CACHE_SET_ROOT_CHANNEL, async (event, directory: unknown) => {
    assertCacheSender(event);
    if (typeof directory !== "string" || directory.trim() === "") {
      throw new Error("cache-set-root: payload must be a directory path");
    }
    cacheRoot = path.resolve(directory);
  });

  ipcMain.handle(CACHE_READ_CHANNEL, async (event, relative: unknown) => {
    assertCacheSender(event);
    if (typeof relative !== "string") {
      throw new Error("cache-read: payload must be a path");
    }
    const target = resolveCachePath(relative);
    await assertRealPathWithinRoot(target);
    try {
      return await fs.readFile(target, "utf8");
    } catch (error) {
      if (errorCode(error) === "ENOENT") {
        return null;
      }
      throw error;
    }
  });

  ipcMain.handle(CACHE_WRITE_CHANNEL, async (event, relative: unknown, content: unknown) => {
    assertCacheSender(event);
    if (typeof relative !== "string" || typeof content !== "string") {
      throw new Error("cache-write: payload must be a path and markdown text");
    }
    const target = resolveCachePath(relative);
    await assertRealPathWithinRoot(target);
    await fs.mkdir(path.dirname(target), { recursive: true });
    await fs.writeFile(target, content, "utf8");
  });

  ipcMain.handle(CACHE_DELETE_CHANNEL, async (event, relative: unknown) => {
    assertCacheSender(event);
    if (typeof relative !== "string") {
      throw new Error("cache-delete: payload must be a path");
    }
    const target = resolveCachePath(relative);
    await assertRealPathWithinRoot(target);
    await fs.rm(target, { force: true });
    await pruneEmptyParents(path.dirname(target));
  });

  const move = async (event: unknown, from: unknown, to: unknown): Promise<void> => {
    assertCacheSender(event);
    if (typeof from !== "string" || typeof to !== "string") {
      throw new Error("cache move: payloads must be paths");
    }
    const source = resolveCachePath(from);
    const destination = resolveCachePath(to);
    await assertRealPathWithinRoot(source);
    await assertRealPathWithinRoot(destination);
    await fs.mkdir(path.dirname(destination), { recursive: true });
    await fs.rename(source, destination);
  };
  ipcMain.handle(CACHE_RENAME_CHANNEL, async (event, from: unknown, to: unknown) =>
    move(event, from, to),
  );
  ipcMain.handle(CACHE_MOVE_DIRECTORY_CHANNEL, async (event, from: unknown, to: unknown) =>
    move(event, from, to),
  );

  ipcMain.handle(CACHE_LIST_CHANNEL, async (event) => {
    assertCacheSender(event);
    if (cacheRoot === null) {
      throw new Error("file cache root has not been set");
    }
    const found: string[] = [];
    await collectMarkdown(cacheRoot, "", found);
    return found.sort();
  });
}