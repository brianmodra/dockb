export interface DockbBridge {
  platform: string;
  openExternal(url: string): Promise<void>;
  quit(): void;
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