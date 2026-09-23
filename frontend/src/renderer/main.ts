import type { ApiClient } from "./api/client";
import { AppLayout } from "./layout/layout";
import { EditPanel } from "./layout/editPanel";
import { LeftPanel } from "./layout/leftPanel";

export interface MountShellOptions {
  api?: ApiClient;
  documentId?: string;
}

export function mountShell(root: HTMLElement, options: MountShellOptions = {}): AppLayout {
  root.replaceChildren();

  const editPanel = options.api ? new EditPanel({ api: options.api }) : null;

  const layout = new AppLayout({
    onSave: () => {
      void editPanel?.save();
    },
    onMode: (mode) => {
      editPanel?.setMode(mode);
    },
  });
  root.append(layout.element);

  if (options.api && editPanel) {
    editPanel.onMessage = (text) => layout.pushMessage(text);
    layout.editPanelEl().append(editPanel.element);

    const panel = new LeftPanel({
      api: options.api,
      onEdit: (chapterId) => {
        void editPanel.load(chapterId);
      },
      onMessage: (text) => layout.pushMessage(text),
    });
    layout.leftPanelEl().append(panel.element);

    if (options.documentId) {
      void panel.load(options.documentId);
    }
  }

  return layout;
}