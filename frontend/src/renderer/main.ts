import type { ApiClient } from "./api/client";
import type { DockbBridge } from "./api/bridge";
import { checkSession, signOut } from "./api/session";
import { AppLayout } from "./layout/layout";
import { EditPanel } from "./layout/editPanel";
import { LeftPanel } from "./layout/leftPanel";
import { openDocumentPicker, openDocumentPickerConfirm, openDeleteDocumentPicker, openDocumentAttrsPicker } from "./layout/documentPicker";
import { confirmModal, editDocumentModal, promptModal } from "./layout/modals";
import { openLanguageSettings } from "./layout/languageSettings";
import { openImportDialog, showImportSummaries, type ImportSelection } from "./layout/importDialog";
import { ensureSignedIn } from "./layout/signInFlow";
import { AppStateController } from "./state/appState";
import { runStartup } from "./state/startup";
import { quitApp, confirmUnsaved } from "./state/quit";
import { reportError } from "./log";

export interface MountShellOptions {
  api?: ApiClient;
  bridge?: DockbBridge;
}

/**
 * How the menu asks for a sign-out.
 *
 * `request` stays inert until boot has a session to end, so a writer who cancelled the
 * gate cannot ask the editor to log out of something it was never in.
 */
interface SignOutFlow {
  request: () => void;
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
  const signOut: SignOutFlow = { request: () => {} };

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
    onSignOut: () => signOut.request(),
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

    void boot(options.api, { layout, panel, controller, editPanel, signOut });
  }

  return layout;
}

interface BootContext {
  layout: AppLayout;
  panel: LeftPanel;
  controller: AppStateController;
  editPanel: EditPanel;
  signOut: SignOutFlow;
}

async function boot(api: ApiClient, ctx: BootContext): Promise<void> {
  const { layout, panel, controller, editPanel, signOut: signOutFlow } = ctx;
  const onMessage = (text: string): void => layout.pushMessage(text);

  let config: import("./api/types").AuthConfig;
  try {
    config = await api.getAuthConfig();
  } catch (error) {
    reportError("Backend config", error, onMessage);
    return;
  }

  if (!config.login_required) {
    // Nobody signed in, so there is no session for File → Sign out to end; the entry
    // keeps the inert handler mountShell gave it.
    let user: import("./api/types").UserProfile | null = null;
    try {
      user = (await checkSession(api))?.user ?? null;
    } catch (error) {
      user = null;
      reportError("Check session", error, onMessage);
    }
    if (user) {
      layout.setUser(user.username);
    }
    await startUp();
    return;
  }

  // One pass per session. Signing out finishes the pass, and the next one opens the
  // gate again, so the editor never needs a reload to get back to a login it can show.
  for (;;) {
    let resume: () => void = () => {};
    const signedOut = new Promise<void>((resolve) => {
      resume = resolve;
    });

    // One call for the whole gate: an existing session, a sign-in, and a forced
    // password change if one is owed.
    const session = await ensureSignedIn(api, { onMessage });
    if (!session) {
      // The user cancelled, or signed out of the change dialog. Stop here rather than
      // carrying on: every request below needs a session, so continuing would fire a
      // burst of guaranteed 401s at a server the user has just declined to talk to.
      signOutFlow.request = () => {};
      return;
    }
    layout.setUser(session.user.username);

    let ending = false;
    const requestSignOut = (): void => {
      if (ending) {
        return;
      }
      ending = true;
      void confirmUnsaved({
        isDirty: () => editPanel.isDirty(),
        save: () => editPanel.save(),
        confirmLabel: "Save",
        proceed: () => {
          void finishSignOut();
        },
      }).then((resolved) => {
        if (!resolved) {
          // Cancelled: still signed in, so the entry has to work again.
          ending = false;
          signOutFlow.request = requestSignOut;
        }
      });
    };
    signOutFlow.request = requestSignOut;

    const finishSignOut = async (): Promise<void> => {
      try {
        await signOut(api);
      } catch (error) {
        // The server still holds this session, so the editor stays signed in rather
        // than showing a gate that the next request would walk straight back through.
        reportError("Sign out", error, onMessage);
        ending = false;
        signOutFlow.request = requestSignOut;
        return;
      }
      panel.clear();
      editPanel.clear();
      layout.setUser("");
      signOutFlow.request = () => {};
      resume();
    };

    await startUp();
    await signedOut;
  }

  async function startUp(): Promise<void> {
    const savedState = await controller.load();
    await runStartup({
      savedState,
      restoreView: (panelWidths, editMode) =>
        layout.restoreState({ panel_widths: panelWidths, edit_mode: editMode }),
      pickDocument: () => openDocumentPicker(api),
      loadDocument: async (documentId) => {
        await panel.load(documentId);
        await controller.saveLastDocument(documentId);
      },
    });
  }
}
