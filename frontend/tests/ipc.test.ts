import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { ipcMain, shell, dialog, fs } = vi.hoisted(() => ({
  ipcMain: {
    handle: vi.fn(),
    removeHandler: vi.fn(),
    on: vi.fn(),
  },
  shell: { openExternal: vi.fn(async () => undefined) },
  dialog: {
    showOpenDialog: vi.fn(async () => ({ canceled: false, filePaths: ["/home/me/cache"] })),
  },
  fs: {
    mkdir: vi.fn(async () => undefined),
    readFile: vi.fn(async () => "cached markdown"),
    writeFile: vi.fn(async () => undefined),
    rm: vi.fn(async () => undefined),
    rmdir: vi.fn(async () => undefined),
    rename: vi.fn(async () => undefined),
    readdir: vi.fn(async () => [] as string[]),
    lstat: vi.fn(async () => ({ isDirectory: () => false, isSymbolicLink: () => false })),
    realpath: vi.fn(async (entry: unknown) => String(entry)),
  },
}));

vi.mock("electron", () => ({ ipcMain, shell, dialog, app: { quit: vi.fn() } }));
vi.mock("fs/promises", () => ({ ...fs }));

import {
  registerFileCache,
  registerOpenExternal,
  registerQuit,
  resolveCachePath,
} from "../src/main/ipc";

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

function handlerFor(channel: string): (...args: unknown[]) => Promise<unknown> {
  const call = ipcMain.handle.mock.calls.find((entry) => entry[0] === channel);
  if (call === undefined) {
    throw new Error(`no handler registered for ${channel}`);
  }
  return call[1] as (...args: unknown[]) => Promise<unknown>;
}

const ipcEvent = { sender: { getURL: () => "http://localhost:8000/editor/" } };

describe("file cache root", () => {
  beforeEach(() => {
    registerFileCache();
  });

  it("refuses to resolve a path until a cache directory has been set", () => {
    expect(() => resolveCachePath("Doc/Act I/Opening.md")).toThrow(/root/i);
  });
});

