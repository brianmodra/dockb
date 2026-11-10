import type { ApiClient } from "../api/client";
import type { ProofreadingCheckRequest, ProofreadingDiagnostic } from "../api/types";
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

export interface ProofreadingPoint {
  x: number;
  y: number;
}

export interface ProofreadingControllerOptions {
  api: Pick<ApiClient, "checkText" | "getGlossary" | "putGlossary">;
  target: ProofreadingTarget;
  documentId: () => string | null;
  language: () => string;
  onMessage?: (text: string) => void;
  debounceMs?: number;
}

/**
 * Debounces backend checks for the paragraph holding the cursor, drops replies
 * for text that has moved, and owns the diagnostic popover.
 */
export class ProofreadingController {
  private readonly options: ProofreadingControllerOptions;
  private timer: ReturnType<typeof setTimeout> | null = null;
  private abortController: AbortController | null = null;
  private requestId = 0;
  private popover: HTMLElement | null = null;
  private readonly glossaries = new Map<string, string[]>();
  private readonly onKeyDown = (event: KeyboardEvent): void => {
    if (event.key === "Escape") {
      this.closePopover();
    }
  };
  private readonly onPointerDown = (event: PointerEvent): void => {
    if (this.popover && !this.popover.contains(event.target as Node)) {
      this.closePopover();
    }
  };

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

  /** Open the suggestion popover for *diagnostic* at *point*. */
  openPopover(diagnostic: WysiwygDiagnostic, point: ProofreadingPoint): void {
    this.closePopover();
    const popover = document.createElement("div");
    popover.className = "proofreading-popover";
    popover.dataset.testid = "proofreading-popover";
    popover.style.left = `${point.x}px`;
    popover.style.top = `${point.y}px`;

    const message = document.createElement("div");
    message.className = "proofreading-message";
    message.textContent = diagnostic.message;
    popover.append(message);

    const replacements = diagnostic.replacements.slice(0, 5);
    if (replacements.length > 0) {
      const list = document.createElement("div");
      list.className = "proofreading-replacements";
      replacements.forEach((replacement) => {
        const button = document.createElement("button");
        button.type = "button";
        button.dataset.testid = "proofreading-replacement";
        button.textContent = replacement;
        button.addEventListener("click", () => {
          const applied = this.options.target.applyProofreadingReplacement(diagnostic, replacement);
          this.closePopover();
          if (applied) {
            this.schedule();
          }
        });
        list.append(button);
      });
      popover.append(list);
    }

    const addWord = document.createElement("button");
    addWord.type = "button";
    addWord.className = "proofreading-add-word";
    addWord.dataset.testid = "proofreading-add-word";
    addWord.textContent = "Add to dictionary";
    addWord.addEventListener("click", () => {
      void this.addWord(diagnostic);
    });
    popover.append(addWord);

    document.body.append(popover);
    window.addEventListener("keydown", this.onKeyDown);
    document.addEventListener("pointerdown", this.onPointerDown);
    this.popover = popover;
  }

  closePopover(): void {
    if (!this.popover) {
      return;
    }
    window.removeEventListener("keydown", this.onKeyDown);
    document.removeEventListener("pointerdown", this.onPointerDown);
    this.popover.remove();
    this.popover = null;
  }

  dispose(): void {
    if (this.timer !== null) {
      clearTimeout(this.timer);
      this.timer = null;
    }
    this.requestId += 1;
    this.abortController?.abort();
    this.abortController = null;
    this.closePopover();
    this.glossaries.clear();
  }

  private async addWord(diagnostic: WysiwygDiagnostic): Promise<void> {
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
      this.closePopover();
      await this.checkNow();
    } catch (error) {
      this.options.onMessage?.(`Could not add the word: ${errorMessage(error)}`);
    }
  }
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

