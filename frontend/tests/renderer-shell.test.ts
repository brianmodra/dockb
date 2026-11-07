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

  it("sends the chat prompt through the client, logs the prompt into the panel, and shows the reply", async () => {
    const sendPrompt = vi.fn(async () => ({ reply: "an answer" }));
    const { api, bridge } = localModeApi({ sendPrompt });
    mountShell(document.body, { api: api as never, bridge: bridge as never });
    await new Promise((r) => setTimeout(r, 0));

    const chat = document.querySelector<HTMLTextAreaElement>("[data-testid='chat-line']")!;
    chat.value = "where should I start?";
    chat.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
    const panel = document.querySelector<HTMLElement>("[data-testid='panel-message']")!;
    expect(panel.textContent).toContain("where should I start?");
    expect(panel.textContent).not.toContain("You asked:");
    expect(sendPrompt).toHaveBeenCalledWith("where should I start?", null);
    await new Promise((r) => setTimeout(r, 0));
    expect(panel.textContent).toContain("an answer");
    expect(panel.textContent).not.toContain("AI said:");
  });

  it("sends the open document's id with the chat prompt", async () => {
    const sendPrompt = vi.fn(async () => ({ reply: "an answer" }));
    const { api, bridge } = localModeApi({
      getAppState: vi.fn(async () => ({ last_document_id: "d1", panel_widths: null, edit_mode: null })),
      listChapters: vi.fn(async () => [{ id: "c1", title: "Opening 1", act: "", index: 0 }]),
      sendPrompt,
    });
    mountShell(document.body, { api: api as never, bridge: bridge as never });
    await new Promise((r) => setTimeout(r, 0));

    const chat = document.querySelector<HTMLTextAreaElement>("[data-testid='chat-line']")!;
    chat.value = "where should I start?";
    chat.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
    await new Promise((r) => setTimeout(r, 0));
    expect(sendPrompt).toHaveBeenCalledWith("where should I start?", "d1");
  });

  it("shows the spinner while the model is replying, then the reply in the response area", async () => {
    let settle: (reply: string) => void = () => undefined;
    const sendPrompt = vi.fn(
      () =>
        new Promise<{ reply: string }>((resolve) => {
          settle = (reply) => resolve({ reply });
        }),
    );
    const { api, bridge } = localModeApi({ sendPrompt });
    mountShell(document.body, { api: api as never, bridge: bridge as never });
    await new Promise((r) => setTimeout(r, 0));

    const chat = document.querySelector<HTMLTextAreaElement>("[data-testid='chat-line']")!;
    chat.value = "find sentences about rain";
    chat.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
    const area = document.querySelector<HTMLElement>("[data-testid='panel-response']")!;
    expect(area.querySelector("[data-testid='response-spinner']")).not.toBeNull();
    expect(chat.hidden).toBe(true);

    settle(
      JSON.stringify({
        response: [
          { text: "Two paragraphs match." },
          { button: { label: "Highlight sentence", function: "highlight", args: { chapter_id: "c1" } } },
        ],
      }),
    );
    await new Promise((r) => setTimeout(r, 0));

    expect(area.textContent).toContain("Two paragraphs match.");
    const found = Array.from(area.querySelectorAll<HTMLButtonElement>("button")).find(
      (el) => el.textContent === "Highlight sentence",
    );
    expect(found).not.toBeNull();
    expect(found?.disabled).toBe(false);
    expect(chat.hidden).toBe(false);
  });

  it("pushes a reply that is not response syntax into the log as plain text", async () => {
    const { api, bridge } = localModeApi({ sendPrompt: vi.fn(async () => ({ reply: "plain prose answer" })) });
    mountShell(document.body, { api: api as never, bridge: bridge as never });
    await new Promise((r) => setTimeout(r, 0));

    const chat = document.querySelector<HTMLTextAreaElement>("[data-testid='chat-line']")!;
    chat.value = "who wrote this?";
    chat.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
    await new Promise((r) => setTimeout(r, 0));

    const panel = document.querySelector<HTMLElement>("[data-testid='panel-message']")!;
    expect(panel.textContent).toContain("plain prose answer");
    expect(panel.querySelectorAll(".response-line")).toHaveLength(0);
  });

  it("runs the reply's highlight button: opens the chapter and selects the sentence", async () => {
    const chapterWire = {
      type: "chapter",
      attrs: { id: "c1", title: "Opening 1", act: "" },
      content: [
        {
          type: "paragraph",
          attrs: { id: "p1" },
          content: [
            {
              type: "sentence",
              attrs: { id: "s1" },
              content: [{ type: "text", text: "Rain fell on the plain." }],
            },
            {
              type: "sentence",
              attrs: { id: "s2" },
              content: [{ type: "text", text: "Karakas closed the door." }],
            },
          ],
        },
      ],
    };
    const getChapter = vi.fn(async () => chapterWire);
    const { api, bridge } = localModeApi({
      getChapter,
      getChapterDocument: vi.fn(async () => ({
        content: '<span data-par-id="p1">\nRain fell on the plain.\nKarakas closed the door.\n</span>',
        summary: null,
      })),
      sendPrompt: vi.fn(
        async () =>
          ({
            reply: JSON.stringify({
              response: [
                { button: { label: "Highlight sentence", function: "highlight", args: {
                  chapter_id: "c1",
                  paragraph_id: "p1",
                  sentence_ids: ["s2"],
                } } },
              ],
            }),
          }) as never,
      ),
    });
    mountShell(document.body, { api: api as never, bridge: bridge as never });
    await new Promise((r) => setTimeout(r, 0));

    const chat = document.querySelector<HTMLTextAreaElement>("[data-testid='chat-line']")!;
    chat.value = "highlight one";
    chat.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
    await new Promise((r) => setTimeout(r, 0));

    const button = Array.from(
      document.querySelectorAll<HTMLButtonElement>("[data-testid='response-button']"),
    ).find((el) => el.textContent === "Highlight sentence")!;
    button.click();
    await new Promise((r) => setTimeout(r, 0));

    expect(getChapter).toHaveBeenCalledWith("c1");
    expect(
      document.querySelector<HTMLElement>("[data-testid='wysiwyg-view']")?.textContent,
    ).toContain("Rain fell on the plain.");
  });

  it("routes a chat failure into the message panel", async () => {
    const sendPrompt = vi.fn(async () => {
      throw new ApiError(503, "ai_key_missing: OPENAI_API_KEY is not set");
    });
    const { api, bridge } = localModeApi({ sendPrompt });
    mountShell(document.body, { api: api as never, bridge: bridge as never });
    await new Promise((r) => setTimeout(r, 0));

    const chat = document.querySelector<HTMLTextAreaElement>("[data-testid='chat-line']")!;
    chat.value = "hello";
    chat.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
    await new Promise((r) => setTimeout(r, 0));
    const panel = document.querySelector<HTMLElement>("[data-testid='panel-message']")!;
    expect(panel.textContent).toContain("AI chat: ai_key_missing");
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

/** An editor with a live session, so boot skips straight past the gate. */
function signedInApi(overrides: Record<string, unknown> = {}): ReturnType<typeof localModeApi> {
  let signedIn = true;
  const session = {
    user: { id: "u-1", username: "brian", email: "a@b.c", display_name: "Brian", avatar_url: "" },
    password_change_required: false,
  };
  return localModeApi({
    getAuthConfig: vi.fn(async () => ({ login_required: true, providers: [] })),
    getMe: vi.fn(async () => {
      if (!signedIn) {
        throw new ApiError(401, "not_authenticated");
      }
      return session;
    }),
    loginWithPassword: vi.fn(async () => {
      signedIn = true;
      return session;
    }),
    logout: vi.fn(async () => {
      signedIn = false;
    }),
    getAppState: vi.fn(async () => ({
      last_document_id: "d1",
      panel_widths: null,
      edit_mode: null,
    })),
    listChapters: vi.fn(async () => [{ id: "c1", title: "Opening 1", act: "", index: 0 }]),
    getChapterDocument: vi.fn(async () => ({
      content: "# Opening 1\n\nSome text.",
      summary: null,
    })),
    ...overrides,
  });
}

function tick(): Promise<void> {
  return new Promise((r) => setTimeout(r, 0));
}

function signInForm(): HTMLElement | null {
  return document.querySelector("[data-testid='sign-in-form']");
}

function userLabel(): HTMLElement | null {
  return document.querySelector("[data-testid='user-label']");
}

function chooseFileItem(key: string): void {
  (document.querySelector<HTMLElement>("[data-testid='menu-File']")!).click();
  (document.querySelector<HTMLElement>(`[data-testid='menu-item-${key}']`)!).click();
}

describe("sign out", () => {
  it("ends the session, clears the workspace and shows the gate again", async () => {
    const { api, bridge } = signedInApi();
    mountShell(document.body, { api: api as never, bridge: bridge as never });
    await tick();

    expect(document.querySelectorAll("[data-testid='chapter-row']")).toHaveLength(1);
    expect(userLabel()?.hidden).toBe(false);
    expect(signInForm()).toBeNull();

    (document.querySelector<HTMLElement>("[data-testid='chapter-row']")!).click();
    await tick();
    const editor = document.querySelector<HTMLElement>("[data-testid='edit-wysiwyg']")!;
    expect(editor.textContent).toContain("Some text.");

    chooseFileItem("sign-out");
    await tick();

    expect(api.logout).toHaveBeenCalledTimes(1);
    expect(document.querySelectorAll("[data-testid='chapter-row']")).toHaveLength(0);
    expect(editor.textContent ?? "").not.toContain("Some text.");
    expect(userLabel()?.hidden).toBe(true);
    expect(signInForm()).not.toBeNull();
    // Exactly one dialog, and it is the gate: a clean buffer must not be asked about.
    const titles = Array.from(
      document.querySelectorAll("[data-testid='modal-title']"),
    ).map((n) => n.textContent);
    expect(titles).toEqual(["Sign in"]);
  });

  it("signs back in and starts up again after signing out", async () => {
    const { api, bridge } = signedInApi();
    mountShell(document.body, { api: api as never, bridge: bridge as never });
    await tick();

    chooseFileItem("sign-out");
    await tick();
    expect(signInForm()).not.toBeNull();

    const username = document.querySelector<HTMLInputElement>("[data-testid='sign-in-username']")!;
    const password = document.querySelector<HTMLInputElement>("[data-testid='sign-in-password']")!;
    username.value = "brian";
    password.value = "correct horse";
    (document.querySelector<HTMLFormElement>("[data-testid='sign-in-form']")!).dispatchEvent(
      new Event("submit", { bubbles: true, cancelable: true }),
    );
    await tick();

    expect(api.loginWithPassword).toHaveBeenCalledWith("brian", "correct horse");
    expect(document.querySelectorAll("[data-testid='chapter-row']")).toHaveLength(1);
    expect(userLabel()?.hidden).toBe(false);
    expect(signInForm()).toBeNull();
  });

  it("stays signed in when ending the session fails", async () => {
    const { api, bridge } = signedInApi({
      logout: vi.fn(async () => {
        throw new ApiError(500, "boom");
      }),
    });
    mountShell(document.body, { api: api as never, bridge: bridge as never });
    await tick();

    chooseFileItem("sign-out");
    await tick();

    expect(api.logout).toHaveBeenCalledTimes(1);
    expect(userLabel()?.hidden).toBe(false);
    expect(signInForm()).toBeNull();
    expect(document.querySelector("[data-testid='panel-message']")?.textContent).toContain(
      "Sign out",
    );
  });

  it("does nothing when there is no session to end", async () => {
    const logout = vi.fn();
    const { api, bridge } = signedInApi({
      getMe: vi.fn(async () => {
        throw new ApiError(401, "not_authenticated");
      }),
      logout,
    });
    mountShell(document.body, { api: api as never, bridge: bridge as never });
    await tick();
    expect(signInForm()).not.toBeNull();

    chooseFileItem("sign-out");
    await tick();

    expect(logout).not.toHaveBeenCalled();
    expect(signInForm()).not.toBeNull();
  });
});