describe("file cache IPC", () => {
  beforeEach(async () => {
    for (const mock of Object.values(fs)) {
      mock.mockReset();
    }
    fs.readFile.mockResolvedValue("cached markdown");
    fs.readdir.mockResolvedValue([]);
    fs.lstat.mockResolvedValue({ isDirectory: () => false, isSymbolicLink: () => false });
    fs.realpath.mockImplementation(async (entry: unknown) => String(entry));
    registerFileCache();
    await handlerFor("cache-set-root")(ipcEvent, "/home/me/cache");
  });

  it("registers every cache channel", () => {
    for (const channel of [
      "cache-choose-directory",
      "cache-set-root",
      "cache-read",
      "cache-write",
      "cache-delete",
      "cache-rename",
      "cache-move-directory",
      "cache-list",
    ]) {
      expect(ipcMain.handle).toHaveBeenCalledWith(channel, expect.any(Function));
    }
  });

  it("opens the native directory chooser and returns the picked directory", async () => {
    dialog.showOpenDialog.mockResolvedValueOnce({
      canceled: false,
      filePaths: ["/home/me/picked"],
    });
    await expect(handlerFor("cache-choose-directory")(ipcEvent)).resolves.toBe("/home/me/picked");
    expect(dialog.showOpenDialog).toHaveBeenCalledWith(
      expect.objectContaining({
        title: "Choose the file cache directory",
        properties: ["openDirectory"],
      }),
    );
  });

  it("returns null when the directory chooser is cancelled", async () => {
    dialog.showOpenDialog.mockResolvedValueOnce({ canceled: true, filePaths: [] });
    await expect(handlerFor("cache-choose-directory")(ipcEvent)).resolves.toBeNull();
  });

  it("resolves a relative path beneath the cache root", () => {
    expect(resolveCachePath("Linchpin/Act I/Opening 1.md")).toBe(
      "/home/me/cache/Linchpin/Act I/Opening 1.md",
    );
  });

  it.each([
    "../secret.md",
    "/etc/passwd",
    "Doc/../../secret.md",
    "C:\\secret.md",
    "Doc//Opening.md",
    "Doc/./Opening.md",
    "Doc/\u0001Opening.md",
    "",
  ])("rejects the unsafe relative path %s", (relative) => {
    expect(() => resolveCachePath(relative)).toThrow();
  });

  it("reads a cached chapter as UTF-8", async () => {
    await expect(handlerFor("cache-read")(ipcEvent, "Doc/Act I/Opening.md")).resolves.toBe(
      "cached markdown",
    );
    expect(fs.readFile).toHaveBeenCalledWith("/home/me/cache/Doc/Act I/Opening.md", "utf8");
  });

  it("returns null when the cached chapter does not exist", async () => {
    fs.readFile.mockRejectedValueOnce(Object.assign(new Error("missing"), { code: "ENOENT" }));
    await expect(handlerFor("cache-read")(ipcEvent, "Doc/Act I/Opening.md")).resolves.toBeNull();
  });

  it("writes a chapter, creating its parent directories", async () => {
    await handlerFor("cache-write")(ipcEvent, "Doc/Act I/Opening.md", "# Opening");
    expect(fs.mkdir).toHaveBeenCalledWith("/home/me/cache/Doc/Act I", { recursive: true });
    expect(fs.writeFile).toHaveBeenCalledWith(
      "/home/me/cache/Doc/Act I/Opening.md",
      "# Opening",
      "utf8",
    );
  });

  it("rejects non-string content and escaping paths on write", async () => {
    await expect(handlerFor("cache-write")(ipcEvent, "Doc/Opening.md", 42)).rejects.toThrow();
    await expect(handlerFor("cache-write")(ipcEvent, "../Opening.md", "x")).rejects.toThrow();
    expect(fs.writeFile).not.toHaveBeenCalled();
  });

  it("deletes a chapter and prunes empty parent directories but keeps the root", async () => {
    await handlerFor("cache-delete")(ipcEvent, "Doc/Act I/Opening.md");
    expect(fs.rm).toHaveBeenCalledWith("/home/me/cache/Doc/Act I/Opening.md", { force: true });
    expect(fs.rmdir).toHaveBeenCalledWith("/home/me/cache/Doc/Act I");
    expect(fs.rmdir).toHaveBeenCalledWith("/home/me/cache/Doc");
    expect(fs.rmdir).not.toHaveBeenCalledWith("/home/me/cache");
  });

  it("stops pruning when a parent directory is not empty", async () => {
    fs.rmdir.mockRejectedValueOnce(Object.assign(new Error("busy"), { code: "ENOTEMPTY" }));
    await expect(handlerFor("cache-delete")(ipcEvent, "Doc/Act I/Opening.md")).resolves.toBeUndefined();
    expect(fs.rmdir).toHaveBeenCalledTimes(1);
  });

  it("renames a chapter within its act directory", async () => {
    await handlerFor("cache-rename")(ipcEvent, "Doc/Act I/Old.md", "Doc/Act I/New.md");
    expect(fs.rename).toHaveBeenCalledWith(
      "/home/me/cache/Doc/Act I/Old.md",
      "/home/me/cache/Doc/Act I/New.md",
    );
  });

  it("creates the destination act directory when a chapter moves act", async () => {
    await handlerFor("cache-rename")(ipcEvent, "Doc/Act I/Old.md", "Doc/Act II/New.md");
    expect(fs.mkdir).toHaveBeenCalledWith("/home/me/cache/Doc/Act II", { recursive: true });
    expect(fs.rename).toHaveBeenCalledWith(
      "/home/me/cache/Doc/Act I/Old.md",
      "/home/me/cache/Doc/Act II/New.md",
    );
  });

  it("moves a whole document directory when the document is renamed", async () => {
    await handlerFor("cache-move-directory")(ipcEvent, "Old Doc", "New Doc");
    expect(fs.rename).toHaveBeenCalledWith("/home/me/cache/Old Doc", "/home/me/cache/New Doc");
  });

  it("lists cached markdown files as relative paths", async () => {
    const entries: Record<string, string[]> = {
      "/home/me/cache": ["Doc", "readme.txt"],
      "/home/me/cache/Doc": ["Act I", "Characters"],
      "/home/me/cache/Doc/Act I": ["Opening 1.md", "notes.txt"],
      "/home/me/cache/Doc/Characters": ["Jael.md"],
    };
    fs.readdir.mockImplementation(async (dir: unknown) => entries[String(dir)] ?? []);
    fs.lstat.mockImplementation(async (entry: unknown) => ({
      isDirectory: () => !/\.(md|txt)$/.test(String(entry)),
      isSymbolicLink: () => false,
    }));
    await expect(handlerFor("cache-list")(ipcEvent)).resolves.toEqual([
      "Doc/Act I/Opening 1.md",
      "Doc/Characters/Jael.md",
    ]);
  });

  it("treats a missing cache directory as an empty cache", async () => {
    fs.readdir.mockRejectedValueOnce(Object.assign(new Error("missing"), { code: "ENOENT" }));
    await expect(handlerFor("cache-list")(ipcEvent)).resolves.toEqual([]);
  });

  it("rejects cache calls from a page loaded at another origin", async () => {
    const foreign = { sender: { getURL: () => "https://evil.example/" } };
    await expect(handlerFor("cache-read")(foreign, "Doc/Opening.md")).rejects.toThrow(/origin/);
    await expect(handlerFor("cache-choose-directory")(foreign)).rejects.toThrow(/origin/);
    expect(fs.readFile).not.toHaveBeenCalled();
    expect(dialog.showOpenDialog).not.toHaveBeenCalled();
  });

  it("accepts the Vite dev server origin when configured", async () => {
    process.env.VITE_DEV_SERVER_URL = "http://localhost:3000";
    try {
      const dev = { sender: { getURL: () => "http://localhost:3000/" } };
      await expect(handlerFor("cache-read")(dev, "Doc/Opening.md")).resolves.toBe(
        "cached markdown",
      );
    } finally {
      delete process.env.VITE_DEV_SERVER_URL;
    }
  });

  it("refuses to read through a symlink that escapes the cache", async () => {
    fs.realpath.mockImplementation(async (entry: unknown) =>
      String(entry) === "/home/me/cache/Doc/Opening.md" ? "/etc/passwd" : String(entry),
    );
    await expect(handlerFor("cache-read")(ipcEvent, "Doc/Opening.md")).rejects.toThrow(/escapes/);
    expect(fs.readFile).not.toHaveBeenCalled();
  });

  it("does not follow symlinked directories when listing the cache", async () => {
    const entries: Record<string, string[]> = {
      "/home/me/cache": ["Doc", "linked"],
      "/home/me/cache/Doc": ["Opening.md"],
    };
    fs.readdir.mockImplementation(async (dir: unknown) => entries[String(dir)] ?? []);
    fs.lstat.mockImplementation(async (entry: unknown) => ({
      isDirectory: () => String(entry) === "/home/me/cache/Doc",
      isSymbolicLink: () => String(entry) === "/home/me/cache/linked",
    }));
    await expect(handlerFor("cache-list")(ipcEvent)).resolves.toEqual(["Doc/Opening.md"]);
  });
});

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