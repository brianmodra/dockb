import { afterEach, describe, expect, it, vi } from "vitest";
import { mountShell } from "../src/renderer/main";
import { ApiError } from "../src/renderer/api/http";

afterEach(() => {
  document.body.replaceChildren();
  vi.restoreAllMocks();
});

function localModeApi(
  overrides: Record<string, unknown> = {},
): { api: Record<string, unknown>; bridge: Record<string, unknown> } {
  const api = {
    getAuthConfig: vi.fn(async () => ({ login_required: false, providers: [] })),
    getMe: vi.fn(async () => ({
      user: { id: "u-1", username: "brian", email: "a@b.c", display_name: "Brian", avatar_url: "" },
      password_change_required: false,
    })),
    getAppState: vi.fn(async () => ({ last_document_id: null, panel_widths: null, edit_mode: null })),
    putAppState: vi.fn(async () => ({ last_document_id: null, panel_widths: null, edit_mode: null })),
    listDocuments: vi.fn(async () => []),
    listChapters: vi.fn(async () => []),
    ...overrides,
  };
  return { api, bridge: { openExternal: vi.fn(async () => undefined) } };
}

describe("renderer shell", () => {
  it("loads and renders a chapter's text when its row is clicked", async () => {
    const getChapterDocument = vi.fn(async () => ({
      content: "# Opening 1\n\nSome text.",
      summary: null,
    }));
    const { api, bridge } = localModeApi({
      getAppState: vi.fn(async () => ({ last_document_id: "d1", panel_widths: null, edit_mode: null })),
      listChapters: vi.fn(async () => [{ id: "c1", title: "Opening 1", act: "", index: 0 }]),
      getChapterDocument,
    });
    mountShell(document.body, { api: api as never, bridge: bridge as never });
    await new Promise((r) => setTimeout(r, 0));

    (document.querySelector<HTMLElement>("[data-testid='chapter-row']")!).click();
    await new Promise((r) => setTimeout(r, 0));

    expect(getChapterDocument).toHaveBeenCalledWith("c1");
  });

  it("mounts an empty shell window with a menubar placeholder", () => {
    mountShell(document.body);
    const shell = document.querySelector("[data-testid='app-shell']");
    expect(shell).not.toBeNull();
    expect(shell?.querySelector("[data-testid='menubar']")).not.toBeNull();
  });

  it("is idempotent — mounting again replaces, not duplicates", () => {
    mountShell(document.body);
    mountShell(document.body);
    expect(document.querySelectorAll("[data-testid='app-shell']")).toHaveLength(1);
  });

  it("shows the signed-in username in the menubar after boot", async () => {
    const { api, bridge } = localModeApi();
    mountShell(document.body, { api: api as never, bridge: bridge as never });
    await new Promise((r) => setTimeout(r, 0));
    const label = document.querySelector<HTMLElement>("[data-testid='user-label']");
    expect(label).not.toBeNull();
    expect(label?.textContent).toBe("brian");
  });

  it("does not render the username when the profile is missing", async () => {
    const { api, bridge } = localModeApi({
      getMe: vi.fn(async () => {
        throw new ApiError(401, "not_authenticated");
      }),
    });
    mountShell(document.body, { api: api as never, bridge: bridge as never });
    await new Promise((r) => setTimeout(r, 0));
    const label = document.querySelector<HTMLElement>("[data-testid='user-label']");
    expect(label).not.toBeNull();
    expect(label?.hidden).toBe(true);
  });

  it("does not open the sign-in gate when login is not required", async () => {
    const { api, bridge } = localModeApi({
      getMe: vi.fn(async () => {
        throw new ApiError(401, "not_authenticated");
      }),
      getAppState: vi.fn(async () => ({ last_document_id: "d1", panel_widths: null, edit_mode: null })),
    });
    mountShell(document.body, { api: api as never, bridge: bridge as never });
    await new Promise((r) => setTimeout(r, 0));
    expect(document.querySelector("[data-testid='modal']")).toBeNull();
    expect(api.listChapters).toHaveBeenCalledWith("d1");
  });

  it("File → Open lists documents and opens the selected one", async () => {
    const { api, bridge } = localModeApi({
      getAppState: vi.fn(async () => ({ last_document_id: "d1", panel_widths: null, edit_mode: null })),
      listDocuments: vi.fn(async () => [
        { attrs: { id: "d1", title: "Faith", author: "A" }, chapter_summaries: [] },
        { attrs: { id: "d2", title: "Sight", author: "B" }, chapter_summaries: [] },
      ]),
      putAppState: vi.fn(async () => ({ last_document_id: "d2", panel_widths: null, edit_mode: null })),
    });
    mountShell(document.body, { api: api as never, bridge: bridge as never });
    await new Promise((r) => setTimeout(r, 0));

    (document.querySelector<HTMLElement>("[data-testid='menu-File']")!).click();
    (document.querySelector<HTMLElement>("[data-testid='menu-item-open']")!).click();
    await new Promise((r) => setTimeout(r, 0));

    const items = document.querySelectorAll("[data-testid='document-picker-item']");
    expect(items).toHaveLength(2);
    const open = document.querySelector<HTMLButtonElement>("[data-testid='document-picker-open']")!;
    expect(open.disabled).toBe(true);

    (items[1] as HTMLElement).click();
    await new Promise((r) => setTimeout(r, 0));
    expect(open.disabled).toBe(false);
    open.click();
    await new Promise((r) => setTimeout(r, 0));

    expect(api.listChapters).toHaveBeenCalledWith("d2");
    expect(api.putAppState).toHaveBeenCalledWith({ last_document_id: "d2" });
  });

  it("File → Delete → Document deletes after confirmation and clears an open document", async () => {
    const deleteDocument = vi.fn(async () => ({ status: { code: "ok", message: "ok" } }));
    const { api, bridge } = localModeApi({
      getAppState: vi.fn(async () => ({ last_document_id: "d1", panel_widths: null, edit_mode: null })),
      listChapters: vi.fn(async () => [{ id: "c1", title: "Opening 1", act: "", index: 0 }]),
      listDocuments: vi.fn(async () => [
        { attrs: { id: "d1", title: "Faith", author: "A" }, chapter_summaries: [] },
      ]),
      deleteDocument,
    });
    mountShell(document.body, { api: api as never, bridge: bridge as never });
    await new Promise((r) => setTimeout(r, 0));
    expect(document.querySelectorAll("[data-testid='chapter-row']")).toHaveLength(1);

    (document.querySelector<HTMLElement>("[data-testid='menu-File']")!).click();
    (document.querySelector<HTMLElement>("[data-testid='menu-item-delete']")!).click();
    (document.querySelector<HTMLElement>("[data-testid='menu-item-delete-document']")!).click();
    await new Promise((r) => setTimeout(r, 0));

    const items = document.querySelectorAll("[data-testid='document-picker-item']");
    expect(items).toHaveLength(1);
    (items[0] as HTMLElement).click();
    const del = document.querySelector<HTMLButtonElement>("[data-testid='document-picker-delete']")!;
    expect(del.disabled).toBe(false);
    del.click();
    await new Promise((r) => setTimeout(r, 0));

    const buttons = Array.from(document.querySelectorAll<HTMLElement>("[data-testid='modal-button']"));
    expect(buttons.map((b) => b.textContent?.trim())).toEqual(["Cancel", "Delete"]);
    (buttons[1] as HTMLElement).click();
    await new Promise((r) => setTimeout(r, 0));

    expect(deleteDocument).toHaveBeenCalledWith("d1");
    expect(api.putAppState).toHaveBeenLastCalledWith({ last_document_id: null });
    expect(document.querySelectorAll("[data-testid='chapter-row']")).toHaveLength(0);
  });

  it("File → Delete → Document does not delete when the confirm is cancelled", async () => {
    const deleteDocument = vi.fn(async () => ({ status: { code: "ok", message: "ok" } }));
    const { api, bridge } = localModeApi({
      getAppState: vi.fn(async () => ({ last_document_id: "d1", panel_widths: null, edit_mode: null })),
      listChapters: vi.fn(async () => [{ id: "c1", title: "Opening 1", act: "", index: 0 }]),
      listDocuments: vi.fn(async () => [
        { attrs: { id: "d1", title: "Faith", author: "A" }, chapter_summaries: [] },
      ]),
      deleteDocument,
    });
    mountShell(document.body, { api: api as never, bridge: bridge as never });
    await new Promise((r) => setTimeout(r, 0));

    (document.querySelector<HTMLElement>("[data-testid='menu-File']")!).click();
    (document.querySelector<HTMLElement>("[data-testid='menu-item-delete']")!).click();
    (document.querySelector<HTMLElement>("[data-testid='menu-item-delete-document']")!).click();
    await new Promise((r) => setTimeout(r, 0));
    (document.querySelector<HTMLElement>("[data-testid='document-picker-item']")!).click();
    (document.querySelector<HTMLButtonElement>("[data-testid='document-picker-delete']")!).click();
    await new Promise((r) => setTimeout(r, 0));

    const buttons = Array.from(document.querySelectorAll<HTMLElement>("[data-testid='modal-button']"));
    (buttons[0] as HTMLElement).click();
    await new Promise((r) => setTimeout(r, 0));

    expect(deleteDocument).not.toHaveBeenCalled();
    expect(document.querySelectorAll("[data-testid='chapter-row']")).toHaveLength(1);
  });

  it("File → Edit → Chapter saves the current chapter's title and reloads", async () => {
    const updateChapter = vi.fn(async () => ({ status: { code: "ok", message: "ok" } }));
    const listChapters = vi
      .fn(async () => [{ id: "c1", title: "Opening 1", act: "", index: 0 }])
      .mockResolvedValueOnce([{ id: "c1", title: "Opening 1", act: "", index: 0 }])
      .mockResolvedValueOnce([{ id: "c1", title: "Second", act: "", index: 0 }]);
    const { api, bridge } = localModeApi({
      getAppState: vi.fn(async () => ({ last_document_id: "d1", panel_widths: null, edit_mode: null })),
      listChapters,
      updateChapter,
      getChapterDocument: vi.fn(async () => ({ content: "", summary: null })),
    });
    mountShell(document.body, { api: api as never, bridge: bridge as never });
    await new Promise((r) => setTimeout(r, 0));

    (document.querySelector<HTMLElement>("[data-testid='chapter-row']")!).click();
    await new Promise((r) => setTimeout(r, 0));

    (document.querySelector<HTMLElement>("[data-testid='menu-File']")!).click();
    (document.querySelector<HTMLElement>("[data-testid='menu-item-edit']")!).click();
    (document.querySelector<HTMLElement>("[data-testid='menu-item-edit-chapter']")!).click();
    await new Promise((r) => setTimeout(r, 0));

    const input = document.querySelector<HTMLInputElement>("[data-testid='modal-input']")!;
    expect(input.value).toBe("Opening 1");
    input.value = "Second";
    const buttons = Array.from(document.querySelectorAll<HTMLElement>("[data-testid='modal-button']"));
    expect(buttons.map((b) => b.textContent?.trim())).toEqual(["Cancel", "Save"]);
    (buttons[1] as HTMLElement).click();
    await new Promise((r) => setTimeout(r, 0));

    expect(updateChapter).toHaveBeenCalledWith("c1", { title: "Second" });
    expect(document.querySelector("[data-testid='chapter-row']")?.textContent).toBe("Second");
  });

  it("File → Edit → Document edits title and author through the modal", async () => {
    const updateDocument = vi.fn(async () => ({ status: { code: "ok", message: "ok" } }));
    const { api, bridge } = localModeApi({
      getAppState: vi.fn(async () => ({ last_document_id: "d1", panel_widths: null, edit_mode: null })),
      listChapters: vi.fn(async () => [{ id: "c1", title: "Opening 1", act: "", index: 0 }]),
      listDocuments: vi.fn(async () => [
        { attrs: { id: "d1", title: "Faith", author: "Paul" }, chapter_summaries: [] },
        { attrs: { id: "d2", title: "Sight", author: "Brian" }, chapter_summaries: [] },
      ]),
      updateDocument,
    });
    mountShell(document.body, { api: api as never, bridge: bridge as never });
    await new Promise((r) => setTimeout(r, 0));

    (document.querySelector<HTMLElement>("[data-testid='menu-File']")!).click();
    (document.querySelector<HTMLElement>("[data-testid='menu-item-edit']")!).click();
    (document.querySelector<HTMLElement>("[data-testid='menu-item-edit-document']")!).click();
    await new Promise((r) => setTimeout(r, 0));

    const items = document.querySelectorAll("[data-testid='document-picker-item']");
    expect(items).toHaveLength(2);
    (items[1] as HTMLElement).click();
    const edit = document.querySelector<HTMLButtonElement>("[data-testid='document-picker-edit']")!;
    expect(edit.disabled).toBe(false);
    edit.click();
    await new Promise((r) => setTimeout(r, 0));

    const titleInput = document.querySelector<HTMLInputElement>("[data-testid='modal-input-title']")!;
    const authorInput = document.querySelector<HTMLInputElement>("[data-testid='modal-input-author']")!;
    expect(titleInput.value).toBe("Sight");
    expect(authorInput.value).toBe("Brian");
    titleInput.value = "Hope";
    authorInput.value = "Anna";
    const buttons = Array.from(document.querySelectorAll<HTMLElement>("[data-testid='modal-button']"));
    (buttons[1] as HTMLElement).click();
    await new Promise((r) => setTimeout(r, 0));

    expect(updateDocument).toHaveBeenCalledWith("d2", { title: "Hope", author: "Anna" });
  });
});