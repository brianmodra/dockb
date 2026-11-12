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
    renumberChapters: vi.fn(async () => ({ status: { code: "ok", message: "ok" }, renames: [] })),
    setPov: vi.fn(async () => ({ applied: true, pov: null, warning: null })),
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

  it("reports Read-only view with the chapter id and title", async () => {
    const onReadonly = vi.fn();
    const panel = new LeftPanel({
      api: fakeApi({
        listChapters: vi.fn(async (): Promise<ChapterListRow[]> => chapters(["a", "A", "I"])),
      }),
      onReadonly,
    });
    document.body.append(panel.element);
    await panel.load("d1");

    listRows()[0].dispatchEvent(new MouseEvent("contextmenu", { bubbles: true, clientX: 10, clientY: 10 }));
    const menu = document.querySelector("[data-testid='context-menu']");
    const item = Array.from(menu!.querySelectorAll<HTMLElement>(".context-item")).find(
      (n) => n.textContent === "Read-only view",
    )!;
    item.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    expect(onReadonly).toHaveBeenCalledWith("a", "A");
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

  it("offers Move, Renumber, and POV on a manuscript chapter", async () => {
    const api = fakeApi({
      listChapters: vi.fn(async (): Promise<ChapterListRow[]> => chapters(["a", "A", "I"])),
    });
    const panel = new LeftPanel({ api });
    document.body.append(panel.element);
    await panel.load("d1");

    listRows()[0].dispatchEvent(new MouseEvent("contextmenu", { bubbles: true, clientX: 10, clientY: 10 }));
    const labels = Array.from(document.querySelectorAll<HTMLElement>("[data-testid='context-menu'] .context-item")).map(
      (n) => n.textContent,
    );
    expect(labels).toEqual(["Edit", "Read-only view", "Rename", "Move", "Renumber", "POV", "Delete"]);
  });

  it("drops Move, Renumber, and POV on a character chapter", async () => {
    const api = fakeApi({
      listChapters: vi.fn(
        async (): Promise<ChapterListRow[]> => [{ id: "k", title: "Karakas", act: "", index: 0, category: "Character" }],
      ),
    });
    const panel = new LeftPanel({ api });
    document.body.append(panel.element);
    await panel.load("d1");

    listRows()[0].dispatchEvent(new MouseEvent("contextmenu", { bubbles: true, clientX: 10, clientY: 10 }));
    const labels = Array.from(document.querySelectorAll<HTMLElement>("[data-testid='context-menu'] .context-item")).map(
      (n) => n.textContent,
    );
    expect(labels).toEqual(["Edit", "Read-only view", "Rename", "Delete"]);
  });

  it("sets the POV from the modal and closes it", async () => {
    const setPov = vi.fn(async () => ({ applied: true, pov: { id: "k1", title: "Karakas" }, warning: null }));
    const api = fakeApi({
      listChapters: vi.fn(async (): Promise<ChapterListRow[]> => chapters(["a", "A", "I"])),
      setPov,
    });
    const onMessage = vi.fn();
    const panel = new LeftPanel({ api, onMessage });
    document.body.append(panel.element);
    await panel.load("d1");

    listRows()[0].dispatchEvent(new MouseEvent("contextmenu", { bubbles: true, clientX: 10, clientY: 10 }));
    Array.from(document.querySelectorAll<HTMLElement>("[data-testid='context-menu'] .context-item"))
      .find((n) => n.textContent === "POV")!
      .dispatchEvent(new MouseEvent("click", { bubbles: true }));

    const input = document.querySelector<HTMLInputElement>("[data-testid='pov-input']")!;
    expect(input).not.toBeNull();
    input.value = "Kiral";
    Array.from(document.querySelectorAll<HTMLElement>("[data-testid='modal-button']"))
      .find((n) => n.textContent === "Set POV")!
      .dispatchEvent(new MouseEvent("click", { bubbles: true }));

    await vi.waitFor(() => expect(setPov).toHaveBeenCalledWith("a", "Kiral"));
    await vi.waitFor(() => expect(onMessage).toHaveBeenCalledWith('POV set to "Karakas".'));
    await vi.waitFor(() => expect(document.querySelector("[data-testid='pov-input']")).toBeNull());
  });

  it("stays in the POV modal on a suggestion, with the text replaced and the warning shown", async () => {
    const setPov = vi
      .fn(async () => ({ applied: false, pov: null, warning: 'The pov "Kira" did not match; perhaps you meant "Karakas"', suggestion: "Karakas" }))
      .mockResolvedValueOnce({ applied: false, pov: null, warning: 'The pov "Kira" did not match; perhaps you meant "Karakas"', suggestion: "Karakas" })
      .mockResolvedValueOnce({ applied: true, pov: { id: "k1", title: "Karakas" }, warning: null });
    const api = fakeApi({
      listChapters: vi.fn(async (): Promise<ChapterListRow[]> => chapters(["a", "A", "I"])),
      setPov,
    });
    const panel = new LeftPanel({ api });
    document.body.append(panel.element);
    await panel.load("d1");

    listRows()[0].dispatchEvent(new MouseEvent("contextmenu", { bubbles: true, clientX: 10, clientY: 10 }));
    Array.from(document.querySelectorAll<HTMLElement>("[data-testid='context-menu'] .context-item"))
      .find((n) => n.textContent === "POV")!
      .dispatchEvent(new MouseEvent("click", { bubbles: true }));
    document.querySelector<HTMLInputElement>("[data-testid='pov-input']")!.value = "Kira";
    Array.from(document.querySelectorAll<HTMLElement>("[data-testid='modal-button']"))
      .find((n) => n.textContent === "Set POV")!
      .dispatchEvent(new MouseEvent("click", { bubbles: true }));

    await vi.waitFor(() => {
      const modalInput = document.querySelector<HTMLInputElement>("[data-testid='pov-input']");
      expect(modalInput).not.toBeNull();
      expect(modalInput!.value).toBe("Karakas");
      expect(document.querySelector("[data-testid='pov-warning']")!.textContent).toContain("perhaps you meant");
    });

    Array.from(document.querySelectorAll<HTMLElement>("[data-testid='modal-button']"))
      .find((n) => n.textContent === "Set POV")!
      .dispatchEvent(new MouseEvent("click", { bubbles: true }));
    await vi.waitFor(() => expect(setPov).toHaveBeenCalledTimes(2));
    await vi.waitFor(() => expect(document.querySelector("[data-testid='pov-input']")).toBeNull());
  });

  it("pre-fills the POV modal with the chapter's existing POV character", async () => {
    const setPov = vi.fn(async () => ({ applied: true, pov: null, warning: null }));
    const api = fakeApi({
      listChapters: vi.fn(
        async (): Promise<ChapterListRow[]> => [{ id: "a", title: "Opening 1", act: "I", index: 0, pov: "Karakas" }],
      ),
      setPov,
    });
    const panel = new LeftPanel({ api });
    document.body.append(panel.element);
    await panel.load("d1");

    listRows()[0].dispatchEvent(new MouseEvent("contextmenu", { bubbles: true, clientX: 10, clientY: 10 }));
    Array.from(document.querySelectorAll<HTMLElement>("[data-testid='context-menu'] .context-item"))
      .find((n) => n.textContent === "POV")!
      .dispatchEvent(new MouseEvent("click", { bubbles: true }));

    expect(document.querySelector<HTMLInputElement>("[data-testid='pov-input']")!.value).toBe("Karakas");
  });

  it("tells the shell when a chapter's POV was set", async () => {
    const setPov = vi.fn(async () => ({ applied: true, pov: { id: "k1", title: "Karakas" }, warning: null }));
    const api = fakeApi({
      listChapters: vi.fn(async (): Promise<ChapterListRow[]> => chapters(["a", "A", "I"])),
      setPov,
    });
    const onPovChanged = vi.fn();
    const panel = new LeftPanel({ api, onPovChanged });
    document.body.append(panel.element);
    await panel.load("d1");

    listRows()[0].dispatchEvent(new MouseEvent("contextmenu", { bubbles: true, clientX: 10, clientY: 10 }));
    Array.from(document.querySelectorAll<HTMLElement>("[data-testid='context-menu'] .context-item"))
      .find((n) => n.textContent === "POV")!
      .dispatchEvent(new MouseEvent("click", { bubbles: true }));
    document.querySelector<HTMLInputElement>("[data-testid='pov-input']")!.value = "Karakas";
    Array.from(document.querySelectorAll<HTMLElement>("[data-testid='modal-button']"))
      .find((n) => n.textContent === "Set POV")!
      .dispatchEvent(new MouseEvent("click", { bubbles: true }));

    await vi.waitFor(() => expect(onPovChanged).toHaveBeenCalledWith("a", "Karakas"));
  });

  it("renumbers the document from the context menu after confirming", async () => {
    const renumberChapters = vi.fn(async () => ({
      status: { code: "ok", message: "ok" },
      renames: [
        { id: "a", old_title: "Opening 2", new_title: "Opening 1" },
        { id: "b", old_title: "Setup 5b", new_title: "Setup 2" },
      ],
    }));
    const api = fakeApi({
      listChapters: vi
        .fn(async (): Promise<ChapterListRow[]> => chapters(["a", "Opening 1", "I"], ["b", "Setup 2", "I"]))
        .mockResolvedValueOnce(chapters(["a", "Opening 2", "I"], ["b", "Setup 5b", "I"]))
        .mockResolvedValueOnce(chapters(["a", "Opening 1", "I"], ["b", "Setup 2", "I"])),
      renumberChapters,
    });
    const onMessage = vi.fn();
    const panel = new LeftPanel({ api, onMessage });
    document.body.append(panel.element);
    await panel.load("d1");

    listRows()[0].dispatchEvent(new MouseEvent("contextmenu", { bubbles: true, clientX: 10, clientY: 10 }));
    const renumberItem = Array.from(
      document.querySelectorAll<HTMLElement>("[data-testid='context-menu'] .context-item"),
    ).find((n) => n.textContent === "Renumber")!;
    renumberItem.dispatchEvent(new MouseEvent("click", { bubbles: true }));

    const confirm = document.querySelector("[data-testid='modal']");
    expect(confirm).not.toBeNull();
    document.querySelectorAll<HTMLElement>("[data-testid='modal-button']")[1].dispatchEvent(
      new MouseEvent("click", { bubbles: true }),
    );

    await vi.waitFor(() => expect(renumberChapters).toHaveBeenCalledWith("d1", { start: 1 }));
    await vi.waitFor(() => expect(onMessage).toHaveBeenCalledWith("Renumbered 2 chapters."));
    await vi.waitFor(() =>
      expect(
        Array.from(listRows()).map((row) => row.textContent),
      ).toEqual(["Opening 1", "Setup 2"]),
    );
  });

  it("renumbers from zero when the dialog's box is ticked", async () => {
    const renumberChapters = vi.fn(async () => ({
      status: { code: "ok", message: "ok" },
      renames: [],
    }));
    const api = fakeApi({
      listChapters: vi.fn(async (): Promise<ChapterListRow[]> => chapters(["a", "A", "I"])),
      renumberChapters,
    });
    const panel = new LeftPanel({ api });
    document.body.append(panel.element);
    await panel.load("d1");

    listRows()[0].dispatchEvent(new MouseEvent("contextmenu", { bubbles: true, clientX: 10, clientY: 10 }));
    const renumberItem = Array.from(
      document.querySelectorAll<HTMLElement>("[data-testid='context-menu'] .context-item"),
    ).find((n) => n.textContent === "Renumber")!;
    renumberItem.dispatchEvent(new MouseEvent("click", { bubbles: true }));

    const checkbox = document.querySelector<HTMLInputElement>("[data-testid='renumber-start-zero']");
    expect(checkbox).not.toBeNull();
    checkbox!.checked = true;
    document.querySelectorAll<HTMLElement>("[data-testid='modal-button']")[1].dispatchEvent(
      new MouseEvent("click", { bubbles: true }),
    );

    await vi.waitFor(() => expect(renumberChapters).toHaveBeenCalledWith("d1", { start: 0 }));
  });

  it("renumbers nothing without a confirmation", async () => {
    const renumberChapters = vi.fn(async () => ({
      status: { code: "ok", message: "ok" },
      renames: [],
    }));
    const api = fakeApi({
      listChapters: vi.fn(async (): Promise<ChapterListRow[]> => chapters(["a", "A", "I"])),
      renumberChapters,
    });
    const panel = new LeftPanel({ api });
    document.body.append(panel.element);
    await panel.load("d1");

    listRows()[0].dispatchEvent(new MouseEvent("contextmenu", { bubbles: true, clientX: 10, clientY: 10 }));
    const renumberItem = Array.from(
      document.querySelectorAll<HTMLElement>("[data-testid='context-menu'] .context-item"),
    ).find((n) => n.textContent === "Renumber")!;
    renumberItem.dispatchEvent(new MouseEvent("click", { bubbles: true }));

    document.querySelectorAll<HTMLElement>("[data-testid='modal-button']")[0].dispatchEvent(
      new MouseEvent("click", { bubbles: true }),
    );
    await vi.waitFor(() => expect(renumberChapters).not.toHaveBeenCalled());
  });

  it("says so when nothing needed renumbering", async () => {
    const renumberChapters = vi.fn(async () => ({
      status: { code: "ok", message: "ok" },
      renames: [],
    }));
    const onMessage = vi.fn();
    const api = fakeApi({
      listChapters: vi.fn(async (): Promise<ChapterListRow[]> => chapters(["a", "A", "I"])),
      renumberChapters,
    });
    const panel = new LeftPanel({ api, onMessage });
    document.body.append(panel.element);
    await panel.load("d1");

    listRows()[0].dispatchEvent(new MouseEvent("contextmenu", { bubbles: true, clientX: 10, clientY: 10 }));
    const renumberItem = Array.from(
      document.querySelectorAll<HTMLElement>("[data-testid='context-menu'] .context-item"),
    ).find((n) => n.textContent === "Renumber")!;
    renumberItem.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    document.querySelectorAll<HTMLElement>("[data-testid='modal-button']")[1].dispatchEvent(
      new MouseEvent("click", { bubbles: true }),
    );

    await vi.waitFor(() => expect(onMessage).toHaveBeenCalledWith("No chapters needed renumbering."));
  });

  it("routes a renumber failure into the message panel", async () => {
    const onMessage = vi.fn();
    const api = fakeApi({
      listChapters: vi.fn(async (): Promise<ChapterListRow[]> => chapters(["a", "A", "I"])),
      renumberChapters: vi.fn(async () => {
        throw new Error("chapter_title_conflict");
      }),
    });
    const panel = new LeftPanel({ api, onMessage });
    document.body.append(panel.element);
    await panel.load("d1");

    listRows()[0].dispatchEvent(new MouseEvent("contextmenu", { bubbles: true, clientX: 10, clientY: 10 }));
    const renumberItem = Array.from(
      document.querySelectorAll<HTMLElement>("[data-testid='context-menu'] .context-item"),
    ).find((n) => n.textContent === "Renumber")!;
    renumberItem.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    document.querySelectorAll<HTMLElement>("[data-testid='modal-button']")[1].dispatchEvent(
      new MouseEvent("click", { bubbles: true }),
    );

    await vi.waitFor(() => expect(onMessage).toHaveBeenCalledWith(expect.stringContaining("chapter_title_conflict")));
  });

  it("exposes the loaded document id and clears it with the list", async () => {
    const api = fakeApi({
      listChapters: vi.fn(async (): Promise<ChapterListRow[]> => chapters(["a", "A", "I"])),
    });
    const panel = new LeftPanel({ api });
    document.body.append(panel.element);
    await panel.load("d1");
    expect(panel.currentDocumentId()).toBe("d1");
    expect(listRows()).toHaveLength(1);

    panel.clear();

    expect(panel.currentDocumentId()).toBeNull();
    expect(listRows()).toHaveLength(0);
  });

  it("reports the selected chapter and reloads the list from the backend", async () => {
    const listChapters = vi
      .fn(async (): Promise<ChapterListRow[]> => chapters(["a", "A", "I"]))
      .mockResolvedValueOnce(chapters(["a", "A", "I"]))
      .mockResolvedValueOnce(chapters(["a", "Second", "I"]));
    const api = fakeApi({ listChapters });
    const panel = new LeftPanel({ api });
    document.body.append(panel.element);
    await panel.load("d1");

    listRows()[0].dispatchEvent(new MouseEvent("click", { bubbles: true }));
    expect(panel.selectedChapter()).toEqual({ id: "a", title: "A", act: "I", index: 0 });

    await panel.reload();
    expect(api.listChapters).toHaveBeenLastCalledWith("d1");
    expect(panel.selectedChapter()?.title).toBe("Second");
  });

  it("keeps the selected chapter when a POV change reloads the list", async () => {
    const afterPov = chapters(["a", "A", "I"], ["b", "B2", "I"], ["c", "C", "II"]).map((row) =>
      row.id === "b" ? { ...row, pov: "Karakas" } : row,
    );
    const api = fakeApi({
      listChapters: vi
        .fn(async (): Promise<ChapterListRow[]> => afterPov)
        .mockResolvedValueOnce(chapters(["a", "A", "I"], ["b", "B", "I"], ["c", "C", "II"]))
        .mockResolvedValueOnce(afterPov),
      setPov: vi.fn(async () => ({ applied: true, pov: { id: "k1", title: "Karakas" }, warning: null })),
    });
    const panel = new LeftPanel({ api });
    document.body.append(panel.element);
    await panel.load("d1");

    listRows()[1].dispatchEvent(new MouseEvent("contextmenu", { bubbles: true, clientX: 10, clientY: 10 }));
    Array.from(document.querySelectorAll<HTMLElement>("[data-testid='context-menu'] .context-item"))
      .find((n) => n.textContent === "POV")!
      .dispatchEvent(new MouseEvent("click", { bubbles: true }));
    document.querySelector<HTMLInputElement>("[data-testid='pov-input']")!.value = "Karakas";
    Array.from(document.querySelectorAll<HTMLElement>("[data-testid='modal-button']"))
      .find((n) => n.textContent === "Set POV")!
      .dispatchEvent(new MouseEvent("click", { bubbles: true }));

    await vi.waitFor(() => expect(listRows()[1].textContent).toBe("B2"));
    const selected = document.querySelector<HTMLElement>(".chapter-row.is-selected");
    expect(selected?.dataset.chapterId).toBe("b");
  });

  it("keeps the selection on the renamed chapter when the list reloads", async () => {
    const updateChapter = vi.fn(async () => ({ status: { code: "ok", message: "ok" } }));
    const api = fakeApi({
      listChapters: vi
        .fn(async (): Promise<ChapterListRow[]> => chapters(["a", "A", "I"], ["b", "Renamed", "I"]))
        .mockResolvedValueOnce(chapters(["a", "A", "I"], ["b", "B", "I"]))
        .mockResolvedValueOnce(chapters(["a", "A", "I"], ["b", "Renamed", "I"])),
      updateChapter,
    });
    const panel = new LeftPanel({ api });
    document.body.append(panel.element);
    await panel.load("d1");

    listRows()[1].dispatchEvent(new MouseEvent("contextmenu", { bubbles: true, clientX: 10, clientY: 10 }));
    Array.from(document.querySelectorAll<HTMLElement>("[data-testid='context-menu'] .context-item"))
      .find((n) => n.textContent === "Rename")!
      .dispatchEvent(new MouseEvent("click", { bubbles: true }));
    document.querySelector<HTMLInputElement>("[data-testid='modal-input']")!.value = "Renamed";
    Array.from(document.querySelectorAll<HTMLElement>("[data-testid='modal-button']"))
      .find((n) => n.textContent === "Rename")!
      .dispatchEvent(new MouseEvent("click", { bubbles: true }));

    await vi.waitFor(() => expect(listRows()[1].textContent).toBe("Renamed"));
    const selected = document.querySelector<HTMLElement>(".chapter-row.is-selected");
    expect(selected?.dataset.chapterId).toBe("b");
    expect(selected?.textContent).toBe("Renamed");
  });

  it("drops the selection when the selected chapter is gone from the reloaded list", async () => {
    const listChapters = vi
      .fn(async (): Promise<ChapterListRow[]> => chapters(["a", "A", "I"]))
      .mockResolvedValueOnce(chapters(["a", "A", "I"], ["b", "B", "I"]))
      .mockResolvedValueOnce(chapters(["a", "A", "I"]));
    const api = fakeApi({ listChapters });
    const panel = new LeftPanel({ api });
    document.body.append(panel.element);
    await panel.load("d1");

    listRows()[1].dispatchEvent(new MouseEvent("click", { bubbles: true }));
    expect(panel.selectedChapter()?.id).toBe("b");

    await panel.reload();

    expect(panel.selectedChapter()).toBeNull();
  });

  it("clears the selection when another document is loaded", async () => {
    const listChapters = vi
      .fn(async (): Promise<ChapterListRow[]> => chapters(["z", "Z", "I"]))
      .mockResolvedValueOnce(chapters(["a", "A", "I"]))
      .mockResolvedValueOnce(chapters(["z", "Z", "I"]));
    const api = fakeApi({ listChapters });
    const panel = new LeftPanel({ api });
    document.body.append(panel.element);
    await panel.load("d1");

    listRows()[0].dispatchEvent(new MouseEvent("click", { bubbles: true }));
    expect(panel.selectedChapter()?.id).toBe("a");

    await panel.load("d2");

    expect(panel.selectedChapter()).toBeNull();
    expect(document.querySelector(".chapter-row.is-selected")).toBeNull();
  });
});