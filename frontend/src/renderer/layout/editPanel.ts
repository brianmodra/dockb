import { EditorState, Compartment, type Extension } from "@codemirror/state";
import { EditorView, lineNumbers, keymap } from "@codemirror/view";
import { defaultKeymap, history, historyKeymap } from "@codemirror/commands";
import { markdown } from "@codemirror/lang-markdown";
import { syntaxHighlighting, defaultHighlightStyle, indentOnInput } from "@codemirror/language";
import {
  forEachDiagnostic,
  setDiagnostics as setLintDiagnostics,
  type Diagnostic as CodeMirrorDiagnostic,
} from "@codemirror/lint";
import type { ApiClient } from "../api/client";
import type { DocumentContentResponse } from "../api/types";
import { reportError } from "../log";
import { characterHeaderText, frontMatterFields, manuscriptHeaderText } from "./characterHeader";
import type { ProofreadingDiagnostic } from "../api/types";
import {
  mapRawProofreadingDiagnostics,
  rawProofreadingParagraphAt,
  rawProofreadingParagraphFor,
  rawProofreadingText,
} from "./rawProofreading";
import {
  WysiwygView,
  chapterBody,
  quoteSignatureOf,
  type ProofreadingParagraph,
  type SelectionContext,
  type WysiwygDiagnostic,
} from "./wysiwyg";
import type { Mode } from "./menubar";

export type EditPanelApi = Pick<ApiClient, "getChapterDocument" | "saveChapterDocument">;

export interface EditPanelOptions {
  api: EditPanelApi;
  onMessage?: (text: string) => void;
  onWarning?: (text: string) => void;
  onDirtyChange?: (dirty: boolean) => void;
  onSelectionActions?: (context: SelectionContext) => void;
  onSelectionChange?: () => void;
  onDiagnostic?: (diagnostic: WysiwygDiagnostic) => void;
}

export class EditPanel {
  readonly element: HTMLElement;

  api: EditPanelApi;
  onMessage?: (text: string) => void;
  onWarning?: (text: string) => void;
  onDirtyChange?: (dirty: boolean) => void;
  onSelectionActions?: (context: SelectionContext) => void;
  onSelectionChange?: () => void;
  onDiagnostic?: (diagnostic: WysiwygDiagnostic) => void;
  onEditActivity?: () => void;
  private view: EditorView;
  private readonly wysiwyg: WysiwygView;
  private readonly rawHost: HTMLElement;
  private readonly wysiwygHost: HTMLElement;
  private mode: Mode = "wysiwyg";
  private chapterId: string | null = null;
  private lastCanonicalText: string | null = null;
  private lastDirty: boolean | null = null;
  private readonly readOnlyCompartment = new Compartment();
  private busy = false;
  private readonly header: HTMLElement;
  private rawProofreading = new Map<CodeMirrorDiagnostic, WysiwygDiagnostic>();

  constructor(options: EditPanelOptions) {
    this.api = options.api;
    this.onMessage = options.onMessage;
    this.onWarning = options.onWarning;
    this.onDirtyChange = options.onDirtyChange;
    this.onSelectionActions = options.onSelectionActions;
    this.onSelectionChange = options.onSelectionChange;
    this.onDiagnostic = options.onDiagnostic;

    this.element = document.createElement("div");
    this.element.className = "edit-panel";
    this.element.dataset.testid = "edit-panel";

    this.header = document.createElement("div");
    this.header.className = "chapter-header";
    this.header.dataset.testid = "chapter-header";
    this.header.setAttribute("contenteditable", "false");

    this.rawHost = document.createElement("div");
    this.rawHost.dataset.testid = "edit-raw";
    this.wysiwygHost = document.createElement("div");
    this.wysiwygHost.dataset.testid = "edit-wysiwyg";
    const scroll = document.createElement("div");
    scroll.className = "edit-scroll";
    // the header lives inside the scroll container, so the original scrollbar
    // covers it alongside the chapter text and nothing spills into .panel to
    // grow a second, far-right scrollbar
    scroll.append(this.header, this.rawHost, this.wysiwygHost);
    this.element.append(scroll);

    const state = EditorState.create({
      doc: "",
      extensions: [
        lineNumbers(),
        history(),
        keymap.of([...defaultKeymap, ...historyKeymap]),
        indentOnInput(),
        syntaxHighlighting(defaultHighlightStyle, { fallback: true }),
        markdown(),
        this.readOnlyCompartment.of(this.editableExtensions()),
        EditorView.updateListener.of((update) => {
          if (update.docChanged) {
            this.notifyDirty();
          }
          if (update.docChanged || update.selectionSet) {
            this.onEditActivity?.();
          }
        }),
      ],
    });
    this.view = new EditorView({ state, parent: this.rawHost });
    this.wysiwyg = new WysiwygView({
      onChange: () => {
        this.notifyDirty();
        this.onEditActivity?.();
      },
      onSelectionChange: () => {
        this.onSelectionChange?.();
        this.onEditActivity?.();
      },
    });
    this.wysiwygHost.append(this.wysiwyg.element);
    this.wysiwygHost.addEventListener("contextmenu", (event) => this.openParagraphMenu(event));
    this.rawHost.addEventListener("contextmenu", (event) => this.openRawParagraphMenu(event));
    this.applyMode();
  }

