import type { DockbBridge } from "../api/bridge";

export const DIRECTORY_KEY = "dockb.fileCacheDirectory";

const ILLEGAL_SEGMENT_CHARS = '<>:"/\\|?*';

export type FileCacheBridge = Pick<
  DockbBridge,
  | "isElectron"
  | "chooseCacheDirectory"
  | "setCacheRoot"
  | "cacheRead"
  | "cacheWrite"
  | "cacheDelete"
  | "cacheRename"
  | "cacheMoveDirectory"
  | "cacheList"
>;

export interface CacheChapter {
  title: string;
  act?: string;
  category?: "Chapter" | "Character";
}

export interface ChapterCacheMove {
  id: string;
  from: CacheChapter;
  to: CacheChapter;
}

export interface FileCacheOptions {
  bridge?: FileCacheBridge;
  storage?: Pick<Storage, "getItem" | "setItem">;
  debounceMs?: number;
}

export function sanitizeSegment(value: string): string {
  let sanitized = "";
  for (const character of value) {
    const code = character.charCodeAt(0);
    if (code < 32 || code === 127 || ILLEGAL_SEGMENT_CHARS.includes(character)) {
      sanitized += "_";
    } else {
      sanitized += character;
    }
  }
  sanitized = sanitized.replace(/[. ]+$/g, "");
  return sanitized === "" ? "_" : sanitized;
}

export function actDirectory(chapter: CacheChapter): string {
  if (chapter.category === "Character") {
    return "Characters";
  }
  const act = (chapter.act ?? "").trim();
  if (act === "") {
    return "Act None";
  }
  return act.startsWith("Act ") ? act : `Act ${act}`;
}

export class FileCache {
  private readonly bridge: FileCacheBridge | undefined;
  private readonly storage: Pick<Storage, "getItem" | "setItem">;
  private readonly debounceMs: number;
  private readonly pendingWrites = new Map<string, string>();
  private readonly cacheTexts = new Map<string, string>();
  private timer: ReturnType<typeof setTimeout> | null = null;
  private directoryValue: string | null = null;

  constructor(options: FileCacheOptions = {}) {
    this.bridge = options.bridge?.isElectron === true ? options.bridge : undefined;
    const storage = options.storage ?? (typeof window === "undefined" ? undefined : window.localStorage);
    this.storage = storage ?? { getItem: () => null, setItem: () => {} };
    this.debounceMs = options.debounceMs ?? 5000;
    this.directoryValue = this.storage.getItem(DIRECTORY_KEY);
  }

  get enabled(): boolean {
    return this.bridge !== undefined;
  }

  directory(): string | null {
    return this.directoryValue;
  }

  isConfigured(): boolean {
    return this.enabled && this.directoryValue !== null;
  }

  async restore(): Promise<void> {
    if (this.bridge === undefined || this.directoryValue === null) {
      return;
    }
    await this.bridge.setCacheRoot(this.directoryValue);
    this.cacheTexts.clear();
  }

  async chooseDirectory(): Promise<string | null> {
    if (this.bridge === undefined) {
      return null;
    }
    const chosen = await this.bridge.chooseCacheDirectory();
    if (chosen === null) {
      return null;
    }
    await this.bridge.setCacheRoot(chosen);
    this.cacheTexts.clear();
    this.directoryValue = chosen;
    this.storage.setItem(DIRECTORY_KEY, chosen);
    return chosen;
  }

  documentDirectory(title: string): string {
    return sanitizeSegment(title);
  }

  chapterPath(documentTitle: string, chapter: CacheChapter): string {
    return `${this.documentDirectory(documentTitle)}/${sanitizeSegment(actDirectory(chapter))}/${sanitizeSegment(chapter.title)}.md`;
  }

  cacheText(path: string): string | null {
    return this.cacheTexts.get(path) ?? null;
  }

  recordCacheText(path: string, text: string): void {
    this.cacheTexts.set(path, text);
  }

