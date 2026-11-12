import MarkdownIt from "markdown-it";
import type { DocumentContentResponse } from "../api/types";
import { chapterParagraphs } from "./wysiwyg";

export interface RightPanelApi {
  getChapterDocument(
    chapterId: string,
    options?: { readonly?: boolean },
  ): Promise<DocumentContentResponse>;
}

export interface RightPanelOptions {
  api: RightPanelApi;
  onMessage?: (text: string) => void;
}

/** A chapter on the shelf: its id and the title its tab shows. */
export interface ShelfChapter {
  chapterId: string;
  title: string;
}

const MAX_TAB_LABEL = 12;

function tabLabel(title: string): string {
  return title.length <= MAX_TAB_LABEL ? title : `${title.slice(0, 9)}…`;
}

/**
 * The right panel: a strip of chapter tabs over one read-only chapter.
 *
 * Writer-added chapters (kept until closed, with an `×`) sit left of the
 * automatic character chapters, which the caller replaces as the cursor moves.
 * Clicking a tab opens it; the opened chapter is fetched read-only and rendered
 * from its markdown (span markup stripped).
 */
export class RightPanel {
  readonly element: HTMLElement;

  private readonly api: RightPanelApi;
  private readonly onMessage?: (text: string) => void;
  private readonly tabs: HTMLElement;
  private readonly content: HTMLElement;
  private writerChapters: ShelfChapter[] = [];
  private characterChapters: ShelfChapter[] = [];
  private openId: string | null = null;

  constructor(options: RightPanelOptions) {
    this.api = options.api;
    this.onMessage = options.onMessage;
    this.element = document.createElement("div");
    this.element.className = "right-panel";
    this.element.dataset.testid = "right-panel";

    this.tabs = document.createElement("div");
    this.tabs.className = "right-tabs";
    this.tabs.dataset.testid = "right-tabs";

    this.content = document.createElement("div");
    this.content.className = "right-content";
    this.content.dataset.testid = "right-content";

    this.element.append(this.tabs, this.content);
  }

  /** Add a writer chapter to the shelf (idempotent) and open it. */
  addWriterChapter(chapterId: string, title: string): void {
    if (!this.writerChapters.some((chapter) => chapter.chapterId === chapterId)) {
      this.writerChapters.push({ chapterId, title });
    }
    this.open(chapterId);
  }

  /** Add a writer chapter (idempotent), open it, and scroll a paragraph into view. */
  addWriterChapterAt(chapterId: string, title: string, paragraphId: string): void {
    if (!this.writerChapters.some((chapter) => chapter.chapterId === chapterId)) {
      this.writerChapters.push({ chapterId, title });
    }
    this.open(chapterId, paragraphId);
  }

  /** Close a writer chapter's tab; its content clears if it was open. */
  closeWriterChapter(chapterId: string): void {
    this.writerChapters = this.writerChapters.filter((chapter) => chapter.chapterId !== chapterId);
    if (this.openId === chapterId) {
      this.openId = null;
      this.clearContent();
    }
    this.renderTabs();
  }

  /** Replace the automatic character chapters (the current paragraph's mentions). */
  setCharacterChapters(chapters: ShelfChapter[]): void {
    this.characterChapters = chapters;
    if (
      this.openId !== null &&
      this.characterChapters.every((chapter) => chapter.chapterId !== this.openId) &&
      this.writerChapters.every((chapter) => chapter.chapterId !== this.openId)
    ) {
      this.openId = null;
      this.clearContent();
    }
    this.renderTabs();
  }

  private open(chapterId: string, paragraphId: string | null = null): void {
    this.openId = chapterId;
    this.renderTabs();
    void this.load(chapterId, paragraphId);
  }

  private async load(chapterId: string, paragraphId: string | null): Promise<void> {
    try {
      const doc = await this.api.getChapterDocument(chapterId, { readonly: true });
      if (this.openId !== chapterId) {
        return;
      }
      this.renderContent(doc.content);
      if (paragraphId !== null) {
        this.content
          .querySelector<HTMLElement>(`[data-par-id="${paragraphId}"]`)
          ?.scrollIntoView();
      }
    } catch (error) {
      this.onMessage?.(`Could not show the chapter: ${errorMessage(error)}`);
    }
  }

  private renderContent(markdown: string): void {
    this.content.replaceChildren();
    for (const paragraph of chapterParagraphs(markdown)) {
      const wrapper = document.createElement("div");
      if (paragraph.id !== null) {
        wrapper.dataset.parId = paragraph.id;
      }
      wrapper.innerHTML = new MarkdownIt().render(paragraph.text);
      this.content.append(wrapper);
    }
  }

  private clearContent(): void {
    this.content.replaceChildren();
  }

  private renderTabs(): void {
    this.tabs.replaceChildren();
    for (const chapter of this.writerChapters) {
      this.tabs.append(this.tabElement(chapter, true));
    }
    for (const chapter of this.characterChapters) {
      this.tabs.append(this.tabElement(chapter, false));
    }
  }

  private tabElement(chapter: ShelfChapter, closable: boolean): HTMLElement {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "right-tab";
    button.dataset.testid = "right-tab";
    if (chapter.chapterId === this.openId) {
      button.classList.add("is-open");
    }
    button.textContent = tabLabel(chapter.title);
    button.addEventListener("click", () => this.open(chapter.chapterId));
    if (closable) {
      const close = document.createElement("button");
      close.type = "button";
      close.className = "right-tab-close";
      close.dataset.testid = "right-tab-close";
      close.textContent = "×";
      close.addEventListener("click", (event) => {
        event.stopPropagation();
        this.closeWriterChapter(chapter.chapterId);
      });
      button.append(close);
    }
    return button;
  }
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}
