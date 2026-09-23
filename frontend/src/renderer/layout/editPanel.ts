import { EditorState } from "@codemirror/state";
import { EditorView, lineNumbers, keymap } from "@codemirror/view";
import { defaultKeymap, history, historyKeymap } from "@codemirror/commands";
import { markdown } from "@codemirror/lang-markdown";
import { syntaxHighlighting, defaultHighlightStyle, indentOnInput } from "@codemirror/language";
import type { ApiClient } from "../api/client";
import type { DocumentContentResponse } from "../api/types";
import { reportError } from "../log";
import { WysiwygView } from "./wysiwyg";
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
    const text = this.content();
    this.mode = mode;
    this.applyMode();
    this.replaceDoc(text);
  }

  async load(chapterId: string): Promise<void> {
    try {
      const response = await this.api.getChapterDocument(chapterId);
      this.chapterId = chapterId;
      this.lastCanonicalText = response.content;
      this.replaceDoc(response.content);
      this.notifyDirty();
    } catch (error) {
      reportError("Load chapter", error, this.onMessage);
    }
  }

  setContent(text: string): void {
    this.replaceDoc(text);
  }

  content(): string {
    return this.mode === "raw" ? this.view.state.doc.toString() : this.wysiwyg.content();
  }

  isDirty(): boolean {
    if (this.lastCanonicalText === null) {
      return false;
    }
    return this.content() !== this.lastCanonicalText;
  }

  lastCanonical(): string | null {
    return this.lastCanonicalText;
  }

  private notifyDirty(): void {
    const dirty = this.isDirty();
    if (dirty === this.lastDirty) {
      return;
    }
    this.lastDirty = dirty;
    this.onDirtyChange?.(dirty);
  }

  async save(): Promise<DocumentContentResponse | null> {
    if (this.chapterId === null) {
      return null;
    }
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