import { afterEach, describe, expect, it, vi } from "vitest";
import type { DocumentContentResponse } from "../src/renderer/api/types";
import { EditPanel, type EditPanelApi } from "../src/renderer/layout/editPanel";
import { FileCache, type FileCacheBridge } from "../src/renderer/state/fileCache";
import type { WysiwygView } from "../src/renderer/layout/wysiwyg";

const PATH = "Novel/Act I/Opening.md";

function doc(content: string): DocumentContentResponse {
  return { content, summary: null, warnings: [] };
}

function fakeApi(overrides: Partial<EditPanelApi> = {}): EditPanelApi {
  return {
    getChapterDocument: vi.fn(async () => doc("---\ntitle: Opening\nact: I\n---\n\nServer body.")),
    saveChapterDocument: vi.fn(async (_id: string, content: string) => doc(content)),
    ...overrides,
  };
}

function memoryStorage(): Pick<Storage, "getItem" | "setItem"> {
  const values = new Map<string, string>();
  return {
    getItem: (key) => values.get(key) ?? null,
    setItem: (key, value) => {
      values.set(key, value);
    },
  };
}

function cacheBridge(cached: string | null = null): FileCacheBridge {
  return {
    isElectron: true,
    chooseCacheDirectory: vi.fn(async () => "/cache"),
    setCacheRoot: vi.fn(async () => undefined),
    cacheRead: vi.fn(async () => cached),
    cacheWrite: vi.fn(async () => undefined),
    cacheDelete: vi.fn(async () => undefined),
    cacheRename: vi.fn(async () => undefined),
    cacheMoveDirectory: vi.fn(async () => undefined),
    cacheList: vi.fn(async () => []),
  };
}

function context(): () => { documentTitle: string; chapter: { title: string; act: string } } {
  return () => ({ documentTitle: "Novel", chapter: { title: "Opening", act: "I" } });
}

function panelWith(
  api: EditPanelApi,
  cache: FileCache,
): EditPanel {
  const panel = new EditPanel({ api, fileCache: cache, cacheContext: context() });
  document.body.append(panel.element);
  return panel;
}

function typeInPanel(panel: EditPanel, text: string): void {
  const wysiwyg = (panel as unknown as { wysiwyg: WysiwygView }).wysiwyg;
  const view = wysiwyg.view;
  view.dispatch(view.state.tr.insertText(text, view.state.doc.content.size));
}

function clickModal(label: string): void {
  const button = Array.from(document.querySelectorAll<HTMLElement>("[data-testid='modal-button']")).find(
    (candidate) => candidate.textContent === label,
  )!;
  button.dispatchEvent(new MouseEvent("click", { bubbles: true }));
}

function tick(): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, 0));
}

afterEach(() => {
  document.body.replaceChildren();
  vi.useRealTimers();
  vi.restoreAllMocks();
});

