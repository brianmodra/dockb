import type { ChapterListRow } from "../api/types";

export interface RowMetrics {
  top: number;
  bottom: number;
}

export interface MoveModeOptions {
  chapterId: string;
  chapters: ChapterListRow[];
  listElement: HTMLElement;
  onCommit: (afterChapterId: string | null) => void;
  onCancel?: () => void;
}

const SCROLL_MARGIN = 20;
const SCROLL_STEP = 12;

export class MoveMode {
  private readonly chapterId: string;
  private readonly chapters: ChapterListRow[];
  private readonly listElement: HTMLElement;
  private readonly onCommit: (afterChapterId: string | null) => void;
  private readonly onCancel?: () => void;
  private readonly bar: HTMLElement;
  private active = true;
  private currentY: number | null = null;
  private readonly rope: AbortController;

  constructor(options: MoveModeOptions) {
    this.chapterId = options.chapterId;
    this.chapters = options.chapters;
    this.listElement = options.listElement;
    this.onCommit = options.onCommit;
    this.onCancel = options.onCancel;

    this.listElement.classList.add("is-moving");
    this.bar = document.createElement("div");
    this.bar.dataset.testid = "move-bar";
    this.bar.className = "move-bar";
    this.listElement.append(this.bar);

    this.rope = new AbortController();
    const signal = this.rope.signal;

    document.addEventListener("mousemove", this.onMouseMove, { signal });
    document.addEventListener("click", this.onCommitClick, { signal });
    window.addEventListener("keydown", this.onKeydown, { signal });
    document.addEventListener("mousedown", this.onBackgroundDown, { signal });
  }

  private readonly onMouseMove = (event: MouseEvent): void => {
    if (!this.active) {
      return;
    }
    this.currentY = event.clientY;
    this.placeBar();
    this.maybeScroll(event.clientY);
  };

  private readonly onCommitClick = (event: MouseEvent): void => {
    if (!this.active || event.target && !this.listElement.contains(event.target as Node)) {
      return;
    }
    if (event.target === this.bar) {
      return;
    }
    const y = this.currentY;
    if (y === null) {
      return;
    }
    const metrics = this.rowMetrics();
    const { afterChapterId } = computeAfterForY(this.chapters, y, metrics);
    if (afterChapterId === null && this.chapters[0]?.id === this.chapterId) {
      return; // already first
    }
    if (afterChapterId === this.chapterId) {
      return; // would move after itself
    }
    this.close();
    this.onCommit(afterChapterId);
  };

  cancel(): void {
    this.close();
    this.onCancel?.();
  }

  private readonly onKeydown = (event: KeyboardEvent): void => {
    if (event.key !== "Escape") {
      return;
    }
    this.cancel();
  };

  private readonly onBackgroundDown = (event: MouseEvent): void => {
    if (!this.listElement.contains(event.target as Node)) {
      this.cancel();
    }
  };

  private placeBar(): void {
    if (this.currentY === null) {
      return;
    }
    const metrics = this.rowMetrics();
    const { afterChapterId } = computeAfterForY(this.chapters, this.currentY, metrics);
    let top = 0;
    if (afterChapterId !== null) {
      const index = this.chapters.findIndex((c) => c.id === afterChapterId);
      if (index >= 0) {
        top = metrics[index]?.bottom ?? 0;
      }
    }
    this.bar.style.top = `${top}px`;
  }

  private maybeScroll(y: number): void {
    const rect = this.listElement.getBoundingClientRect();
    if (rect.height === 0) {
      return;
    }
    if (y < rect.top + SCROLL_MARGIN) {
      this.listElement.scrollTop -= SCROLL_STEP;
      this.placeBar();
    } else if (y > rect.bottom - SCROLL_MARGIN) {
      this.listElement.scrollTop += SCROLL_STEP;
      this.placeBar();
    }
  }

  private rowMetrics(): RowMetrics[] {
    return this.chapters.map((chapter) => {
      const el = this.listElement.querySelector<HTMLElement>(`[data-chapter-id="${chapter.id}"]`);
      const rect = el?.getBoundingClientRect();
      if (!rect) {
        return { top: 0, bottom: 0 };
      }
      return { top: rect.top, bottom: rect.bottom };
    });
  }

  private close(): void {
    if (!this.active) {
      return;
    }
    this.active = false;
    this.listElement.classList.remove("is-moving");
    this.bar.remove();
    this.rope.abort();
  }
}

export function computeAfterForY(
  chapters: ChapterListRow[],
  y: number,
  rowMetrics: RowMetrics[],
): { afterChapterId: string | null } {
  // Each chapter owns the zone around its row's vertical midpoint; the slot
  // below that chapter is the drop target. Above the first midpoint the target
  // is the list top (null = first).
  const midpoints = rowMetrics.map((m) => (m.bottom - m.top) / 2 + m.top);
  if (midpoints.length === 0 || y < midpoints[0]) {
    return { afterChapterId: null };
  }
  let nearest = 0;
  let nearestDistance = Number.POSITIVE_INFINITY;
  for (let i = 0; i < midpoints.length; i += 1) {
    const distance = Math.abs(midpoints[i] - y);
    if (distance < nearestDistance) {
      nearest = i;
      nearestDistance = distance;
    }
  }
  return { afterChapterId: chapters[nearest].id };
}