  /**
   * Right-click with a selection: hand the selected text's context to the
   * caller, which offers the quote actions in the response area. With no
   * selection the browser's own menu is left alone.
   */
  private openParagraphMenu(event: MouseEvent): void {
    const diagnostic = this.wysiwyg.diagnosticAtPoint(event.clientX, event.clientY);
    if (diagnostic !== null) {
      event.preventDefault();
      this.onDiagnostic?.(diagnostic);
      return;
    }
    const context = this.wysiwyg.selectionContext();
    if (context === null) {
      return;
    }
    event.preventDefault();
    this.onSelectionActions?.(context);
  }

  private openRawParagraphMenu(event: MouseEvent): void {
    if (this.mode !== "raw") {
      return;
    }
    const diagnostic = this.rawDiagnosticAtPoint(event.clientX, event.clientY);
    if (diagnostic === null) {
      return;
    }
    event.preventDefault();
    this.onDiagnostic?.(diagnostic);
  }

  private rawDiagnosticAtPoint(x: number, y: number): WysiwygDiagnostic | null {
    const position = this.view.posAtCoords({ x, y });
    if (position === null) {
      return null;
    }
    let hit: { diagnostic: CodeMirrorDiagnostic; from: number; to: number } | null = null;
    forEachDiagnostic(this.view.state, (diagnostic, from, to) => {
      if (hit === null && position >= from && position <= to) {
        hit = { diagnostic, from, to };
      }
    });
    if (hit === null) {
      return null;
    }
    const found = hit as { diagnostic: CodeMirrorDiagnostic; from: number; to: number };
    const meta = this.rawProofreading.get(found.diagnostic);
    if (!meta) {
      return null;
    }
    const word = rawProofreadingText(this.view.state.doc.sliceString(found.from, found.to));
    return { ...meta, from: found.from, to: found.to, word };
  }

  /**
   * Apply a quote action chosen from the response area: set, change, or clear
   * the quote type of the named paragraphs. The args come from outside the
   * editor, so the type and identities are checked before anything changes.
   */
  applyQuote(rawArgs: unknown): boolean {
    if (this.mode !== "wysiwyg" || typeof rawArgs !== "object" || rawArgs === null) {
      return false;
    }
    const args = rawArgs as Record<string, unknown>;
    const quoteType = args.quote_type;
    if (quoteType !== "" && quoteType !== "reading" && quoteType !== "writing") {
      return false;
    }
    if (!Array.isArray(args.paragraph_ids) || args.paragraph_ids.length === 0) {
      return false;
    }
    if (!args.paragraph_ids.every((id) => id === null || typeof id === "string")) {
      return false;
    }
    const ids = args.paragraph_ids as Array<string | null>;
    const indexes = Array.isArray(args.paragraph_indexes)
      ? args.paragraph_indexes.map((value) =>
          typeof value === "number" && Number.isInteger(value) ? value : Number.NaN,
        )
      : [];
    return this.wysiwyg.setQuoteTypeByIds(ids, indexes, quoteType);
  }

  setMode(mode: Mode): void {
    if (mode === this.mode) {
      return;
    }
    const text = this.isDirty() ? this.content() : (this.lastCanonicalText ?? this.content());
    this.mode = mode;
    this.applyMode();
    this.replaceDoc(text);
  }

  /**
   * Open a chapter, saving the open buffer first when it is dirty.
   *
   * A failed save keeps the editor on the open chapter: the click that would
   * leave it must not lose the writer's text. The failure is already reported
   * by save() to the message panel; the writer can retry the click once the
   * backend answers again.
   */
  async open(chapterId: string): Promise<void> {
    if (this.isDirty()) {
      const saved = await this.save();
      if (saved === null) {
        return;
      }
    }
    await this.load(chapterId);
  }

  setContent(text: string): void {
    this.replaceDoc(text);
  }

  content(): string {
    return this.mode === "raw" ? this.view.state.doc.toString() : this.wysiwyg.content();
  }

  clear(): void {
    this.chapterId = null;
    this.lastCanonicalText = null;
    this.replaceDoc("");
    this.notifyDirty();
    this.onSelectionChange?.();
  }

