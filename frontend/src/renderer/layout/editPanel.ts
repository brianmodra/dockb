import { EditorState } from "@codemirror/state";
import { EditorView, lineNumbers, keymap } from "@codemirror/view";
import { defaultKeymap, history, historyKeymap } from "@codemirror/commands";
import { markdown } from "@codemirror/lang-markdown";
import { syntaxHighlighting, defaultHighlightStyle, indentOnInput } from "@codemirror/language";
import type { ApiClient } from "../api/client";
import type { DocumentContentResponse } from "../api/types";
import { reportError } from "../log";

export type EditPanelApi = Pick<ApiClient, "getChapterDocument" | "saveChapterDocument">;

export interface EditPanelOptions {
  api: EditPanelApi;
  onMessage?: (text: string) => void;
}

export class EditPanel {
  readonly element: HTMLElement;

  api: EditPanelApi;
  onMessage?: (text: string) => void;
  private view: EditorView;
  private chapterId: string | null = null;
  private lastCanonicalText: string | null = null;

  constructor(options: EditPanelOptions) {
    this.api = options.api;
    this.onMessage = options.onMessage;
    this.element = document.createElement("div");
    this.element.className = "edit-panel";
    this.element.dataset.testid = "edit-panel";

    const state = EditorState.create({
      doc: "",
      extensions: [
        lineNumbers(),
        history(),
        keymap.of([...defaultKeymap, ...historyKeymap]),
        indentOnInput(),
        syntaxHighlighting(defaultHighlightStyle, { fallback: true }),
        markdown(),
      ],
    });
    this.view = new EditorView({ state, parent: this.element });
  }

  async load(chapterId: string): Promise<void> {
    try {
      const response = await this.api.getChapterDocument(chapterId);
      this.chapterId = chapterId;
      this.lastCanonicalText = response.content;
      this.replaceDoc(response.content);
    } catch (error) {
      reportError("Load chapter", error, this.onMessage);
    }
  }

  setContent(text: string): void {
    this.replaceDoc(text);
  }

  content(): string {
    return this.view.state.doc.toString();
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

  async save(): Promise<DocumentContentResponse | null> {
    if (this.chapterId === null) {
      return null;
    }
    try {
      const response = await this.api.saveChapterDocument(this.chapterId, this.content());
      this.lastCanonicalText = response.content;
      this.replaceDoc(response.content);
      this.onMessage?.(saveMessage(response));
      return response;
    } catch (error) {
      reportError("Save chapter", error, this.onMessage);
      return null;
    }
  }

  private replaceDoc(text: string): void {
    this.view.dispatch({
      changes: { from: 0, to: this.view.state.doc.length, insert: text },
    });
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