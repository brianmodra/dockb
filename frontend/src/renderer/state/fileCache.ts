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

  async readChapter(path: string): Promise<string | null> {
    if (this.bridge === undefined) {
      return null;
    }
    return this.bridge.cacheRead(path);
  }

  async writeChapter(path: string, content: string): Promise<void> {
    if (this.bridge !== undefined) {
      await this.bridge.cacheWrite(path, content);
    }
  }

  async deleteChapter(path: string): Promise<void> {
    if (this.bridge !== undefined) {
      await this.bridge.cacheDelete(path);
    }
  }

  async renameChapter(from: string, to: string): Promise<void> {
    if (this.bridge !== undefined) {
      await this.bridge.cacheRename(from, to);
    }
  }

  async renameDocument(from: string, to: string): Promise<void> {
    if (this.bridge !== undefined) {
      await this.bridge.cacheMoveDirectory(this.documentDirectory(from), this.documentDirectory(to));
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
    }
  }
}