  isDirty(): boolean {
    if (this.lastCanonicalText === null) {
      return false;
    }
    return this.mode === "raw"
      ? this.view.state.doc.toString() !== this.lastCanonicalText
      : this.wysiwyg.plainContent() !== chapterBody(this.lastCanonicalText) ||
          this.wysiwyg.quoteSignature() !== quoteSignatureOf(this.lastCanonicalText);
  }

  lastCanonical(): string | null {
    return this.lastCanonicalText;
  }

  /** The chapter whose document the panel is showing, if any. */
  currentChapter(): string | null {
    return this.chapterId;
  }

  /**
   * Select one or more sentences of a paragraph as the WYSIWYG view shows it,
   * so a reply's highlight button can point the writer at them. No sentence
   * named selects the whole paragraph. The raw view has no sentences (the
   * canonical file is its content), so there it answers false.
   */
  selectSentences(paragraphId: string, sentenceIndexes: number[] | null): boolean {
    return this.mode === "wysiwyg" && this.wysiwyg.selectSentences(paragraphId, sentenceIndexes);
  }

  proofreadingParagraph(): ProofreadingParagraph | null {
    if (this.mode === "raw") {
      const paragraph = rawProofreadingParagraphAt(
        this.view.state.doc.toString(),
        this.view.state.selection.main.head,
      );
      return paragraph?.context ?? null;
    }
    return this.wysiwyg.currentProofreadingParagraph();
  }

  setProofreadingDiagnostics(
    context: ProofreadingParagraph,
    diagnostics: ProofreadingDiagnostic[],
  ): WysiwygDiagnostic[] {
    if (this.mode === "raw") {
      const paragraph = rawProofreadingParagraphFor(this.view.state.doc.toString(), context);
      if (paragraph === null) {
        this.clearRawProofreadingDiagnostics();
        return [];
      }
      const mapped = mapRawProofreadingDiagnostics(paragraph, diagnostics);
      const lintDiagnostics = mapped.map((diagnostic): CodeMirrorDiagnostic => ({
        from: diagnostic.from,
        to: diagnostic.to,
        severity: lintSeverity(diagnostic.severity),
        message: diagnostic.message,
        source: diagnostic.rule_id,
      }));
      this.rawProofreading = new Map(
        lintDiagnostics.map((diagnostic, index) => [diagnostic, mapped[index]]),
      );
      this.view.dispatch(setLintDiagnostics(this.view.state, lintDiagnostics));
      return mapped;
    }
    return this.wysiwyg.setProofreadingDiagnostics(context, diagnostics);
  }

  clearProofreadingDiagnostics(): void {
    this.wysiwyg.clearProofreadingDiagnostics();
    this.clearRawProofreadingDiagnostics();
  }

  applyProofreadingReplacement(diagnostic: WysiwygDiagnostic, replacement: string): boolean {
    if (this.mode === "raw") {
      const length = this.view.state.doc.length;
      if (
        typeof diagnostic.from !== "number" ||
        typeof diagnostic.to !== "number" ||
        diagnostic.from < 0 ||
        diagnostic.to > length ||
        diagnostic.from >= diagnostic.to ||
        rawProofreadingText(this.view.state.doc.sliceString(diagnostic.from, diagnostic.to)) !==
          diagnostic.word
      ) {
        return false;
      }
      this.view.dispatch({
        changes: { from: diagnostic.from, to: diagnostic.to, insert: replacement },
      });
      return true;
    }
    return this.wysiwyg.applyProofreadingReplacement(diagnostic, replacement);
  }

  private clearRawProofreadingDiagnostics(): void {
    this.rawProofreading.clear();
    this.view.dispatch(setLintDiagnostics(this.view.state, []));
  }

  getLanguage(): string {
    return this.wysiwyg.getLanguage();
  }

  setLanguage(lang: string): void {
    this.wysiwyg.setLanguage(lang);
    this.onEditActivity?.();
  }

  private notifyDirty(): void {
    const dirty = this.isDirty();
    if (dirty === this.lastDirty) {
      return;
    }
    this.lastDirty = dirty;
    this.onDirtyChange?.(dirty);
  }

  /**
   * The facets that decide whether the raw editor takes input.
   *
   * `EditorState.readOnly` stops user edits changing the document;
   * `EditorView.editable` takes the contenteditable attribute with it, so the
   * panel reads as frozen rather than merely swallowing keys.
   */
  private editableExtensions(): Extension[] {
    return [EditorState.readOnly.of(this.busy), EditorView.editable.of(!this.busy)];
  }

