export interface DockbBridge {
  platform: string;
  openExternal(url: string): Promise<void>;
}

declare global {
  interface Window {
    dockb: DockbBridge;
  }
}

export {};