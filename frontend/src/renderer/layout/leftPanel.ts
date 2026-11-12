import type { ChapterListRow } from "../api/types";
import { ChapterList, orderedForDisplay } from "./chapterList";
import { openContextMenu } from "./contextMenu";
import { confirmCheckboxModal, confirmModal, povModal, promptModal } from "./modals";
import { MoveMode } from "./moveMode";
import { reportError } from "../log";
import type { ApiClient } from "../api/client";

export type LeftPanelApi = Pick<
  ApiClient,
  "listChapters" | "updateChapter" | "deleteChapter" | "reorderChapter" | "renumberChapters" | "setPov"
>;

export interface LeftPanelOptions {
  api: LeftPanelApi;
  onEdit?: (chapterId: string) => void;
  onMessage?: (text: string) => void;
  onPovChanged?: (chapterId: string, povTitle: string | null) => void;
}

export class LeftPanel {
  readonly element: HTMLElement;

  private api: LeftPanelApi;
  private onEdit?: (chapterId: string) => void;
  private onMessage?: (text: string) => void;
  private onPovChanged?: (chapterId: string, povTitle: string | null) => void;
  private documentId: string | null = null;
  private chapters: ChapterListRow[] = [];
  private chapterList: ChapterList;
  private moveMode: MoveMode | null = null;

  constructor(options: LeftPanelOptions) {
    this.api = options.api;
    this.onEdit = options.onEdit;
    this.onMessage = options.onMessage;
    this.onPovChanged = options.onPovChanged;
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

  /**
   * Load a document's chapters, keeping the selected chapter selected when it
   * is still in the list: reloading the same document after a rename, move,
   * renumber, or POV change must not drop the row the writer is editing, while
   * another document's rows — or a deleted chapter — leave nothing selected.
   */
  async load(documentId: string): Promise<void> {
    try {
      const selectedId = this.chapterList.selectedId();
      this.documentId = documentId;
      this.chapters = await this.api.listChapters(documentId);
      this.chapterList.setChapters(this.chapters);
      this.chapterList.select(selectedId);
    } catch (error) {
      reportError("Load chapters", error, this.onMessage);
    }
  }

  select(chapterId: string | null): void {
    this.chapterList.select(chapterId);
  }

  currentDocumentId(): string | null {
    return this.documentId;
  }

  selectedChapter(): ChapterListRow | null {
    const chapterId = this.chapterList.selectedId();
    return chapterId === null ? null : this.chapterList.chapter(chapterId) ?? null;
  }

  /** The title of *chapterId*, or null when it is not in the loaded list. */
  titleOf(chapterId: string): string | null {
    return this.chapterList.chapter(chapterId)?.title ?? null;
  }

  async reload(): Promise<void> {
    if (this.documentId !== null) {
      await this.load(this.documentId);
    }
  }

  clear(): void {
    this.documentId = null;
    this.chapters = [];
    this.chapterList.setChapters([]);
    this.chapterList.select(null);
  }

  private handleContext(chapterId: string, event: MouseEvent): void {
    const chapter = this.chapterList.chapter(chapterId);
    if (!chapter) {
      return;
    }
    const items = [
      { label: "Edit", onSelect: () => this.onEdit?.(chapterId) },
      { label: "Rename", onSelect: () => void this.rename(chapterId, chapter.title) },
    ];
    if (chapter.category === "Character") {
      // A character is neither moved within the manuscript nor numbered.
      items.push({ label: "Delete", onSelect: () => void this.delete(chapterId, chapter.title) });
    } else {
      items.push(
        { label: "Move", onSelect: () => this.startMove(chapterId) },
        { label: "Renumber", onSelect: () => void this.renumberAll() },
        { label: "POV", onSelect: () => void this.pov(chapterId) },
        { label: "Delete", onSelect: () => void this.delete(chapterId, chapter.title) },
      );
    }
    openContextMenu(event.clientX, event.clientY, items);
  }

  /** Ask for a POV character by name until one applies, is cleared, or is cancelled. */
  private async pov(chapterId: string): Promise<void> {
    if (!this.documentId) {
      return;
    }
    let initial = this.chapterList.chapter(chapterId)?.pov ?? "";
    let warning: string | undefined;
    for (;;) {
      const { value, input } = await povModal({
        title: "POV character",
        label: "Character name",
        initial,
        confirmLabel: "Set POV",
        warning,
      });
      if (value !== "confirm") {
        return;
      }
      const response = await this.api.setPov(chapterId, input);
      if (response.applied) {
        this.onMessage?.(response.pov ? `POV set to "${response.pov.title}".` : "POV cleared.");
        this.onPovChanged?.(chapterId, response.pov?.title ?? null);
        await this.load(this.documentId);
        return;
      }
      initial = response.suggestion ?? input;
      warning = response.warning ?? "No matching character chapter";
    }
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

  private async renumberAll(): Promise<void> {
    if (!this.documentId) {
      return;
    }
    const { confirmed, checked } = await confirmCheckboxModal({
      title: "Renumber chapters",
      message: "Renumber all chapters in their current order?",
      checkboxLabel: " Start from 0",
      checkboxTestId: "renumber-start-zero",
      confirmLabel: "Renumber",
    });
    if (!confirmed) {
      return;
    }
    try {
      const response = await this.api.renumberChapters(this.documentId, { start: checked ? 0 : 1 });
      const count = response.renames.length;
      this.onMessage?.(
        count === 0 ? "No chapters needed renumbering." : `Renumbered ${count} chapter${count === 1 ? "" : "s"}.`,
      );
      await this.load(this.documentId);
    } catch (error) {
      reportError("Renumber", error, this.onMessage);
    }
  }

  private startMove(chapterId: string): void {
    this.moveMode?.cancel();
    this.moveMode = new MoveMode({
      chapterId,
      chapters: orderedForDisplay(this.chapters),
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