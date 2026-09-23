import { afterEach, describe, expect, it, vi } from "vitest";
import type { ChapterListRow } from "../src/renderer/api/types";
import { MoveMode, computeAfterForY } from "../src/renderer/layout/moveMode";

function chapters(...rows: Array<[id: string, title: string, act: string]>): ChapterListRow[] {
  return rows.map(([id, title, act], index) => ({ id, title, act, index }));
}

const METRICS = [
  { top: 0, bottom: 20 }, // a
  { top: 20, bottom: 40 }, // b
  { top: 40, bottom: 60 }, // c
];

function stubRect(el: HTMLElement, top: number, bottom: number): void {
  el.getBoundingClientRect = () =>
    ({ top, bottom, left: 0, right: 200, width: 200, height: bottom - top }) as DOMRect;
}

function buildList(): HTMLElement {
  const list = document.createElement("div");
  list.dataset.testid = "chapter-list";
  list.style.position = "relative";
  const rows = chapters(["a", "A", "I"], ["b", "B", "I"], ["c", "C", "II"]);
  for (const [i, row] of rows.entries()) {
    const el = document.createElement("div");
    el.dataset.chapterId = row.id;
    el.textContent = row.title;
    stubRect(el, METRICS[i].top, METRICS[i].bottom);
    list.append(el);
  }
  stubRect(list, 0, 60);
  return list;
}

afterEach(() => {
  document.body.replaceChildren();
  vi.restoreAllMocks();
});

describe("computeAfterForY", () => {
  it("maps a point above the first row to after null", () => {
    expect(computeAfterForY(chapters(["a", "A", "I"], ["b", "B", "I"]), 5, METRICS.slice(0, 2))).toEqual({
      afterChapterId: null,
    });
  });

  it("maps a point nearest a row to the slot right below it", () => {
    expect(
      computeAfterForY(chapters(["a", "A", "I"], ["b", "B", "I"], ["c", "C", "II"]), 25, METRICS),
    ).toEqual({ afterChapterId: "b" });
  });

  it("maps a point below the last row to after the last chapter", () => {
    expect(
      computeAfterForY(chapters(["a", "A", "I"], ["b", "B", "I"], ["c", "C", "II"]), 75, METRICS),
    ).toEqual({ afterChapterId: "c" });
  });
});

describe("MoveMode", () => {
  it("draws a drop bar following the pointer and lets a click commit", () => {
    const list = buildList();
    document.body.append(list);
    const onCommit = vi.fn();
    void new MoveMode({
      chapterId: "a",
      chapters: chapters(["a", "A", "I"], ["b", "B", "I"], ["c", "C", "II"]),
      listElement: list,
      onCommit,
    });

    const bar = list.querySelector("[data-testid='move-bar']");
    expect(bar).not.toBeNull();

    movePointerTo(25); // slot below b
    clickInList(list, 25);
    expect(onCommit).toHaveBeenCalledWith("b");
  });

  it("moves to the front when the pointer is above the first row", () => {
    const list = buildList();
    document.body.append(list);
    const onCommit = vi.fn();
    void new MoveMode({
      chapterId: "b",
      chapters: chapters(["a", "A", "I"], ["b", "B", "I"], ["c", "C", "II"]),
      listElement: list,
      onCommit,
    });

    movePointerTo(-5);
    clickInList(list, -5);
    expect(onCommit).toHaveBeenCalledWith(null);
  });

  it("skips a commit when the target is the moved row's own slot", () => {
    const list = buildList();
    document.body.append(list);
    const onCommit = vi.fn();
    void new MoveMode({
      chapterId: "a",
      chapters: chapters(["a", "A", "I"], ["b", "B", "I"], ["c", "C", "II"]),
      listElement: list,
      onCommit,
    });

    movePointerTo(-5); // above a -> after null, and a is already first
    clickInList(list, -5);
    expect(onCommit).not.toHaveBeenCalled();
  });

  it("uses the pointer position at click time, not at construction", () => {
    const list = buildList();
    document.body.append(list);
    const onCommit = vi.fn();
    void new MoveMode({
      chapterId: "a",
      chapters: chapters(["a", "A", "I"], ["b", "B", "I"], ["c", "C", "II"]),
      listElement: list,
      onCommit,
    });

    movePointerTo(-5);
    movePointerTo(25);
    clickInList(list, 25);
    expect(onCommit).toHaveBeenCalledWith("b");
  });

  it("cancels on Esc and removes the bar", () => {
    const list = buildList();
    document.body.append(list);
    const onCancel = vi.fn();
    void new MoveMode({
      chapterId: "a",
      chapters: chapters(["a", "A", "I"], ["b", "B", "I"], ["c", "C", "II"]),
      listElement: list,
      onCancel,
    });

    window.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" }));
    expect(onCancel).toHaveBeenCalled();
    expect(list.querySelector("[data-testid='move-bar']")).toBeNull();
  });

  it("cancels on a click outside the list", () => {
    const list = buildList();
    document.body.append(list);
    const onCancel = vi.fn();
    void new MoveMode({
      chapterId: "a",
      chapters: chapters(["a", "A", "I"], ["b", "B", "I"], ["c", "C", "II"]),
      listElement: list,
      onCommit: vi.fn(),
      onCancel,
    });

    document.body.dispatchEvent(
      new MouseEvent("mousedown", { bubbles: true, clientX: 400, clientY: 400 }),
    );
    expect(onCancel).toHaveBeenCalled();
  });

  it("auto-scrolls when the pointer leaves the list edges", () => {
    const list = buildList();
    list.scrollTop = 60;
    document.body.append(list);
    void new MoveMode({
      chapterId: "a",
      chapters: chapters(["a", "A", "I"], ["b", "B", "I"], ["c", "C", "II"]),
      listElement: list,
      onCommit: vi.fn(),
    });

    movePointerTo(90); // below the bottom edge -> scrolls down
    expect(list.scrollTop).toBeGreaterThan(60);
  });

  function movePointerTo(y: number): void {
    document.body.dispatchEvent(new MouseEvent("mousemove", { bubbles: true, clientX: 100, clientY: y }));
  }

  function clickInList(list: HTMLElement, y: number): void {
    list.dispatchEvent(new MouseEvent("click", { bubbles: true, clientX: 100, clientY: y }));
  }
});