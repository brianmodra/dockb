export interface DockbBridge {
  platform: string;
  isElectron: boolean;
  openExternal(url: string): Promise<void>;
  quit(): void;
  chooseCacheDirectory(): Promise<string | null>;
  setCacheRoot(directory: string): Promise<void>;
  cacheRead(relativePath: string): Promise<string | null>;
  cacheWrite(relativePath: string, content: string): Promise<void>;
  cacheDelete(relativePath: string): Promise<void>;
  cacheRename(from: string, to: string): Promise<void>;
  cacheMoveDirectory(from: string, to: string): Promise<void>;
  cacheList(): Promise<string[]>;
  /**
   * The absolute path of a file the user chose through a native dialog.
   *
   * Empty when the File is not backed by disk. This is the only way the renderer
   * learns a filesystem path, and only for a file the user just picked; it grants
   * no other access to the disk.
   */
  getPathForFile(file: File): string;
}

declare global {
  interface Window {
    dockb: DockbBridge;
  }
}

export {};