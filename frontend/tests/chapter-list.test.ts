import { afterEach, describe, expect, it, vi } from "vitest";

import type { ChapterListRow } from "../src/renderer/api/types";
import { ChapterList, actHeaderLabel, groupByAct } from "../src/renderer/layout/chapterList";

function chapters(...rows: Array<[id: string, title: string, act: string]>): ChapterListRow[] {
  return rows.map(([id, title, act], index) => ({ id, title, act, index }));
}

afterEach(() => {
  document.body.replaceChildren();
  vi.restoreAllMocks();
});

describe("groupByAct", () => {
  it("groups contiguous chapters in act runs, preserving order", () => {
    const runs = groupByAct(chapters(["a", "A", "I"], ["b", "B", "I"], ["c", "C", "II"]));
    expect(runs.map((r) => r.act)).toEqual(["I", "II"]);
    expect(runs[0].chapters.map((c) => c.id)).toEqual(["a", "b"]);
    expect(runs[1].chapters.map((c) => c.id)).toEqual(["c"]);
  });

  it("re-opens a run when the act changes and comes back", () => {
    const runs = groupByAct(chapters(["a", "A", "I"], ["b", "B", "II"], ["c", "C", "I"]));
    expect(runs.map((r) => r.act)).toEqual(["I", "II", "I"]);
  });

  it("labels an empty act as no act", () => {
    expect(actHeaderLabel("")).toBe("No act");
    expect(actHeaderLabel("Act I")).toBe("Act I");
  });
});

describe("ChapterList", () => {
  it("renders act headers and chapter rows", () => {
    const list = new ChapterList();
    list.setChapters(chapters(["a", "A", "I"], ["b", "B", "I"], ["c", "C", "II"]));
    document.body.append(list.element);

    const headers = Array.from(list.element.querySelectorAll("[data-testid='act-header']"));
    expect(headers.map((h) => h.textContent)).toEqual(["I", "II"]);
    const rows = Array.from(list.element.querySelectorAll("[data-testid='chapter-row']"));
    expect(rows.map((r) => r.textContent)).toEqual(["A", "B", "C"]);
  });

  it("collapses an act run on header click", () => {
    const list = new ChapterList();
    list.setChapters(chapters(["a", "A", "I"], ["b", "B", "I"]));
    document.body.append(list.element);

    const section = list.element.querySelector<HTMLElement>(".act-run")!;
    expect(section.classList.contains("is-collapsed")).toBe(false);
    list.element.querySelector<HTMLElement>("[data-testid='act-header']")!.click();
    expect(section.classList.contains("is-collapsed")).toBe(true);
  });

  it("reports selection on row click and highlights the row", () => {
    const onSelect = vi.fn();
    const list = new ChapterList({ onSelect });
    list.setChapters(chapters(["a", "A", "I"], ["b", "B", "I"]));
    document.body.append(list.element);

    const rows = list.element.querySelectorAll("[data-testid='chapter-row']");
    (rows[0] as HTMLElement).click();
    expect(onSelect).toHaveBeenCalledWith("a");
    expect(list.element.querySelector("[data-chapter-id='a']")!.classList.contains("is-selected")).toBe(true);
    expect(list.element.querySelector("[data-chapter-id='b']")!.classList.contains("is-selected")).toBe(false);
  });

  it("select() highlights a row without reporting", () => {
    const onSelect = vi.fn();
    const list = new ChapterList({ onSelect });
    list.setChapters(chapters(["a", "A", "I"]));
    document.body.append(list.element);

    list.select("a");
    expect(onSelect).not.toHaveBeenCalled();
    expect(list.element.querySelector("[data-chapter-id='a']")!.classList.contains("is-selected")).toBe(true);
  });

  it("emits the context-menu signal with coordinates on right-click", () => {
    const onContext = vi.fn();
    const list = new ChapterList({ onContext });
    list.setChapters(chapters(["a", "A", "I"]));
    document.body.append(list.element);

    const row = list.element.querySelector("[data-testid='chapter-row']")!;
    const event = new MouseEvent("contextmenu", { bubbles: true, clientX: 12, clientY: 34 });
    row.dispatchEvent(event);

    expect(onContext).toHaveBeenCalledTimes(1);
    expect(onContext).toHaveBeenCalledWith("a", expect.any(MouseEvent));
    expect((onContext.mock.calls[0][1] as MouseEvent).clientX).toBe(12);
  });

  it("setChapters replaces the previous list", () => {
    const list = new ChapterList();
    list.setChapters(chapters(["a", "A", "I"]));
    list.setChapters(chapters(["b", "B", "II"]));
    document.body.append(list.element);

    const rows = list.element.querySelectorAll("[data-testid='chapter-row']");
    expect(rows).toHaveLength(1);
    expect(rows[0].textContent).toBe("B");
  });
});