  /**
   * Freeze or release the whole panel while a save or load is in flight.
   *
   * The class greys the panel and turns clicks away; the editors' editable
   * facets stop typing; the focus leaves whatever the writer was typing into,
   * so a keystroke held over the change cannot land once the save completes.
   */
  private setBusy(next: boolean): void {
    if (next === this.busy) {
      return;
    }
    this.busy = next;
    this.element.classList.toggle("is-busy", next);
    this.view.dispatch({ effects: this.readOnlyCompartment.reconfigure(this.editableExtensions()) });
    this.wysiwyg.setEditable(!next);
    if (next) {
      (document.activeElement as HTMLElement | null)?.blur?.();
    }
  }

  async load(chapterId: string): Promise<void> {
    this.setBusy(true);
    try {
      const response = await this.api.getChapterDocument(chapterId);
      this.chapterId = chapterId;
      this.lastCanonicalText = response.content;
      this.replaceDoc(response.content);
      this.notifyDirty();
      this.updateHeader();
      this.onSelectionChange?.();
      for (const warning of response.warnings ?? []) {
        this.onWarning?.(warning);
      }
    } catch (error) {
      reportError("Load chapter", error, this.onMessage);
    } finally {
      this.setBusy(false);
    }
  }

  async save(): Promise<DocumentContentResponse | null> {
    if (this.chapterId === null) {
      return null;
    }
    this.setBusy(true);
    try {
      const response = await this.api.saveChapterDocument(this.chapterId, this.content());
      this.lastCanonicalText = response.content;
      this.replaceDoc(response.content);
      this.notifyDirty();
      this.updateHeader();
      this.onMessage?.(saveMessage(response));
      for (const warning of response.warnings ?? []) {
        this.onWarning?.(warning);
      }
      return response;
    } catch (error) {
      reportError("Save chapter", error, this.onMessage);
      return null;
    } finally {
      this.setBusy(false);
    }
  }

  private replaceDoc(text: string): void {
    this.wysiwyg.setContent(text);
    this.view.dispatch({
      changes: { from: 0, to: this.view.state.doc.length, insert: text },
    });
    this.clearRawProofreadingDiagnostics();
    this.onEditActivity?.();
  }

  private applyMode(): void {
    const raw = this.mode === "raw";
    this.rawHost.hidden = !raw;
    this.wysiwygHost.hidden = raw;
    // The raw view shows the front matter itself; the header would say it twice.
    this.header.hidden = raw;
    this.element.dataset.mode = this.mode;
  }

  /**
   * The un-editable identity line above the text: a character's name parts, or
   * the manuscript chapter's title and its point of view.
   */
  private updateHeader(): void {
    if (this.lastCanonicalText === null) {
      this.header.textContent = "";
      return;
    }
    const fields = frontMatterFields(this.lastCanonicalText);
    this.header.textContent =
      fields.category === "Character" ? characterHeaderText(fields) : manuscriptHeaderText(fields);
  }

  /**
   * Rewrite the buffer's pov line in place after a POV set or clear elsewhere.
   *
   * The open buffer's front matter would otherwise go stale — and its next
   * save, carrying no pov, would clear what the modal just set. Both the
   * buffer and the clean baseline learn the new line, so the save sends it.
   */
  refreshPovLine(povTitle: string | null): void {
    const rewrite = (text: string | null): string | null => {
      if (text === null) {
        return null;
      }
      if (!text.startsWith("---")) {
        return text;
      }
      const lines = text.split("\n");
      const closing = lines.findIndex((line, index) => index > 0 && line.startsWith("---"));
      if (closing === -1) {
        return text;
      }
      const kept = lines.filter((line, index) => index === 0 || index >= closing || !line.startsWith("pov:"));
      if (povTitle) {
        const bodyLines = lines.length - closing;
        kept.splice(kept.length - bodyLines, 0, `pov: ${povTitle}`);
      }
      return kept.join("\n");
    };
    this.lastCanonicalText = rewrite(this.lastCanonicalText);
    this.replaceDoc(this.lastCanonicalText ?? "");
    this.updateHeader();
    this.notifyDirty();
  }
}

function lintSeverity(severity: string): "error" | "warning" | "info" | "hint" {
  if (severity === "error") {
    return "error";
  }
  if (severity === "info") {
    return "info";
  }
  if (severity === "hint") {
    return "hint";
  }
  return "warning";
}

function saveMessage(response: DocumentContentResponse): string {
  const summary = response.summary;
  if (!summary) {
    return "Saved.";
  }
  const parts: string[] = [];
  if (summary.changed > 0) {
    parts.push(`${summary.changed} changed`);
  }
  if (summary.added > 0) {
    parts.push(`${summary.added} added`);
  }
  if (summary.deleted > 0) {
    parts.push(`${summary.deleted} deleted`);
  }
  const detail = parts.length > 0 ? parts.join(", ") : "no changes";
  return `Saved. ${detail}.`;
}