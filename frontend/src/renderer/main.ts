import type { ApiClient } from "./api/client";
import type { DockbBridge } from "./api/bridge";
import { checkSession } from "./api/session";
import { AppLayout } from "./layout/layout";
import { EditPanel } from "./layout/editPanel";
import { LeftPanel } from "./layout/leftPanel";
import { openDocumentPicker, openDocumentPickerConfirm } from "./layout/documentPicker";
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

export function mountShell(root: HTMLElement, options: MountShellOptions = {}): AppLayout {
  root.replaceChildren();

  const editPanel = options.api ? new EditPanel({ api: options.api }) : null;
  let stateController: AppStateController | null = null;
  let openDocument: () => void = () => {};

  const layout = new AppLayout({
    onOpen: () => openDocument(),
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

    openDocument = () => {
      void openDocumentPickerConfirm(options.api!).then((documentId) => {
        if (documentId === null) {
          return;
        }
        void panel.load(documentId);
        void controller.saveLastDocument(documentId);
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