  isCacheDirty(path: string, current: string): boolean {
    const baseline = this.cacheTexts.get(path);
    return baseline !== undefined && baseline !== current;
  }

  async readChapter(path: string): Promise<string | null> {
    if (this.bridge === undefined) {
      return null;
    }
    return this.bridge.cacheRead(path);
  }

  async writeChapter(path: string, content: string): Promise<void> {
    if (this.bridge !== undefined) {
      await this.bridge.cacheWrite(path, content);
      this.recordCacheText(path, content);
    }
  }

  async deleteChapter(path: string): Promise<void> {
    if (this.bridge !== undefined) {
      await this.bridge.cacheDelete(path);
      this.cacheTexts.delete(path);
    }
  }

  async renameChapter(from: string, to: string): Promise<void> {
    if (this.bridge !== undefined) {
      await this.bridge.cacheRename(from, to);
      const text = this.cacheTexts.get(from);
      if (text !== undefined) {
        this.cacheTexts.delete(from);
        this.cacheTexts.set(to, text);
      }
    }
  }

  async renameDocument(from: string, to: string): Promise<void> {
    if (this.bridge !== undefined) {
      const fromDirectory = this.documentDirectory(from);
      const toDirectory = this.documentDirectory(to);
      const paths = await this.list();
      if (!paths.some((path) => path.startsWith(`${fromDirectory}/`))) {
        return;
      }
      await this.bridge.cacheMoveDirectory(fromDirectory, toDirectory);
      for (const [path, text] of [...this.cacheTexts.entries()]) {
        if (path === fromDirectory || path.startsWith(`${fromDirectory}/`)) {
          this.cacheTexts.delete(path);
          this.cacheTexts.set(`${toDirectory}${path.slice(fromDirectory.length)}`, text);
        }
      }
    }
  }

  async moveChapters(documentTitle: string, moves: ChapterCacheMove[]): Promise<void> {
    if (this.bridge === undefined) {
      return;
    }
    const documentDirectory = this.documentDirectory(documentTitle);
    const staged: Array<{ temporary: string; to: string }> = [];
    for (const move of moves) {
      const from = this.chapterPath(documentTitle, move.from);
      const to = this.chapterPath(documentTitle, move.to);
      if (from === to) {
        continue;
      }
      if ((await this.readChapter(from)) === null) {
        this.cacheTexts.delete(from);
        continue;
      }
      const temporary = `${documentDirectory}/.cache-move-${sanitizeSegment(move.id)}.md`;
      await this.renameChapter(from, temporary);
      staged.push({ temporary, to });
    }
    for (const move of staged) {
      await this.renameChapter(move.temporary, move.to);
    }
  }

  async deleteChapters(documentTitle: string, chapters: CacheChapter[]): Promise<void> {
    for (const chapter of chapters) {
      await this.deleteChapter(this.chapterPath(documentTitle, chapter));
    }
  }

  async deleteDocument(documentTitle: string): Promise<void> {
    const documentDirectory = this.documentDirectory(documentTitle);
    for (const path of await this.list()) {
      if (path.startsWith(`${documentDirectory}/`)) {
        await this.deleteChapter(path);
      }
    }
  }

  async list(): Promise<string[]> {
    return this.bridge === undefined ? [] : this.bridge.cacheList();
  }

  scheduleWrite(path: string, content: string): void {
    if (this.bridge === undefined) {
      return;
    }
    this.pendingWrites.set(path, content);
    if (this.timer !== null) {
      clearTimeout(this.timer);
    }
    this.timer = setTimeout(() => {
      this.timer = null;
      void this.flush();
    }, this.debounceMs);
  }

  async flush(): Promise<void> {
    if (this.bridge === undefined) {
      return;
    }
    if (this.timer !== null) {
      clearTimeout(this.timer);
      this.timer = null;
    }
    for (const [path, content] of [...this.pendingWrites.entries()]) {
      await this.bridge.cacheWrite(path, content);
      this.pendingWrites.delete(path);
      this.recordCacheText(path, content);
    }
  }
}
