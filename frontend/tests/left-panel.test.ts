import { afterEach, describe, expect, it, vi } from "vitest";
import type { ChapterListRow, MutationResponse } from "../src/renderer/api/types";
import { LeftPanel, type LeftPanelApi } from "../src/renderer/layout/leftPanel";

function fakeApi(overrides: Partial<LeftPanelApi> = {}): LeftPanelApi {
  const ok: MutationResponse = { status: { code: "ok", message: "ok" } };
  return {
    listChapters: vi.fn(async (): Promise<ChapterListRow[]> => []),
    updateChapter: vi.fn(async () => ok),
    deleteChapter: vi.fn(async () => ok),
    reorderChapter: vi.fn(async () => ok),
    ...overrides,
  };
}

function chapters(...rows: Array<[id: string, title: string, act: string]>): ChapterListRow[] {
  return rows.map(([id, title, act], index) => ({ id, title, act, index }));
}

function listRows(): HTMLElement[] {
  return Array.from(document.querySelectorAll("[data-testid='chapter-row']")) as HTMLElement[];
}

afterEach(() => {
  document.body.replaceChildren();
  vi.restoreAllMocks();
});

describe("LeftPanel", () => {
  it("loads and renders chapters grouped by act", async () => {
    const api = fakeApi({
      listChapters: vi.fn(
        async (): Promise<ChapterListRow[]> =>
          chapters(["a", "A", "I"], ["b", "B", "I"], ["c", "C", "II"]),
      ),
    });
    const panel = new LeftPanel({ api });
    document.body.append(panel.element);

    await panel.load("d1");

    expect(api.listChapters).toHaveBeenCalledWith("d1");
    const headers = Array.from(document.querySelectorAll("[data-testid='act-header']"));
    expect(headers.map((h) => h.textContent)).toEqual(["I", "II"]);
  });

  it("routes load failures into the message panel", async () => {
    const onMessage = vi.fn();
    const api = fakeApi({
      listChapters: vi.fn(async () => {
        throw new Error("backend down");
      }),
    });
    const panel = new LeftPanel({ api, onMessage });
    document.body.append(panel.element);

    await panel.load("d1");
    expect(onMessage).toHaveBeenCalledWith(expect.stringContaining("backend down"));
  });

  it("opens the document editor on chapter row click", async () => {
    const onEdit = vi.fn();
    const panel = new LeftPanel({
      api: fakeApi({
        listChapters: vi.fn(
          async (): Promise<ChapterListRow[]> => chapters(["a", "A", "I"]),
        ),
      }),
      onEdit,
    });
    document.body.append(panel.element);
    await panel.load("d1");

    listRows()[0].dispatchEvent(new MouseEvent("click", { bubbles: true }));
    expect(onEdit).toHaveBeenCalledWith("a");
  });

  it("only highlights when right-clicking a chapter, without opening the editor", async () => {
    const onEdit = vi.fn();
    const panel = new LeftPanel({
      api: fakeApi({
        listChapters: vi.fn(
          async (): Promise<ChapterListRow[]> => chapters(["a", "A", "I"]),
        ),
      }),
      onEdit,
    });
    document.body.append(panel.element);
    await panel.load("d1");

    listRows()[0].dispatchEvent(new MouseEvent("contextmenu", { bubbles: true, clientX: 10, clientY: 10 }));
    expect(document.querySelector("[data-testid='context-menu']")).not.toBeNull();
    expect(onEdit).not.toHaveBeenCalled();
  });

  it("opens the document editor on Edit", async () => {
    const onEdit = vi.fn();
    const panel = new LeftPanel({
      api: fakeApi({
        listChapters: vi.fn(
          async (): Promise<ChapterListRow[]> => chapters(["a", "A", "I"]),
        ),
      }),
      onEdit,
    });
    document.body.append(panel.element);
    await panel.load("d1");

    listRows()[0].dispatchEvent(new MouseEvent("contextmenu", { bubbles: true, clientX: 10, clientY: 10 }));
    const menu = document.querySelector("[data-testid='context-menu']");
    expect(menu).not.toBeNull();

    const editItem = Array.from(menu!.querySelectorAll<HTMLElement>(".context-item")).find(
      (n) => n.textContent === "Edit",
    )!;
    editItem.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    expect(onEdit).toHaveBeenCalledWith("a");
  });

  it("renames a chapter through the modal and reloads the list", async () => {
    const updateChapter = vi.fn(async () => ({ status: { code: "ok", message: "ok" } }));
    const api = fakeApi({
      listChapters: vi
        .fn(async () => chapters(["a", "A", "I"]))
        .mockResolvedValueOnce(chapters(["a", "A", "I"]))
        .mockResolvedValueOnce(chapters(["a", "Renamed", "I"])),
      updateChapter,
    });
    const panel = new LeftPanel({ api });
    document.body.append(panel.element);
    await panel.load("d1");

    listRows()[0].dispatchEvent(new MouseEvent("contextmenu", { bubbles: true, clientX: 10, clientY: 10 }));
    const renameItem = Array.from(
      document.querySelectorAll<HTMLElement>("[data-testid='context-menu'] .context-item"),
    ).find((n) => n.textContent === "Rename")!;
    renameItem.dispatchEvent(new MouseEvent("click", { bubbles: true }));

    const input = document.querySelector<HTMLInputElement>("[data-testid='modal-input']")!;
    expect(input.value).toBe("A");
    input.value = "Renamed";
    document.querySelectorAll<HTMLElement>("[data-testid='modal-button']")[1].dispatchEvent(
      new MouseEvent("click", { bubbles: true }),
    );

    await vi.waitFor(() => expect(updateChapter).toHaveBeenCalledWith("a", { title: "Renamed" }));
    await vi.waitFor(() =>
      expect(document.querySelector("[data-testid='chapter-row']")?.textContent).toBe("Renamed"),
    );
  });

  it("deletes a chapter only after confirmation", async () => {
    const deleteChapter = vi.fn(async () => ({ status: { code: "ok", message: "ok" } }));
    const api = fakeApi({
      listChapters: vi
        .fn(async () => [chapters(["a", "A", "I"])])
        .mockResolvedValueOnce(chapters(["a", "A", "I"]))
        .mockResolvedValueOnce([]),
      deleteChapter,
    });
    const panel = new LeftPanel({ api });
    document.body.append(panel.element);
    await panel.load("d1");

    listRows()[0].dispatchEvent(new MouseEvent("contextmenu", { bubbles: true, clientX: 10, clientY: 10 }));
    const deleteItem = Array.from(
      document.querySelectorAll<HTMLElement>("[data-testid='context-menu'] .context-item"),
    ).find((n) => n.textContent === "Delete")!;
    deleteItem.dispatchEvent(new MouseEvent("click", { bubbles: true }));

    const confirm = document.querySelector("[data-testid='modal']");
    expect(confirm).not.toBeNull();
    document.querySelectorAll<HTMLElement>("[data-testid='modal-button']")[0].dispatchEvent(
      new MouseEvent("click", { bubbles: true }),
    );
    await vi.waitFor(() => expect(deleteChapter).not.toHaveBeenCalled());

    deleteItem.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    document.querySelectorAll<HTMLElement>("[data-testid='modal-button']")[1].dispatchEvent(
      new MouseEvent("click", { bubbles: true }),
    );
    await vi.waitFor(() => expect(deleteChapter).toHaveBeenCalledWith("a"));
  });

  it("enters move mode from the menu and commits the reorder", async () => {
    const reorderChapter = vi.fn(async () => ({ status: { code: "ok", message: "ok" } }));
    const api = fakeApi({
      listChapters: vi.fn(
        async (): Promise<ChapterListRow[]> =>
          chapters(["a", "A", "I"], ["b", "B", "I"], ["c", "C", "II"]),
      ),
      reorderChapter,
    });
    const panel = new LeftPanel({ api });
    document.body.append(panel.element);
    await panel.load("d1");

    const rows = listRows();
    // geometry: a@0-20, b@20-40, c@40-60
    rows.forEach((row, i) => {
      const top = i * 20;
      const bottom = top + 20;
      row.getBoundingClientRect = () =>
        ({ top, bottom, left: 0, right: 100, width: 100, height: 20 }) as DOMRect;
    });
    document.body.dispatchEvent(new MouseEvent("mousemove", { bubbles: true, clientX: 5, clientY: 5 }));
    rows[0].dispatchEvent(new MouseEvent("contextmenu", { bubbles: true, clientX: 5, clientY: 5 }));
    const moveItem = Array.from(
      document.querySelectorAll<HTMLElement>("[data-testid='context-menu'] .context-item"),
    ).find((n) => n.textContent === "Move")!;
    moveItem.dispatchEvent(new MouseEvent("click", { bubbles: true }));

    const bar = document.querySelector("[data-testid='move-bar']");
    expect(bar).not.toBeNull();

    document.body.dispatchEvent(new MouseEvent("mousemove", { bubbles: true, clientX: 50, clientY: 35 }));
    document.body.querySelector<HTMLElement>("[data-testid='chapter-list']")!.dispatchEvent(
      new MouseEvent("click", { bubbles: true, clientX: 50, clientY: 35 }),
    );
    await vi.waitFor(() => expect(reorderChapter).toHaveBeenCalledWith("a", "b"));
  });

  it("escapes move mode with Esc and makes no API call", async () => {
    const reorderChapter = vi.fn(async () => ({ status: { code: "ok", message: "ok" } }));
    const api = fakeApi({
      listChapters: vi.fn(
        async (): Promise<ChapterListRow[]> =>
          chapters(["a", "A", "I"], ["b", "B", "I"], ["c", "C", "II"]),
      ),
      reorderChapter,
    });
    const panel = new LeftPanel({ api });
    document.body.append(panel.element);
    await panel.load("d1");

    const rows = listRows();
    rows.forEach((row, i) => {
      const top = i * 20;
      row.getBoundingClientRect = () => ({ top, bottom: top + 20 } as DOMRect);
    });
    rows[0].dispatchEvent(new MouseEvent("contextmenu", { bubbles: true, clientX: 5, clientY: 5 }));
    const moveItem = Array.from(
      document.querySelectorAll<HTMLElement>("[data-testid='context-menu'] .context-item"),
    ).find((n) => n.textContent === "Move")!;
    moveItem.dispatchEvent(new MouseEvent("click", { bubbles: true }));

    window.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" }));
    expect(document.querySelector("[data-testid='move-bar']")).toBeNull();
    expect(reorderChapter).not.toHaveBeenCalled();
  });
});