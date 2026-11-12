import type { ApiClient } from "./api/client";
import type { DockbBridge } from "./api/bridge";
import { checkSession, signOut } from "./api/session";
import { AppLayout } from "./layout/layout";
import {
  PROOFREADING_ADD_WORD_FUNCTION,
  PROOFREADING_FIX_PAIR_FUNCTION,
  PROOFREADING_REPLACE_FUNCTION,
  parseResponseReply,
  selectionActionObjects,
} from "./layout/responseArea";
import { EditPanel } from "./layout/editPanel";
import { ProofreadingController } from "./layout/proofreading";
import { LeftPanel } from "./layout/leftPanel";
import { RightPanel, type ShelfChapter } from "./layout/rightPanel";
import { openDocumentPicker, openDocumentPickerConfirm, openDeleteDocumentPicker, openDocumentAttrsPicker } from "./layout/documentPicker";
import { confirmModal, editDocumentModal, promptModal } from "./layout/modals";
import { LANGUAGES, openLanguageSettings } from "./layout/languageSettings";
import { openDictionaryDialog } from "./layout/dictionaryDialog";
import { openImportDialog, showImportSummaries, type ImportSelection } from "./layout/importDialog";
import { ensureSignedIn } from "./layout/signInFlow";
import { AppStateController } from "./state/appState";
import { runStartup } from "./state/startup";
import { defaultProofreadingLanguage } from "./state/language";
import { quitApp, confirmUnsaved } from "./state/quit";
import { warningModal } from "./layout/modals";
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
  let currentDocumentId: () => string | null = () => null;
  let runHighlight: (rawArgs: unknown) => Promise<void> = async () => {};
  let runQuote: (rawArgs: unknown) => void = () => {};
  let runReadonlyScroll: (rawArgs: unknown) => void = () => {};
  let loadDocumentMentions: (documentId: string) => void = () => {};
  let proofreading: ProofreadingController | null = null;
  let editorPromptOpen = false;
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
      void (async () => {
        let languages = LANGUAGES;
        if (options.api && typeof options.api.getProofreadingLanguages === "function") {
          try {
            const response = await options.api.getProofreadingLanguages();
            if (response.languages.length > 0) {
              languages = response.languages;
            }
          } catch {
            // The dialog still works with its built-in list while the backend is away.
          }
        }
        const lang = await openLanguageSettings({
          current: editPanel?.getLanguage() ?? "en-US",
          languages,
        });
        if (lang !== null) {
          editPanel?.setLanguage(lang);
        }
      })();
    },
    onOpenDictionary: () => {
      if (!options.api) {
        return;
      }
      openDictionaryDialog({
        api: options.api,
        documentId: currentDocumentId(),
        onMessage: (text) => layout.pushMessage(text),
        onWordsChanged: () => {
          void proofreading?.checkNow();
        },
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
    onPrompt: (prompt) => {
      if (!options.api) {
        return;
      }
      editorPromptOpen = false;
      layout.beginResponse();
      void options.api
        .sendPrompt(prompt, currentDocumentId())
        .then((response) => {
          editorPromptOpen = false;
          const parsed = parseResponseReply(response.reply);
          if (parsed === null) {
            layout.cancelResponse();
            layout.pushMessage(response.reply);
          } else {
            layout.showResponse(parsed);
          }
        })
        .catch((error) => {
          editorPromptOpen = false;
          layout.cancelResponse();
          reportError("AI chat", error, (text) => layout.pushMessage(text));
        });
    },
    responseFunctions: {
      highlight: (args) => void runHighlight(args),
      quote: (args) => runQuote(args),
      "readonly-scroll": (args) => runReadonlyScroll(args),
      [PROOFREADING_REPLACE_FUNCTION]: (args) => {
        const replacement =
          typeof args === "object" && args !== null ? (args as { replacement?: unknown }).replacement : undefined;
        if (typeof replacement === "string") {
          proofreading?.applyActiveReplacement(replacement);
        }
      },
      [PROOFREADING_ADD_WORD_FUNCTION]: () => {
        void proofreading?.addActiveWord();
      },
      [PROOFREADING_FIX_PAIR_FUNCTION]: () => {
        proofreading?.applyActivePair();
      },
    },
  });
  root.append(layout.element);

  if (options.api && editPanel) {
    const api = options.api;
    const controller = new AppStateController(api, {
      onMessage: (text) => layout.pushMessage(text),
    });
    stateController = controller;
    editPanel.onMessage = (text) => layout.pushMessage(text);
    editPanel.onDirtyChange = (dirty) => layout.setDirty(dirty);
    editPanel.onWarning = (text) => void warningModal("POV warning", text);
    editPanel.onSelectionActions = (context) => {
      editorPromptOpen = true;
      layout.showResponse(selectionActionObjects(context));
    };
    editPanel.onSelectionChange = () => {
      if (editorPromptOpen) {
        editorPromptOpen = false;
        layout.cancelResponse();
      }
    };
    layout.editPanelEl().append(editPanel.element);

    const rightPanel = new RightPanel({
      api: options.api,
      onMessage: (text) => layout.pushMessage(text),
    });
    layout.rightPanelEl().append(rightPanel.element);

    const panel = new LeftPanel({
      api: options.api,
      onEdit: (chapterId) => {
        void editPanel.open(chapterId);
      },
      onMessage: (text) => layout.pushMessage(text),
      onReadonly: (chapterId, title) => {
        rightPanel.addWriterChapter(chapterId, title);
      },
      onPovChanged: (chapterId, povTitle) => {
        // The file's pov line changed under the open buffer: a clean buffer
        // re-reads it; a dirty one learns the line in place, so its next save
        // carries the pov instead of clearing it.
        if (panel.selectedChapter()?.id === chapterId) {
          if (editPanel.isDirty()) {
            editPanel.refreshPovLine(povTitle);
          } else {
            void editPanel.load(chapterId);
          }
        }
      },
    });
    layout.leftPanelEl().append(panel.element);
    currentDocumentId = () => panel.currentDocumentId();

    let mentionMap: Record<string, string[]> = {};
    let lastMentionParagraphId: string | null = null;

    const refreshMentionTabs = (): void => {
      const paragraphId = editPanel.proofreadingParagraph()?.paragraphId ?? null;
      if (paragraphId === lastMentionParagraphId) {
        return;
      }
      lastMentionParagraphId = paragraphId;
      const characterIds = paragraphId === null ? [] : (mentionMap[paragraphId] ?? []);
      const chapters = characterIds
        .map((characterId): ShelfChapter | null => {
          const title = panel.titleOf(characterId);
          return title === null ? null : { chapterId: characterId, title };
        })
        .filter((chapter): chapter is ShelfChapter => chapter !== null);
      rightPanel.setCharacterChapters(chapters);
    };

    loadDocumentMentions = (documentId: string): void => {
      mentionMap = {};
      lastMentionParagraphId = null;
      rightPanel.setCharacterChapters([]);
      void api.getDocumentMentions(documentId).then(
        (response) => {
          mentionMap = response.mentions;
          refreshMentionTabs();
        },
        (error) => reportError("Load mentions", error, (text) => layout.pushMessage(text)),
      );
    };

    editPanel.onSelectionChange = () => {
      if (editorPromptOpen) {
        editorPromptOpen = false;
        layout.cancelResponse();
      }
      refreshMentionTabs();
    };

    if (
      typeof options.api.checkText === "function" &&
      typeof options.api.postGlossary === "function"
    ) {
      proofreading = new ProofreadingController({
        api: options.api,
        target: {
          currentProofreadingParagraph: () => editPanel.proofreadingParagraph(),
          setProofreadingDiagnostics: (context, diagnostics) =>
            editPanel.setProofreadingDiagnostics(context, diagnostics),
          clearProofreadingDiagnostics: () => editPanel.clearProofreadingDiagnostics(),
          applyProofreadingReplacement: (diagnostic, replacement) =>
            editPanel.applyProofreadingReplacement(diagnostic, replacement),
          applyProofreadingPair: (diagnostic) => editPanel.applyProofreadingPair(diagnostic),
        },
        documentId: () => panel.currentDocumentId(),
        language: () => editPanel.getLanguage(),
        onMessage: (text) => layout.pushMessage(text),
        onShowActions: (objects) => {
          editorPromptOpen = true;
          layout.showResponse(objects);
        },
        onCloseActions: () => {
          editorPromptOpen = false;
          layout.cancelResponse();
        },
      });
      editPanel.onDiagnostic = (diagnostic) => proofreading?.showActions(diagnostic);
      editPanel.onEditActivity = () => proofreading?.schedule();
    }

    /**
     * A reply's highlight button: open the named chapter (saving the dirty open
     * buffer first), then select the named sentences — the whole paragraph when
     * the reply carries no usable `sentence_indices` positions — scrolled into
     * view. The positions come from the tool's own marks, so no second
     * chapter read is ever needed.
     */
    runHighlight = async (rawArgs: unknown): Promise<void> => {
      const args = (typeof rawArgs === "object" && rawArgs !== null ? rawArgs : {}) as {
        chapter_id?: unknown;
        paragraph_id?: unknown;
        sentence_indices?: unknown;
      };
      const chapterId = typeof args.chapter_id === "string" ? args.chapter_id : null;
      const paragraphId = typeof args.paragraph_id === "string" ? args.paragraph_id : null;
      // a lone number instead of an array is accepted as a one-entry list;
      // junk inside the array is skipped, not treated as "highlight nothing"
      const sentenceIndexes = (Array.isArray(args.sentence_indices)
        ? args.sentence_indices
        : [args.sentence_indices]
      )
        .filter((index) => typeof index === "number" && Number.isFinite(index))
        .map(Math.trunc);
      if (!chapterId || !paragraphId || !options.api || !editPanel) {
        layout.pushMessage("The AI's highlight button is missing its chapter or paragraph.");
        return;
      }
      try {
        if (editPanel.currentChapter() !== chapterId) {
          panel.select(chapterId);
          await editPanel.open(chapterId);
        }
        const selected = editPanel.selectSentences(
          paragraphId,
          sentenceIndexes.length > 0 ? sentenceIndexes : null,
        );
        if (!selected) {
          layout.pushMessage("Highlighting works in WYSIWYG chapters.");
        }
      } catch (error) {
        reportError("Highlight", error, (text) => layout.pushMessage(text));
      }
    };

    runQuote = (rawArgs: unknown): void => {
      editorPromptOpen = false;
      layout.cancelResponse();
      if (!editPanel || !editPanel.applyQuote(rawArgs)) {
        layout.pushMessage("Quoting works in WYSIWYG chapters.");
      }
    };

    runReadonlyScroll = (rawArgs: unknown): void => {
      const args = (typeof rawArgs === "object" && rawArgs !== null ? rawArgs : {}) as {
        chapter_id?: unknown;
        paragraph_id?: unknown;
      };
      const chapterId = typeof args.chapter_id === "string" ? args.chapter_id : null;
      const paragraphId = typeof args.paragraph_id === "string" ? args.paragraph_id : null;
      if (chapterId === null || paragraphId === null) {
        layout.pushMessage("The read-only button is missing its chapter or paragraph.");
        return;
      }
      const title = panel.titleOf(chapterId);
      if (title === null) {
        layout.pushMessage("That chapter is not in this document.");
        return;
      }
      rightPanel.addWriterChapterAt(chapterId, title, paragraphId);
    };

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
        loadDocumentMentions(documentId);
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

    void boot(options.api, { layout, panel, controller, editPanel, signOut, loadDocumentMentions });
  }

  return layout;
}

interface BootContext {
  layout: AppLayout;
  panel: LeftPanel;
  controller: AppStateController;
  editPanel: EditPanel;
  signOut: SignOutFlow;
  loadDocumentMentions: (documentId: string) => void;
}

async function boot(api: ApiClient, ctx: BootContext): Promise<void> {
  const { layout, panel, controller, editPanel, signOut: signOutFlow, loadDocumentMentions } = ctx;
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
    const language = await defaultProofreadingLanguage(api);
    if (language !== null) {
      editPanel.setLanguage(language);
    }
    await runStartup({
      savedState,
      restoreView: (panelWidths, editMode) =>
        layout.restoreState({ panel_widths: panelWidths, edit_mode: editMode }),
      pickDocument: () => openDocumentPicker(api),
      loadDocument: async (documentId) => {
        await panel.load(documentId);
        loadDocumentMentions(documentId);
        await controller.saveLastDocument(documentId);
      },
    });
  }
}
