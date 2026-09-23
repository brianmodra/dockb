import type { ApiClient } from "./api/client";
import { AppLayout } from "./layout/layout";
import { LeftPanel } from "./layout/leftPanel";

export interface MountShellOptions {
  api?: ApiClient;
  documentId?: string;
}

export function mountShell(root: HTMLElement, options: MountShellOptions = {}): AppLayout {
  root.replaceChildren();
  const layout = new AppLayout();
  root.append(layout.element);

  if (options.api) {
    const panel = new LeftPanel({ api: options.api });
    layout.leftPanelEl().append(panel.element);
    if (options.documentId) {
      void panel.load(options.documentId);
    }
  }

  return layout;
}