import type { ApiClient } from "./api/client";
import type { DockbBridge } from "./api/bridge";
import { checkSession } from "./api/session";
import { AppLayout } from "./layout/layout";
import { EditPanel } from "./layout/editPanel";
import { LeftPanel } from "./layout/leftPanel";
import { openDocumentPicker, openDocumentPickerConfirm, openDeleteDocumentPicker, openDocumentAttrsPicker } from "./layout/documentPicker";
import { confirmModal, editDocumentModal, promptModal } from "./layout/modals";
import { openLanguageSettings } from "./layout/languageSettings";
import { openImportDialog, showImportSummaries, type ImportSelection } from "./layout/importDialog";
import { openSignInGate } from "./layout/signInGate";
import { AppStateController } from "./state/appState";
import { runStartup } from "./state/startup";
import { quitApp } from "./state/quit";
import { reportError } from "./log";

export interface MountShellOptions {
  api?: ApiClient;
  bridge?: DockbBridge;
  provider?: string;
}

async function sendImport(
  selection: ImportSelection,
  api: ApiClient,
  layout: AppLayout,
): Promise<void> {
  try {
    const response = await api.importDocument(selection.directoryName, selection.files, {
      singleNewlineParagraphs: selection.singleNewlineParagraphs,
    });
    showImportSummaries(response.imports);
  } catch (error) {
    reportError("Import", error, (text) => layout.pushMessage(text));
  }
}

export function mountShell(root: HTMLElement, options: MountShellOptions = {}): AppLayout {
  root.replaceChildren();

  const editPanel = options.api ? new EditPanel({ api: options.api }) : null;
  let stateController: AppStateController | null = null;
  let openDocument: () => void = () => {};
  let runImport: () => void = () => {};
  let runDeleteDocument: () => void = () => {};
  let runEditDocument: () => void = () => {};
  let runEditChapter: () => void = () => {};

  const layout = new AppLayout({
    onOpen: () => openDocument(),
    onImport: () => runImport(),
    onDeleteDocument: () => runDeleteDocument(),
    onEditDocument: () => runEditDocument(),
    onEditChapter: () => runEditChapter(),
    onSave: () => {
      void editPanel?.save();
    },
    onMode: (mode) => {
      editPanel?.setMode(mode);
      void stateController?.saveEditMode(mode);
    },
    onOpenLanguageSettings: () => {
      void openLanguageSettings({ current: editPanel?.getLanguage() ?? "en-US" }).then((lang) => {
        if (lang !== null) {
          editPanel?.setLanguage(lang);
        }
      });
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
    editPanel.onDirtyChange = (dirty) => layout.setDirty(dirty);
    layout.editPanelEl().append(editPanel.element);

    const panel = new LeftPanel({
      api: options.api,
      onEdit: (chapterId) => {
        void editPanel.load(chapterId);
      },
      onMessage: (text) => layout.pushMessage(text),
    });
    layout.leftPanelEl().append(panel.element);

    runDeleteDocument = () => {
      void openDeleteDocumentPicker(options.api!).then((selection) => {
        if (selection === null) {
          return;
        }
        void confirmModal({
          title: "Delete document",
          message: `Are you sure you want to delete "${selection.title}"?`,
          confirmLabel: "Delete",
        }).then((confirmed) => {
          if (!confirmed) {
            return;
          }
          void options.api!.deleteDocument(selection.documentId).then(
            () => {
              layout.pushMessage(`Deleted "${selection.title}".`);
              if (panel.currentDocumentId() === selection.documentId) {
                panel.clear();
                editPanel.clear();
                void stateController?.saveLastDocument(null);
              }
            },
            (error) => reportError("Delete document", error, (text) => layout.pushMessage(text)),
          );
        });
      });
    };

    openDocument = () => {
      void openDocumentPickerConfirm(options.api!).then((documentId) => {
        if (documentId === null) {
          return;
        }
        void panel.load(documentId);
        void controller.saveLastDocument(documentId);
      });
    };

    runImport = () => {
      void openImportDialog(options.bridge, { onMessage: (text) => layout.pushMessage(text) })
        .then((selection) => {
          if (selection !== null) {
            void sendImport(selection, options.api!, layout);
          }
        })
        .catch((error) => {
          reportError("Import", error, (text) => layout.pushMessage(text));
        });
    };

    runEditDocument = () => {
      void openDocumentAttrsPicker(options.api!).then((attrs) => {
        if (attrs === null) {
          return;
        }
        void editDocumentModal({ title: attrs.title, author: attrs.author }).then((values) => {
          if (values === null) {
            return;
          }
          void options.api!.updateDocument(attrs.id, { title: values.title, author: values.author }).then(
            () => {
              layout.pushMessage(`Updated "${values.title}".`);
              void panel.reload();
            },
            (error) => reportError("Edit document", error, (text) => layout.pushMessage(text)),
          );
        });
      });
    };

    runEditChapter = () => {
      const chapter = panel.selectedChapter();
      if (chapter === null) {
        return;
      }
      void promptModal({
        title: "Edit chapter",
        label: "Title",
        initial: chapter.title,
        confirmLabel: "Save",
      }).then((result) => {
        if (result.value !== "confirm") {
          return;
        }
        void options.api!.updateChapter(chapter.id, { title: result.input }).then(
          () => {
            layout.pushMessage(`Renamed chapter to "${result.input}".`);
            void panel.reload();
          },
          (error) => reportError("Edit chapter", error, (text) => layout.pushMessage(text)),
        );
      });
    };

    void boot(options.api, options.bridge ?? window.dockb, options.provider, layout, panel, controller);
  }

  return layout;
}

async function boot(
  api: ApiClient,
  bridge: DockbBridge | undefined,
  provider: string | undefined,
  layout: AppLayout,
  panel: LeftPanel,
  controller: AppStateController,
): Promise<void> {
  let config: import("./api/types").AuthConfig;
  try {
    config = await api.getAuthConfig();
  } catch (error) {
    reportError("Backend config", error, (text) => layout.pushMessage(text));
    return;
  }

  let user: import("./api/types").UserProfile | null = null;
  if (config.login_required) {
    try {
      user = await checkSession(api);
    } catch {
      user = null;
    }
    if (!user) {
      if (!bridge) {
        return;
      }
      const ok = await openSignInGate(api, bridge, {
        provider: provider ?? config.providers[0],
        onMessage: (text) => layout.pushMessage(text),
      });
      if (!ok) {
        return;
      }
      user = await checkSession(api);
    }
  } else {
    try {
      user = await checkSession(api);
    } catch (error) {
      user = null;
      reportError("Check session", error, (text) => layout.pushMessage(text));
    }
  }
  if (user) {
    layout.setUser(user.username);
  }

  const savedState = await controller.load();
  await runStartup({
    savedState,
    restoreView: (panelWidths, editMode) => layout.restoreState({ panel_widths: panelWidths, edit_mode: editMode }),
    pickDocument: () => openDocumentPicker(api),
    loadDocument: async (documentId) => {
      await panel.load(documentId);
      await controller.saveLastDocument(documentId);
    },
  });
}