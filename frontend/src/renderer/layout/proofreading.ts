import type { ApiClient } from "../api/client";
import type { ProofreadingCheckRequest, ProofreadingDiagnostic } from "../api/types";
import { proofreadingActionObjects } from "./responseArea";
import type { ResponseObject } from "./responseArea";
import type { ProofreadingParagraph, WysiwygDiagnostic } from "./wysiwyg";

export interface ProofreadingTarget {
  currentProofreadingParagraph(): ProofreadingParagraph | null;
  setProofreadingDiagnostics(
    context: ProofreadingParagraph,
    diagnostics: ProofreadingDiagnostic[],
  ): WysiwygDiagnostic[];
  clearProofreadingDiagnostics(): void;
  applyProofreadingReplacement(diagnostic: WysiwygDiagnostic, replacement: string): boolean;
}

export interface ProofreadingControllerOptions {
  api: Pick<ApiClient, "checkText" | "getGlossary" | "putGlossary">;
  target: ProofreadingTarget;
  documentId: () => string | null;
  language: () => string;
  onMessage?: (text: string) => void;
  onShowActions?: (objects: ResponseObject[]) => void;
  onCloseActions?: () => void;
  debounceMs?: number;
}

/**
 * Debounces backend checks for the paragraph holding the cursor, drops replies
 * for text that has moved, and shows a right-clicked diagnostic's actions in
 * the response area.
 */
export class ProofreadingController {
  private readonly options: ProofreadingControllerOptions;
  private timer: ReturnType<typeof setTimeout> | null = null;
  private abortController: AbortController | null = null;
  private requestId = 0;
  private active: WysiwygDiagnostic | null = null;
  private readonly glossaries = new Map<string, string[]>();

  constructor(options: ProofreadingControllerOptions) {
    this.options = options;
  }

  /** Queue a check after the debounce interval; a newer call replaces it. */
  schedule(): void {
    if (this.timer !== null) {
      clearTimeout(this.timer);
    }
    this.timer = setTimeout(() => {
      this.timer = null;
      void this.checkNow();
    }, this.options.debounceMs ?? 500);
  }

  /** Run a check now, aborting and invalidating any earlier one. */
  async checkNow(): Promise<void> {
    if (this.timer !== null) {
      clearTimeout(this.timer);
      this.timer = null;
    }
    const requestId = ++this.requestId;
    this.abortController?.abort();
    this.abortController = null;
    const context = this.options.target.currentProofreadingParagraph();
    if (!context || context.text.trim() === "") {
      this.options.target.clearProofreadingDiagnostics();
      return;
    }
    const controller = new AbortController();
    this.abortController = controller;
    const body: ProofreadingCheckRequest = { text: context.text };
    const language = this.options.language();
    const documentId = this.options.documentId();
    if (language) {
      body.language = language;
    }
    if (documentId) {
      body.document_id = documentId;
    }
    if (context.paragraphId) {
      body.paragraph_id = context.paragraphId;
    }
    if (context.focus) {
      body.focus = context.focus;
    }
    try {
      const response = await this.options.api.checkText(body, controller.signal);
      if (requestId !== this.requestId) {
        return;
      }
      if (this.options.documentId() !== documentId) {
        return;
      }
      const current = this.options.target.currentProofreadingParagraph();
      if (
        !current ||
        current.paragraphId !== context.paragraphId ||
        current.paragraphIndex !== context.paragraphIndex ||
        current.text !== context.text
      ) {
        return;
      }
      this.options.target.setProofreadingDiagnostics(context, response.diagnostics);
    } catch (error) {
      if (
        requestId !== this.requestId ||
        controller.signal.aborted ||
        (typeof error === "object" && error !== null && (error as { name?: unknown }).name === "AbortError")
      ) {
        return;
      }
      this.options.onMessage?.(`Proofreading failed: ${errorMessage(error)}`);
    } finally {
      if (this.abortController === controller) {
        this.abortController = null;
      }
    }
  }

  /** Hold *diagnostic* as the active one and show its actions in the response area. */
  showActions(diagnostic: WysiwygDiagnostic): void {
    this.active = diagnostic;
    this.options.onShowActions?.(proofreadingActionObjects(diagnostic));
  }

  /** Apply *replacement* to the active diagnostic's text in the editor buffer. */
  applyActiveReplacement(replacement: string): void {
    const diagnostic = this.active;
    if (diagnostic === null) {
      return;
    }
    const applied = this.options.target.applyProofreadingReplacement(diagnostic, replacement);
    this.closeActions();
    if (applied) {
      this.schedule();
    }
  }

  /** Add the active diagnostic's word to this document's glossary and re-check. */
  async addActiveWord(): Promise<void> {
    const diagnostic = this.active;
    if (diagnostic === null) {
      return;
    }
    const documentId = this.options.documentId();
    if (!documentId) {
      return;
    }
    try {
      let words = this.glossaries.get(documentId);
      if (!words) {
        words = [...(await this.options.api.getGlossary(documentId)).words];
        this.glossaries.set(documentId, words);
      }
      const folded = diagnostic.word.toLowerCase();
      if (!words.some((word) => word.toLowerCase() === folded)) {
        words = [...words, diagnostic.word];
        await this.options.api.putGlossary(documentId, words);
        this.glossaries.set(documentId, words);
      }
      this.closeActions();
      await this.checkNow();
    } catch (error) {
      this.options.onMessage?.(`Could not add the word: ${errorMessage(error)}`);
    }
  }

  /** Drop the active diagnostic and close its actions in the response area. */
  closeActions(): void {
    this.active = null;
    this.options.onCloseActions?.();
  }

  dispose(): void {
    if (this.timer !== null) {
      clearTimeout(this.timer);
      this.timer = null;
    }
    this.requestId += 1;
    this.abortController?.abort();
    this.abortController = null;
    this.closeActions();
    this.glossaries.clear();
  }
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

