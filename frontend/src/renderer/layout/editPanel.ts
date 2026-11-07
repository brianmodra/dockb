import { EditorState, Compartment, type Extension } from "@codemirror/state";
import { EditorView, lineNumbers, keymap } from "@codemirror/view";
import { defaultKeymap, history, historyKeymap } from "@codemirror/commands";
import { markdown } from "@codemirror/lang-markdown";
import { syntaxHighlighting, defaultHighlightStyle, indentOnInput } from "@codemirror/language";
import type { ApiClient } from "../api/client";
import type { DocumentContentResponse } from "../api/types";
import { reportError } from "../log";
import { characterHeaderText, frontMatterFields, manuscriptHeaderText } from "./characterHeader";
import { WysiwygView, chapterBody, quoteSignatureOf, uniformQuoteType } from "./wysiwyg";
import { openContextMenu } from "./contextMenu";
import type { Mode } from "./menubar";

export type EditPanelApi = Pick<ApiClient, "getChapterDocument" | "saveChapterDocument">;

export interface EditPanelOptions {
  api: EditPanelApi;
  onMessage?: (text: string) => void;
  onWarning?: (text: string) => void;
  onDirtyChange?: (dirty: boolean) => void;
}

export class EditPanel {
  readonly element: HTMLElement;

  api: EditPanelApi;
  onMessage?: (text: string) => void;
  onWarning?: (text: string) => void;
  onDirtyChange?: (dirty: boolean) => void;
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

  constructor(options: EditPanelOptions) {
    this.api = options.api;
    this.onMessage = options.onMessage;
    this.onWarning = options.onWarning;
    this.onDirtyChange = options.onDirtyChange;

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
    scroll.append(this.rawHost, this.wysiwygHost);
    this.element.append(this.header, scroll);

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
        }),
      ],
    });
    this.view = new EditorView({ state, parent: this.rawHost });
    this.wysiwyg = new WysiwygView({ onChange: () => this.notifyDirty() });
    this.wysiwygHost.append(this.wysiwyg.element);
    this.wysiwygHost.addEventListener("contextmenu", (event) => this.openParagraphMenu(event));
    this.applyMode();
  }

  /** Right-click inside a paragraph: the Edit ▸ Quote pulldown for the selection's paragraphs. */
  private openParagraphMenu(event: MouseEvent): void {
    event.preventDefault();
    const positions = this.wysiwyg.paragraphPositions(event.target);
    if (positions.length === 0) {
      return;
    }
    const types = positions.map((pos) => this.wysiwyg.quoteTypeAt(pos));
    const uniform = uniformQuoteType(types);
    const setQuote = (quoteType: string): void => {
      this.wysiwyg.setQuoteTypeAtPositions(positions, quoteType);
    };
    openContextMenu(
      event.clientX,
      event.clientY,
      [
        {
          label: "Quote",
          children: [
            { label: "None", checked: uniform === "", onSelect: () => setQuote("") },
            { label: "Reading", checked: uniform === "reading", onSelect: () => setQuote("reading") },
            { label: "Writing", checked: uniform === "writing", onSelect: () => setQuote("writing") },
          ],
        },
      ],
      { title: "Edit" },
    );
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
   * Select one sentence of a paragraph as the WYSIWYG view shows it, so a
   * reply's highlight button can point the writer at it. The raw view has no
   * sentences (the canonical file is its content), so there it answers false.
   */
  selectSentence(paragraphId: string, sentenceIndex: number | null): boolean {
    return this.mode === "wysiwyg" && this.wysiwyg.selectSentence(paragraphId, sentenceIndex);
  }

  getLanguage(): string {
    return this.wysiwyg.getLanguage();
  }

  setLanguage(lang: string): void {
    this.wysiwyg.setLanguage(lang);
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