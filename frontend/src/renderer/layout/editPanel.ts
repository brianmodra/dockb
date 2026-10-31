import { EditorState, Compartment, type Extension } from "@codemirror/state";
import { EditorView, lineNumbers, keymap } from "@codemirror/view";
import { defaultKeymap, history, historyKeymap } from "@codemirror/commands";
import { markdown } from "@codemirror/lang-markdown";
import { syntaxHighlighting, defaultHighlightStyle, indentOnInput } from "@codemirror/language";
import type { ApiClient } from "../api/client";
import type { DocumentContentResponse } from "../api/types";
import { reportError } from "../log";
import { WysiwygView, chapterBody } from "./wysiwyg";
import type { Mode } from "./menubar";

export type EditPanelApi = Pick<ApiClient, "getChapterDocument" | "saveChapterDocument">;

export interface EditPanelOptions {
  api: EditPanelApi;
  onMessage?: (text: string) => void;
  onDirtyChange?: (dirty: boolean) => void;
}

export class EditPanel {
  readonly element: HTMLElement;

  api: EditPanelApi;
  onMessage?: (text: string) => void;
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

  constructor(options: EditPanelOptions) {
    this.api = options.api;
    this.onMessage = options.onMessage;
    this.onDirtyChange = options.onDirtyChange;

    this.element = document.createElement("div");
    this.element.className = "edit-panel";
    this.element.dataset.testid = "edit-panel";

    this.rawHost = document.createElement("div");
    this.rawHost.dataset.testid = "edit-raw";
    this.wysiwygHost = document.createElement("div");
    this.wysiwygHost.dataset.testid = "edit-wysiwyg";
    this.element.append(this.rawHost, this.wysiwygHost);

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
    this.applyMode();
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
      : this.wysiwyg.plainContent() !== chapterBody(this.lastCanonicalText);
  }

  lastCanonical(): string | null {
    return this.lastCanonicalText;
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
      this.onMessage?.(saveMessage(response));
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
    this.element.dataset.mode = this.mode;
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