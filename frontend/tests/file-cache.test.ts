import { afterEach, describe, expect, it, vi } from "vitest";
import {
  DIRECTORY_KEY,
  FileCache,
  actDirectory,
  sanitizeSegment,
  type FileCacheBridge,
} from "../src/renderer/state/fileCache";

function memoryStorage(initial: Record<string, string> = {}): Pick<Storage, "getItem" | "setItem"> {
  const values = new Map(Object.entries(initial));
  return {
    getItem: vi.fn((key) => values.get(key) ?? null),
    setItem: vi.fn((key, value) => {
      values.set(key, value);
    }),
  };
}

function electronBridge(overrides: Partial<FileCacheBridge> = {}): FileCacheBridge {
  return {
    isElectron: true,
    chooseCacheDirectory: vi.fn(async () => "/tmp/cache"),
    setCacheRoot: vi.fn(async () => undefined),
    cacheRead: vi.fn(async () => null),
    cacheWrite: vi.fn(async () => undefined),
    cacheDelete: vi.fn(async () => undefined),
    cacheRename: vi.fn(async () => undefined),
    cacheMoveDirectory: vi.fn(async () => undefined),
    cacheList: vi.fn(async () => []),
    ...overrides,
  };
}

afterEach(() => {
  vi.useRealTimers();
});

describe("file cache path mapping", () => {
  it("sanitizes illegal filename characters and empty titles", () => {
    expect(sanitizeSegment('A/B: C? "D"')).toBe("A_B_ C_ _D_");
    expect(sanitizeSegment("  ")).toBe("_");
    expect(sanitizeSegment("trailing. ")).toBe("trailing");
  });

  it("maps chapter metadata onto backend-style act directories", () => {
    expect(actDirectory({ title: "Opening", act: "I", category: "Chapter" })).toBe("Act I");
    expect(actDirectory({ title: "Opening", act: "Act II", category: "Chapter" })).toBe("Act II");
    expect(actDirectory({ title: "Opening", act: "", category: "Chapter" })).toBe("Act None");
    expect(actDirectory({ title: "Jane", act: "I", category: "Character" })).toBe("Characters");
  });

  it("builds the cache path from document title, act and chapter title", () => {
    const cache = new FileCache({ bridge: electronBridge() });
    expect(cache.chapterPath("My/Novel", { title: "First: Chapter", act: "III" })).toBe(
      "My_Novel/Act III/First_ Chapter.md",
    );
    expect(cache.chapterPath("Doc", { title: "One", act: "I/II" })).toBe("Doc/Act I_II/One.md");
  });
});

describe("FileCache", () => {
  it("is disabled without the Electron bridge and performs no directory work", async () => {
    const bridge = { ...electronBridge(), isElectron: false } as FileCacheBridge;
    const cache = new FileCache({ bridge, storage: memoryStorage() });
    expect(cache.enabled).toBe(false);
    expect(cache.isConfigured()).toBe(false);
    expect(await cache.chooseDirectory()).toBeNull();
    expect(bridge.chooseCacheDirectory).not.toHaveBeenCalled();
    expect(await cache.readChapter("x.md")).toBeNull();
  });

  it("restores a saved directory and marks the cache configured", async () => {
    const bridge = electronBridge();
    const storage = memoryStorage({ [DIRECTORY_KEY]: "/saved/cache" });
    const cache = new FileCache({ bridge, storage });
    await cache.restore();
    expect(cache.directory()).toBe("/saved/cache");
    expect(cache.isConfigured()).toBe(true);
    expect(bridge.setCacheRoot).toHaveBeenCalledWith("/saved/cache");
  });

  it("uses the stable localStorage key for the chosen directory", () => {
    expect(DIRECTORY_KEY).toBe("dockb.fileCacheDirectory");
    const storage = memoryStorage();
    const cache = new FileCache({ bridge: electronBridge(), storage });
    expect(cache.directory()).toBeNull();
  });

  it("chooses, persists and configures a directory through the bridge", async () => {
    const bridge = electronBridge({ chooseCacheDirectory: vi.fn(async () => "/chosen/cache") });
    const storage = memoryStorage();
    const cache = new FileCache({ bridge, storage });
    expect(await cache.chooseDirectory()).toBe("/chosen/cache");
    expect(storage.setItem).toHaveBeenCalledWith(DIRECTORY_KEY, "/chosen/cache");
    expect(bridge.setCacheRoot).toHaveBeenCalledWith("/chosen/cache");
    expect(cache.isConfigured()).toBe(true);
  });

  it("keeps the old directory when the chooser is cancelled", async () => {
    const bridge = electronBridge({ chooseCacheDirectory: vi.fn(async () => null) });
    const storage = memoryStorage({ [DIRECTORY_KEY]: "/old/cache" });
    const cache = new FileCache({ bridge, storage });
    await cache.restore();
    expect(await cache.chooseDirectory()).toBeNull();
    expect(cache.directory()).toBe("/old/cache");
    expect(bridge.setCacheRoot).toHaveBeenCalledTimes(1);
  });

  it("delegates cache file operations to the bridge", async () => {
    const bridge = electronBridge();
    const cache = new FileCache({ bridge });
    await cache.writeChapter("Doc/Act I/One.md", "# One");
    await cache.readChapter("Doc/Act I/One.md");
    await cache.renameChapter("Doc/Act I/One.md", "Doc/Act I/Two.md");
    await cache.deleteChapter("Doc/Act I/Two.md");
    await cache.renameDocument("Old", "New");
    await cache.list();
    expect(bridge.cacheWrite).toHaveBeenCalledWith("Doc/Act I/One.md", "# One");
    expect(bridge.cacheRead).toHaveBeenCalledWith("Doc/Act I/One.md");
    expect(bridge.cacheRename).toHaveBeenCalledWith("Doc/Act I/One.md", "Doc/Act I/Two.md");
    expect(bridge.cacheDelete).toHaveBeenCalledWith("Doc/Act I/Two.md");
    expect(bridge.cacheMoveDirectory).toHaveBeenCalledWith("Old", "New");
    expect(bridge.cacheList).toHaveBeenCalled();
  });

  it("debounces scheduled writes and flushes immediately on demand", async () => {
    vi.useFakeTimers();
    const bridge = electronBridge();
    const cache = new FileCache({ bridge, debounceMs: 5000 });
    cache.scheduleWrite("Doc/One.md", "first");
    cache.scheduleWrite("Doc/One.md", "second");
    expect(bridge.cacheWrite).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(4999);
    expect(bridge.cacheWrite).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(1);
    expect(bridge.cacheWrite).toHaveBeenCalledTimes(1);
    expect(bridge.cacheWrite).toHaveBeenCalledWith("Doc/One.md", "second");
  });

  it("flush cancels a pending debounce and writes the buffered content", async () => {
    vi.useFakeTimers();
    const bridge = electronBridge();
    const cache = new FileCache({ bridge, debounceMs: 5000 });
    cache.scheduleWrite("Doc/Two.md", "buffered");
    await cache.flush();
    expect(bridge.cacheWrite).toHaveBeenCalledWith("Doc/Two.md", "buffered");
    await vi.advanceTimersByTimeAsync(5000);
    expect(bridge.cacheWrite).toHaveBeenCalledTimes(1);
  });
});
