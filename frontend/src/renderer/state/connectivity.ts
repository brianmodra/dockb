export interface ConnectivityOptions {
  enabled: boolean;
  onChange?: (online: boolean) => void;
}

export class Connectivity {
  readonly enabled: boolean;

  private online = true;
  private onChange?: (online: boolean) => void;
  private readonly subscribers = new Set<(online: boolean) => void>();

  constructor(options: ConnectivityOptions) {
    this.enabled = options.enabled;
    this.onChange = options.onChange;
  }

  setOnChange(handler: ((online: boolean) => void) | null): void {
    this.onChange = handler ?? undefined;
  }

  isOnline(): boolean {
    return this.online;
  }

  subscribe(listener: (online: boolean) => void): () => void {
    this.subscribers.add(listener);
    listener(this.online);
    return () => {
      this.subscribers.delete(listener);
    };
  }

  async setOnline(online: boolean): Promise<void> {
    if (this.online === online) {
      return;
    }
    this.online = online;
    this.onChange?.(online);
    for (const subscriber of [...this.subscribers]) {
      subscriber(online);
    }
  }
}
