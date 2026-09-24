import type { ChapterListRow } from "../api/types";
import { ChapterList } from "./chapterList";
import { openContextMenu } from "./contextMenu";
import { confirmModal, promptModal } from "./modals";
import { MoveMode } from "./moveMode";
import { reportError } from "../log";
import type { ApiClient } from "../api/client";

export type LeftPanelApi = Pick<
  ApiClient,
  "listChapters" | "updateChapter" | "deleteChapter" | "reorderChapter"
>;

export interface LeftPanelOptions {
  api: LeftPanelApi;
  onEdit?: (chapterId: string) => void;
  onMessage?: (text: string) => void;
}

export class LeftPanel {
  readonly element: HTMLElement;

  private api: LeftPanelApi;
  private onEdit?: (chapterId: string) => void;
  private onMessage?: (text: string) => void;
  private documentId: string | null = null;
  private chapters: ChapterListRow[] = [];
  private chapterList: ChapterList;
  private moveMode: MoveMode | null = null;

  constructor(options: LeftPanelOptions) {
    this.api = options.api;
    this.onEdit = options.onEdit;
    this.onMessage = options.onMessage;
    this.element = document.createElement("div");
    this.element.className = "left-panel";

    this.chapterList = new ChapterList({
      onSelect: (chapterId) => {
        this.select(chapterId);
        this.onEdit?.(chapterId);
      },
      onContext: (chapterId, event) => this.handleContext(chapterId, event),
    });
    this.element.append(this.chapterList.element);
  }

  async load(documentId: string): Promise<void> {
    try {
      this.documentId = documentId;
      this.chapters = await this.api.listChapters(documentId);
      this.chapterList.setChapters(this.chapters);
    } catch (error) {
      reportError("Load chapters", error, this.onMessage);
    }
  }

  select(chapterId: string | null): void {
    this.chapterList.select(chapterId);
  }

  private handleContext(chapterId: string, event: MouseEvent): void {
    const chapter = this.chapterList.chapter(chapterId);
    if (!chapter) {
      return;
    }
    openContextMenu(event.clientX, event.clientY, [
      { label: "Edit", onSelect: () => this.onEdit?.(chapterId) },
      { label: "Rename", onSelect: () => void this.rename(chapterId, chapter.title) },
      { label: "Move", onSelect: () => this.startMove(chapterId) },
      { label: "Delete", onSelect: () => void this.delete(chapterId, chapter.title) },
    ]);
  }

  private async rename(chapterId: string, currentTitle: string): Promise<void> {
    const { value, input } = await promptModal({
      title: "Rename chapter",
      label: "New name",
      initial: currentTitle,
      confirmLabel: "Rename",
    });
    if (value !== "confirm" || !this.documentId) {
      return;
    }
    try {
      await this.api.updateChapter(chapterId, { title: input });
      await this.load(this.documentId);
    } catch (error) {
      reportError("Rename chapter", error, this.onMessage);
    }
  }

  private async delete(chapterId: string, title: string): Promise<void> {
    const confirmed = await confirmModal({
      title: "Delete chapter",
      message: `Are you sure you want to delete "${title}"?`,
      confirmLabel: "Delete",
    });
    if (!confirmed || !this.documentId) {
      return;
    }
    try {
      await this.api.deleteChapter(chapterId);
      await this.load(this.documentId);
    } catch (error) {
      reportError("Delete chapter", error, this.onMessage);
    }
  }

  private startMove(chapterId: string): void {
    this.moveMode?.cancel();
    this.moveMode = new MoveMode({
      chapterId,
      chapters: this.chapters,
      listElement: this.chapterList.element,
      onCommit: (afterChapterId) => {
        void this.commitMove(chapterId, afterChapterId);
      },
      onCancel: () => {
        this.moveMode = null;
      },
    });
  }

  private async commitMove(chapterId: string, afterChapterId: string | null): Promise<void> {
    this.moveMode = null;
    if (!this.documentId) {
      return;
    }
    try {
      const response = await this.api.reorderChapter(chapterId, afterChapterId);
      this.onMessage?.(response.status.message);
      await this.load(this.documentId);
    } catch (error) {
      reportError("Move chapter", error, this.onMessage);
    }
  }
}