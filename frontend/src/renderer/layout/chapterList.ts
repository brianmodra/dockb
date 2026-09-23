import type { ChapterListRow } from "../api/types";

export interface ActRun {
  act: string;
  chapters: ChapterListRow[];
}

export interface ChapterListOptions {
  onSelect?: (chapterId: string) => void;
  onContext?: (chapterId: string, event: MouseEvent) => void;
}

export class ChapterList {
  readonly element: HTMLElement;

  private rows: ChapterListRow[] = [];
  private readonly onSelect?: (chapterId: string) => void;
  private readonly onContext?: (chapterId: string, event: MouseEvent) => void;

  constructor(options: ChapterListOptions = {}) {
    this.element = document.createElement("div");
    this.element.dataset.testid = "chapter-list";
    this.element.className = "chapter-list";
    this.onSelect = options.onSelect;
    this.onContext = options.onContext;
  }

  setChapters(chapters: ChapterListRow[]): void {
    this.rows = chapters;
    this.element.replaceChildren(
      ...groupByAct(chapters).map((run) => this.renderRun(run)),
    );
  }

  select(chapterId: string | null): void {
    this.setSelection(chapterId);
  }

  chapter(chapterId: string): ChapterListRow | undefined {
    return this.rows.find((row) => row.id === chapterId);
  }

  selectedId(): string | null {
    return (
      this.element.querySelector<HTMLElement>(".chapter-row.is-selected")?.dataset.chapterId ??
      null
    );
  }

  private renderRun(run: ActRun): HTMLElement {
    const section = document.createElement("div");
    section.className = "act-run";
    section.dataset.act = run.act;

    const header = document.createElement("button");
    header.type = "button";
    header.className = "act-header";
    header.dataset.testid = "act-header";
    header.textContent = actHeaderLabel(run.act);

    const body = document.createElement("div");
    body.className = "act-body";
    for (const chapter of run.chapters) {
      body.append(this.renderRow(chapter));
    }

    header.addEventListener("click", () => {
      const collapsed = section.classList.toggle("is-collapsed");
      header.setAttribute("aria-expanded", String(!collapsed));
    });

    section.append(header, body);
    return section;
  }

  private renderRow(chapter: ChapterListRow): HTMLElement {
    const row = document.createElement("div");
    row.className = "chapter-row";
    row.dataset.testid = "chapter-row";
    row.dataset.chapterId = chapter.id;
    row.textContent = chapter.title;

    row.addEventListener("click", () => {
      this.select(chapter.id);
      this.onSelect?.(chapter.id);
    });
    row.addEventListener("contextmenu", (event) => {
      event.preventDefault();
      this.select(chapter.id);
      this.onContext?.(chapter.id, event);
    });

    return row;
  }

  private setSelection(chapterId: string | null): void {
    for (const row of this.element.querySelectorAll(".chapter-row")) {
      row.classList.toggle("is-selected", row.getAttribute("data-chapter-id") === chapterId);
    }
  }
}

export function groupByAct(chapters: ChapterListRow[]): ActRun[] {
  const runs: ActRun[] = [];
  for (const chapter of chapters) {
    const last = runs.at(-1);
    if (last && last.act === chapter.act) {
      last.chapters.push(chapter);
    } else {
      runs.push({ act: chapter.act, chapters: [chapter] });
    }
  }
  return runs;
}

export function actHeaderLabel(act: string): string {
  return act.trim().length > 0 ? act : "No act";
}