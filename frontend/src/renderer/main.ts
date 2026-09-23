import type { ApiClient } from "./api/client";
import { AppLayout } from "./layout/layout";
import { EditPanel } from "./layout/editPanel";
import { LeftPanel } from "./layout/leftPanel";
import { openDocumentPicker } from "./layout/documentPicker";
import { AppStateController } from "./state/appState";
import { runStartup } from "./state/startup";
import { quitApp } from "./state/quit";

export interface MountShellOptions {
  api?: ApiClient;
}

export function mountShell(root: HTMLElement, options: MountShellOptions = {}): AppLayout {
  root.replaceChildren();

  const editPanel = options.api ? new EditPanel({ api: options.api }) : null;
  let stateController: AppStateController | null = null;

  const layout = new AppLayout({
    onSave: () => {
      void editPanel?.save();
    },
    onMode: (mode) => {
      editPanel?.setMode(mode);
      void stateController?.saveEditMode(mode);
    },
    onQuit: () => {
      void quitApp({
        isDirty: () => editPanel?.isDirty() ?? false,
        save: () => editPanel?.save() ?? Promise.resolve(null),
        onQuit: () => {
          window.dockb?.quit();
        },
      });
    },
    onWidthsChange: (widths) => {
      void stateController?.savePanelWidths(widths);
    },
  });
  root.append(layout.element);

  if (options.api && editPanel) {
    const controller = new AppStateController(options.api, {
      onMessage: (text) => layout.pushMessage(text),
    });
    stateController = controller;
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

    void controller.load().then((savedState) =>
      runStartup({
        savedState,
        restoreView: (panelWidths, editMode) => layout.restoreState({ panel_widths: panelWidths, edit_mode: editMode }),
        pickDocument: () => openDocumentPicker(options.api!),
        loadDocument: async (documentId) => {
          await panel.load(documentId);
          await controller.saveLastDocument(documentId);
        },
      }),
    );
  }

  return layout;
}