describe("EditPanel file cache", () => {
  it("leaves the cache untouched when no document context is available", async () => {
    const bridge = cacheBridge();
    const cache = new FileCache({ bridge, storage: memoryStorage() });
    const panel = new EditPanel({ api: fakeApi(), fileCache: cache });
    document.body.append(panel.element);

    await panel.load("c1");

    expect(bridge.cacheWrite).not.toHaveBeenCalled();
    expect(panel.isCacheDirty()).toBe(false);
  });

  it("writes the backend copy into the cache when the chapter loads", async () => {
    const bridge = cacheBridge();
    const cache = new FileCache({ bridge, storage: memoryStorage() });
    const panel = panelWith(fakeApi(), cache);
    const content = "---\ntitle: Opening\nact: I\n---\n\nServer body.";

    await panel.load("c1");

    expect(bridge.cacheWrite).toHaveBeenCalledWith(PATH, content);
    expect(panel.isCacheDirty()).toBe(false);
  });

  it("debounces cache writes without clearing backend-dirty state", async () => {
    vi.useFakeTimers();
    const bridge = cacheBridge();
    const cache = new FileCache({ bridge, storage: memoryStorage() });
    const api = fakeApi();
    const panel = panelWith(api, cache);
    await panel.load("c1");
    expect(bridge.cacheWrite).toHaveBeenCalledTimes(1);

    typeInPanel(panel, " more");
    expect(panel.isDirty()).toBe(true);
    expect(panel.isCacheDirty()).toBe(true);
    expect(bridge.cacheWrite).toHaveBeenCalledTimes(1);

    await vi.advanceTimersByTimeAsync(5000);
    expect(bridge.cacheWrite).toHaveBeenCalledTimes(2);
    expect(bridge.cacheWrite).toHaveBeenLastCalledWith(PATH, panel.content());
    expect(panel.isCacheDirty()).toBe(false);
    expect(panel.isDirty()).toBe(true);
    expect(api.saveChapterDocument).not.toHaveBeenCalled();
  });

  it("flush writes the buffered cache text immediately", async () => {
    vi.useFakeTimers();
    const bridge = cacheBridge();
    const cache = new FileCache({ bridge, storage: memoryStorage() });
    const panel = panelWith(fakeApi(), cache);
    await panel.load("c1");
    typeInPanel(panel, " buffered");
    await panel.flushCache();
    expect(bridge.cacheWrite).toHaveBeenCalledTimes(2);
    await vi.advanceTimersByTimeAsync(5000);
    expect(bridge.cacheWrite).toHaveBeenCalledTimes(2);
  });

  it("offers save-first when the cached copy has changes, then uploads it", async () => {
    const cached = "---\ntitle: Opening\nact: I\n---\n\nCached edit.";
    const bridge = cacheBridge(cached);
    const cache = new FileCache({ bridge, storage: memoryStorage() });
    cache.recordCacheText(PATH, cached);
    const saveChapterDocument = vi.fn(async (_id: string, content: string) => doc(`${content}\n\nSaved.`));
    const api = fakeApi({ saveChapterDocument });

    const pending = panelWith(api, cache).load("c1");
    await tick();
    expect(document.querySelector("[data-testid='modal-title']")?.textContent).toBe(
      "File cache has changes",
    );
    clickModal("Save to backend");
    await pending;

    expect(saveChapterDocument).toHaveBeenCalledWith("c1", cached);
    expect(bridge.cacheWrite).toHaveBeenCalledWith(PATH, `${cached}\n\nSaved.`);
  });

  it("offers overwrite and discards the cached edits", async () => {
    const cached = "---\ntitle: Opening\nact: I\n---\n\nCached edit.";
    const bridge = cacheBridge(cached);
    const cache = new FileCache({ bridge, storage: memoryStorage() });
    cache.recordCacheText(PATH, cached);
    const saveChapterDocument = vi.fn(async (_id: string, content: string) => doc(content));
    const api = fakeApi({ saveChapterDocument });

    const pending = panelWith(api, cache).load("c1");
    await tick();
    clickModal("Overwrite cache");
    await pending;

    expect(saveChapterDocument).not.toHaveBeenCalled();
    expect(bridge.cacheWrite).toHaveBeenCalledWith(
      PATH,
      "---\ntitle: Opening\nact: I\n---\n\nServer body.",
    );
  });

  it("rewrites the cache after a backend save", async () => {
    const bridge = cacheBridge();
    const cache = new FileCache({ bridge, storage: memoryStorage() });
    const api = fakeApi({
      saveChapterDocument: vi.fn(async (_id, content) => doc(`${content}\n\nSaved.`)),
    });
    const panel = panelWith(api, cache);
    await panel.load("c1");
    typeInPanel(panel, " edit");

    await panel.save();

    expect(bridge.cacheWrite).toHaveBeenLastCalledWith(PATH, panel.content());
    expect(panel.isDirty()).toBe(false);
    expect(panel.isCacheDirty()).toBe(false);
  });
});
