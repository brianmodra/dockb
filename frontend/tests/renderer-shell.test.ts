import { afterEach, describe, expect, it, vi } from "vitest";
import { mountShell } from "../src/renderer/main";
import { ApiClient } from "../src/renderer/api/client";
import { ApiError } from "../src/renderer/api/http";
import { unsavedChangesObjects } from "../src/renderer/layout/responseArea";

afterEach(() => {
  document.body.replaceChildren();
  window.localStorage.clear();
  vi.unstubAllGlobals();
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
      twoFactorEnabled: true,
      twoFactorMethod: "totp",
    })),
    getAppState: vi.fn(async () => ({ last_document_id: null, panel_widths: null, edit_mode: null })),
    putAppState: vi.fn(async () => ({ last_document_id: null, panel_widths: null, edit_mode: null })),
    listDocuments: vi.fn(async () => []),
    listChapters: vi.fn(async () => []),
    getDocument: vi.fn(async () => ({ attrs: { id: "d1", title: "", author: "" } })),
    getDocumentAttrs: vi.fn(async () => ({ id: "d1", title: "", author: "", narrative_perspective: "" })),
    getNarrativePerspectives: vi.fn(async () => ({ perspectives: [] })),
    getDocumentMentions: vi.fn(async () => ({ mentions: {} })),
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

  it("offers the backend's proofreading languages in the settings dialog", async () => {
    const getProofreadingLanguages = vi.fn(async () => ({
      languages: [{ code: "xx", label: "Testish" }],
      default: "xx",
    }));
    const { api, bridge } = localModeApi({ getProofreadingLanguages });
    mountShell(document.body, { api: api as never, bridge: bridge as never });
    await tick();

    document.querySelector<HTMLElement>('[data-testid="menu-Settings"]')?.click();
    document
      .querySelector('[data-testid="menu-item-language"]')
      ?.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    await tick();

    expect(getProofreadingLanguages).toHaveBeenCalledTimes(2);
    const items = Array.from(
      document.querySelectorAll<HTMLElement>('[data-testid="language-settings-item"]'),
    ).map((item) => item.textContent);
    expect(items).toEqual(["Testish"]);
  });

  it("falls back to the built-in language list when the backend list fails", async () => {
    const getProofreadingLanguages = vi.fn(async () => {
      throw new ApiError(503, "proofreading_unavailable");
    });
    const { api, bridge } = localModeApi({ getProofreadingLanguages });
    mountShell(document.body, { api: api as never, bridge: bridge as never });
    await tick();

    document.querySelector<HTMLElement>('[data-testid="menu-Settings"]')?.click();
    document
      .querySelector('[data-testid="menu-item-language"]')
      ?.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    await tick();

    const items = Array.from(
      document.querySelectorAll<HTMLElement>('[data-testid="language-settings-item"]'),
    ).map((item) => item.textContent);
    expect(items).toContain("English (US)");
  });

  it("saves the chosen language and applies it to the editor", async () => {
    const saved: string[] = [];
    const getProofreadingLanguages = vi.fn(async () => ({
      languages: [
        { code: "en-US", label: "English (US)" },
        { code: "fr", label: "Français" },
      ],
      default: "en-US",
    }));
    const setProofreadingLanguage = vi.fn(async (language: string) => {
      saved.push(language);
      return { languages: [], default: language };
    });
    const { api, bridge } = localModeApi({ getProofreadingLanguages, setProofreadingLanguage });
    mountShell(document.body, { api: api as never, bridge: bridge as never });
    await tick();

    openLanguageDialog();
    await tick();
    document
      .querySelector<HTMLElement>('[data-testid="language-settings-item"][data-lang="fr"]')!
      .click();
    document.querySelector<HTMLButtonElement>('[data-testid="language-settings-apply"]')!.click();
    await tick();

    expect(saved).toEqual(["fr"]);

    openLanguageDialog();
    await tick();
    const current = document.querySelector<HTMLElement>(
      '[data-testid="language-settings-item"][aria-current="true"]',
    );
    expect(current?.dataset.lang).toBe("fr");
  });

  it("keeps the chosen language when saving it fails", async () => {
    const getProofreadingLanguages = vi.fn(async () => ({
      languages: [
        { code: "en-US", label: "English (US)" },
        { code: "fr", label: "Français" },
      ],
      default: "en-US",
    }));
    const setProofreadingLanguage = vi.fn(async () => {
      throw new ApiError(503, "proofreading_unavailable");
    });
    const { api, bridge } = localModeApi({ getProofreadingLanguages, setProofreadingLanguage });
    mountShell(document.body, { api: api as never, bridge: bridge as never });
    await tick();

    openLanguageDialog();
    await tick();
    document
      .querySelector<HTMLElement>('[data-testid="language-settings-item"][data-lang="fr"]')!
      .click();
    document.querySelector<HTMLButtonElement>('[data-testid="language-settings-apply"]')!.click();
    await tick();

    expect(setProofreadingLanguage).toHaveBeenCalledWith("fr");
    openLanguageDialog();
    await tick();
    const current = document.querySelector<HTMLElement>(
      '[data-testid="language-settings-item"][aria-current="true"]',
    );
    expect(current?.dataset.lang).toBe("fr");
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
    const area = document.querySelector<HTMLElement>("[data-testid='panel-response']")!;
    expect(panel.textContent).toContain("plain prose answer");
    expect(panel.querySelectorAll(".response-line")).toHaveLength(0);
    expect(chat.hidden).toBe(false);
    expect(area.hidden).toBe(true);
    expect(area.querySelector("[data-testid='response-spinner']")).toBeNull();
  });

  it("runs the reply's highlight button straight from the sentence positions it carries", async () => {
    const getChapter = vi.fn(async () => {
      throw new Error("the editor must not re-read the chapter for its positions");
    });
    const getChapterDocument = vi.fn(async () => ({
      content: '<span data-par-id="p1">\nRain fell on the plain.\nKarakas closed the door.\n</span>',
      summary: null,
    }));
    const { api, bridge } = localModeApi({
      getChapter,
      getChapterDocument,
      sendPrompt: vi.fn(
        async () =>
          ({
            reply: JSON.stringify({
              response: [
                { button: { label: "Highlight sentence", function: "highlight", args: {
                  chapter_id: "c1",
                  paragraph_id: "p1",
                  sentence_indices: [1],
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

    expect(getChapter).not.toHaveBeenCalled();
    expect(getChapterDocument).toHaveBeenCalledWith("c1");
    expect(
      document.querySelector<HTMLElement>("[data-testid='wysiwyg-view']")?.textContent,
    ).toContain("Karakas closed the door.");
  });

  it("runs a highlight button without sentence positions by selecting the whole paragraph", async () => {
    const getChapterDocument = vi.fn(async () => ({
      content: '<span data-par-id="p1">\nRain fell on the plain.\n</span>',
      summary: null,
    }));
    const { api, bridge } = localModeApi({
      getChapterDocument,
      sendPrompt: vi.fn(
        async () =>
          ({
            reply: JSON.stringify({
              response: [
                { button: { label: "Highlight paragraph", function: "highlight", args: {
                  chapter_id: "c1",
                  paragraph_id: "p1",
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
    ).find((el) => el.textContent === "Highlight paragraph")!;
    button.click();
    await new Promise((r) => setTimeout(r, 0));

    expect(getChapterDocument).toHaveBeenCalledWith("c1");
    expect(
      document.querySelector<HTMLElement>("[data-testid='wysiwyg-view']")?.textContent,
    ).toContain("Rain fell on the plain.");
  });

  it("shows the formatting menu with quote-paragraph buttons on right-clicking a whole selected paragraph, applies a quote, and clears the strip", async () => {
    const getChapterDocument = vi.fn(async () => ({
      content: '<span data-par-id="p1">\nRain fell on the plain.\nKarakas closed the door.\n</span>',
      summary: null,
    }));
    const { api, bridge } = localModeApi({
      getChapterDocument,
      sendPrompt: vi.fn(
        async () =>
          ({
            reply: JSON.stringify({
              response: [
                {
                  button: {
                    label: "Highlight paragraph",
                    function: "highlight",
                    args: { chapter_id: "c1", paragraph_id: "p1" },
                  },
                },
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

    const highlightButton = Array.from(
      document.querySelectorAll<HTMLButtonElement>("[data-testid='response-button']"),
    ).find((el) => el.textContent === "Highlight paragraph")!;
    highlightButton.click();
    await new Promise((r) => setTimeout(r, 0));

    const paragraph = document.querySelector<HTMLElement>("[data-testid='wysiwyg-view'] p")!;
    paragraph.dispatchEvent(new MouseEvent("contextmenu", { bubbles: true, cancelable: true }));

    const area = document.querySelector<HTMLElement>("[data-testid='panel-response']")!;
    expect(area.hidden).toBe(false);
    expect(area.textContent).toContain(
      'What do you want to do with this text: "Rain fell on the plain. Karakas closed t…"',
    );
    const buttons = Array.from(area.querySelectorAll<HTMLButtonElement>("button")).map(
      (el) => el.textContent,
    );
    expect(buttons).toEqual([
      "Italic",
      "Bold",
      "Underline",
      "Monospace",
      "Normal font",
      "Large",
      "Small",
      "Normal size",
      "Clear formatting",
      'Quote para "reading"',
      'Quote para "writing"',
    ]);

    const quoteRead = Array.from(area.querySelectorAll<HTMLButtonElement>("button")).find(
      (el) => el.textContent === 'Quote para "reading"',
    )!;
    quoteRead.click();

    expect(
      document.querySelector(
        "[data-testid='wysiwyg-view'] p.quoted[data-layout-kind='quoted'][data-layout-variant='reading']",
      ),
    ).not.toBeNull();
    expect(area.hidden).toBe(true);

    document
      .querySelector<HTMLElement>("[data-testid='wysiwyg-view'] p")!
      .dispatchEvent(new MouseEvent("contextmenu", { bubbles: true, cancelable: true }));
    expect(area.hidden).toBe(false);
    const nextButtons = Array.from(area.querySelectorAll<HTMLButtonElement>("button")).map(
      (el) => el.textContent,
    );
    expect(nextButtons).toEqual([
      "Italic",
      "Bold",
      "Underline",
      "Monospace",
      "Normal font",
      "Large",
      "Small",
      "Normal size",
      "Clear formatting",
      'Quote para "writing"',
    ]);
  });

  it("reports in the message log when a quote button cannot apply in raw mode", async () => {
    const getChapterDocument = vi.fn(async () => ({
      content: '<span data-par-id="p1">\nRain fell on the plain.\n</span>',
      summary: null,
    }));
    const { api, bridge } = localModeApi({
      getChapterDocument,
      sendPrompt: vi.fn(
        async () =>
          ({
            reply: JSON.stringify({
              response: [
                {
                  button: {
                    label: "Highlight paragraph",
                    function: "highlight",
                    args: { chapter_id: "c1", paragraph_id: "p1" },
                  },
                },
              ],
            }),
          }) as never,
      ),
    });
    mountShell(document.body, { api: api as never, bridge: bridge as never });
    await new Promise((r) => setTimeout(r, 0));

    await enableRawMarkdown();

    const chat = document.querySelector<HTMLTextAreaElement>("[data-testid='chat-line']")!;
    chat.value = "highlight one";
    chat.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
    await new Promise((r) => setTimeout(r, 0));

    Array.from(document.querySelectorAll<HTMLButtonElement>("[data-testid='response-button']"))
      .find((el) => el.textContent === "Highlight paragraph")!
      .click();
    await new Promise((r) => setTimeout(r, 0));

    const paragraph = document.querySelector<HTMLElement>("[data-testid='wysiwyg-view'] p")!;
    paragraph.dispatchEvent(new MouseEvent("contextmenu", { bubbles: true, cancelable: true }));

    document.querySelector<HTMLButtonElement>("[data-testid='mode-toggle']")!.click();

    const area = document.querySelector<HTMLElement>("[data-testid='panel-response']")!;
    Array.from(area.querySelectorAll<HTMLButtonElement>("button"))
      .find((el) => el.textContent === 'Quote para "reading"')!
      .click();

    expect(area.hidden).toBe(true);
    const panel = document.querySelector<HTMLElement>("[data-testid='panel-message']")!;
    expect(panel.textContent).toContain("Quoting works in WYSIWYG chapters.");
  });

  it("closes the right-click quote prompt when the highlight changes or another chapter loads, while keeping an AI reply open", async () => {
    const getChapterDocument = vi.fn(async (chapterId: string) => ({
      content:
        chapterId === "c1"
          ? '<span data-par-id="p1">\nRain fell on the plain.\nKarakas closed the door.\n</span>'
          : '<span data-par-id="p2">\nAnother chapter.\n</span>',
      summary: null,
    }));
    const { api, bridge } = localModeApi({
      getAppState: vi.fn(async () => ({ last_document_id: "d1", panel_widths: null, edit_mode: null })),
      listChapters: vi.fn(async () => [
        { id: "c1", title: "Chapter 1", act: "", index: 0 },
        { id: "c2", title: "Chapter 2", act: "", index: 1 },
      ]),
      getChapterDocument,
      sendPrompt: vi.fn(
        async () =>
          ({
            reply: JSON.stringify({
              response: [
                {
                  button: {
                    label: "Highlight first",
                    function: "highlight",
                    args: { chapter_id: "c1", paragraph_id: "p1", sentence_indices: [0] },
                  },
                },
                {
                  button: {
                    label: "Highlight second",
                    function: "highlight",
                    args: { chapter_id: "c1", paragraph_id: "p1", sentence_indices: [1] },
                  },
                },
              ],
            }),
          }) as never,
      ),
    });
    mountShell(document.body, { api: api as never, bridge: bridge as never });
    await new Promise((r) => setTimeout(r, 0));

    const chat = document.querySelector<HTMLTextAreaElement>("[data-testid='chat-line']")!;
    chat.value = "highlight both";
    chat.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
    await new Promise((r) => setTimeout(r, 0));

    const area = document.querySelector<HTMLElement>("[data-testid='panel-response']")!;
    const firstHighlight = () =>
      Array.from(document.querySelectorAll<HTMLButtonElement>("[data-testid='response-button']")).find(
        (el) => el.textContent === "Highlight first",
      )!;
    const secondHighlight = () =>
      Array.from(document.querySelectorAll<HTMLButtonElement>("[data-testid='response-button']")).find(
        (el) => el.textContent === "Highlight second",
      )!;

    // Clicking an AI highlight button loads c1 and selects a sentence without closing the AI reply.
    firstHighlight().click();
    await new Promise((r) => setTimeout(r, 0));
    expect(area.hidden).toBe(false);
    secondHighlight().click();
    await new Promise((r) => setTimeout(r, 0));
    expect(area.hidden).toBe(false);

    // Right-clicking the highlighted text replaces the strip with the quote prompt.
    const paragraph = () => document.querySelector<HTMLElement>("[data-testid='wysiwyg-view'] p")!;
    paragraph().dispatchEvent(new MouseEvent("contextmenu", { bubbles: true, cancelable: true }));
    expect(area.hidden).toBe(false);
    expect(area.textContent).toContain("What do you want to do with this text:");

    // Changing the highlight in the editor closes the right-click quote prompt:
    // focus the editor again first, as a real click back into it would.
    const pm = document.querySelector<HTMLElement>("[data-testid='wysiwyg-view'] .ProseMirror")!;
    pm.focus();
    const range = document.createRange();
    range.setStart(pm.querySelector("p")!.firstChild!, 0);
    range.setEnd(pm.querySelector("p")!.firstChild!, 4);
    const sel = window.getSelection()!;
    sel.removeAllRanges();
    sel.addRange(range);
    document.dispatchEvent(new Event("selectionchange"));
    expect(area.hidden).toBe(true);

    // Right-click the new selection to reopen the quote prompt, then load another chapter from the left panel.
    paragraph().dispatchEvent(new MouseEvent("contextmenu", { bubbles: true, cancelable: true }));
    expect(area.hidden).toBe(false);

    const chapterRows = Array.from(document.querySelectorAll<HTMLElement>("[data-testid='chapter-row']"));
    chapterRows.find((row) => row.textContent?.includes("Chapter 2"))!.click();
    await new Promise((r) => setTimeout(r, 0));
    expect(area.hidden).toBe(true);
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
    expect(label?.closest(".menu")?.hasAttribute("hidden")).toBe(true);
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

  it("Settings → Document edits the open document through the same modal", async () => {
    const getDocument = vi.fn(async () => ({
      attrs: { id: "d1", title: "Faith", author: "Paul", narrative_perspective: "" },
      chapter_summaries: [],
    }));
    const getDocumentAttrs = vi.fn(async () => ({
      id: "d1",
      title: "Faith",
      author: "Paul",
      narrative_perspective: "first_person",
    }));
    const getNarrativePerspectives = vi.fn(async () => ({
      perspectives: [
        { code: "first_person", label: "First Person" },
        { code: "epistolary", label: "Epistolary" },
      ],
    }));
    const updateDocument = vi.fn(async () => ({ status: { code: "ok", message: "ok" } }));
    const { api, bridge } = localModeApi({
      getAppState: vi.fn(async () => ({ last_document_id: "d1", panel_widths: null, edit_mode: null })),
      listChapters: vi.fn(async () => [{ id: "c1", title: "Opening 1", act: "", index: 0 }]),
      getDocument,
      getDocumentAttrs,
      getNarrativePerspectives,
      updateDocument,
    });
    mountShell(document.body, { api: api as never, bridge: bridge as never });
    await new Promise((r) => setTimeout(r, 0));

    (document.querySelector<HTMLElement>("[data-testid='menu-Settings']")!).click();
    (document.querySelector<HTMLElement>("[data-testid='menu-item-document']")!).click();
    await new Promise((r) => setTimeout(r, 0));

    const titleInput = document.querySelector<HTMLInputElement>("[data-testid='modal-input-title']")!;
    const authorInput = document.querySelector<HTMLInputElement>("[data-testid='modal-input-author']")!;
    const perspective = document.querySelector<HTMLSelectElement>(
      "[data-testid='modal-select-narrative-perspective']",
    )!;
    expect(getDocumentAttrs).toHaveBeenCalledWith("d1");
    expect(getDocument).not.toHaveBeenCalled();
    expect(getNarrativePerspectives).toHaveBeenCalledTimes(1);
    expect(titleInput.value).toBe("Faith");
    expect(authorInput.value).toBe("Paul");
    expect(perspective.value).toBe("first_person");
    expect(
      Array.from(
        perspective.querySelectorAll<HTMLOptionElement>(
          "[data-testid='modal-option-narrative-perspective']",
        ),
      ).map((option) => option.textContent),
    ).toEqual(["None", "First Person", "Epistolary"]);

    titleInput.value = "Hope";
    authorInput.value = "Anna";
    perspective.value = "epistolary";
    const buttons = Array.from(document.querySelectorAll<HTMLElement>("[data-testid='modal-button']"));
    (buttons[1] as HTMLElement).click();
    await new Promise((r) => setTimeout(r, 0));

    expect(updateDocument).toHaveBeenCalledWith("d1", {
      title: "Hope",
      author: "Anna",
      narrative_perspective: "epistolary",
    });
  });

  it("Settings → Document asks the writer to open a document when none is open", async () => {
    const getDocumentAttrs = vi.fn(async () => ({
      id: "d1",
      title: "Faith",
      author: "Paul",
      narrative_perspective: "",
    }));
    const getNarrativePerspectives = vi.fn(async () => ({ perspectives: [] }));
    const { api, bridge } = localModeApi({ getDocumentAttrs, getNarrativePerspectives });
    mountShell(document.body, { api: api as never, bridge: bridge as never });
    await new Promise((r) => setTimeout(r, 0));

    (document.querySelector<HTMLElement>("[data-testid='menu-Settings']")!).click();
    (document.querySelector<HTMLElement>("[data-testid='menu-item-document']")!).click();
    await new Promise((r) => setTimeout(r, 0));

    expect(getDocumentAttrs).not.toHaveBeenCalled();
    expect(getNarrativePerspectives).not.toHaveBeenCalled();
    expect(document.querySelector<HTMLElement>("[data-testid='panel-message']")?.textContent).toContain(
      "Open a document first.",
    );
  });

  it("offers a Save chapter button that saves the open chapter", async () => {
    const saveChapterDocument = vi.fn(async (_id: string, content: string) => ({ content, summary: null }));
    const { api, bridge } = localModeApi({
      getAppState: vi.fn(async () => ({ last_document_id: "d1", panel_widths: null, edit_mode: null })),
      listChapters: vi.fn(async () => [{ id: "c1", title: "Opening 1", act: "", index: 0 }]),
      getChapterDocument: vi.fn(async () => ({ content: "# Opening 1\n\nSome text.", summary: null })),
      saveChapterDocument,
    });
    const layout = mountShell(document.body, { api: api as never, bridge: bridge as never });
    await new Promise((r) => setTimeout(r, 0));

    document.querySelector<HTMLElement>("[data-testid='chapter-row']")!.click();
    await new Promise((r) => setTimeout(r, 0));

    layout.showResponse(unsavedChangesObjects(32));

    const area = document.querySelector<HTMLElement>("[data-testid='panel-response']")!;
    expect(area.textContent).toContain("The chapter has 32 unsaved changes");
    const save = Array.from(area.querySelectorAll<HTMLButtonElement>("button")).find(
      (el) => el.textContent === "Save chapter",
    )!;
    expect(save.disabled).toBe(false);
    save.click();
    await new Promise((r) => setTimeout(r, 0));

    expect(saveChapterDocument).toHaveBeenCalledWith("c1", expect.stringContaining("Some text."));
  });
});

/** An editor with a live session, so boot skips straight past the gate. */
function signedInApi(overrides: Record<string, unknown> = {}): ReturnType<typeof localModeApi> {
  let signedIn = true;
  const session = {
    user: { id: "u-1", username: "brian", email: "a@b.c", display_name: "Brian", avatar_url: "" },
    password_change_required: false,
    twoFactorEnabled: true,
    twoFactorMethod: "totp",
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

function electronBridge(entries: Map<string, string> = new Map()): Record<string, unknown> & {
  cache: Map<string, string>;
} {
  return {
    cache: entries,
    isElectron: true,
    openExternal: vi.fn(async () => undefined),
    chooseCacheDirectory: vi.fn(async () => "/cache"),
    setCacheRoot: vi.fn(async () => undefined),
    cacheRead: vi.fn(async (path: string) => entries.get(path) ?? null),
    cacheWrite: vi.fn(async (path: string, content: string) => {
      entries.set(path, content);
    }),
    cacheDelete: vi.fn(async (path: string) => {
      entries.delete(path);
    }),
    cacheRename: vi.fn(async () => undefined),
    cacheMoveDirectory: vi.fn(async () => undefined),
    cacheList: vi.fn(async () => Array.from(entries.keys())),
  };
}

function clickModalButton(label: string): void {
  const button = Array.from(document.querySelectorAll<HTMLButtonElement>("[data-testid='modal-button']")).find(
    (candidate) => candidate.textContent === label,
  )!;
  button.click();
}

function connectivityToggle(): HTMLElement {
  return document.querySelector<HTMLElement>("[data-testid='connectivity-toggle']")!;
}

function openLanguageDialog(): void {
  document.querySelector<HTMLElement>('[data-testid="menu-Settings"]')?.click();
  document
    .querySelector('[data-testid="menu-item-language"]')
    ?.dispatchEvent(new MouseEvent("click", { bubbles: true }));
}

function signInForm(): HTMLElement | null {
  return document.querySelector("[data-testid='sign-in-form']");
}

function userLabel(): HTMLElement | null {
  return document.querySelector("[data-testid='user-label']");
}

function chooseUserAction(label: string): void {
  (document.querySelector<HTMLElement>("[data-testid='user-label']")!).click();
  const item = label === "Sign out" ? "sign-out" : "user-settings";
  document.querySelector<HTMLElement>(`[data-testid="menu-item-${item}"]`)!.click();
}

async function enableRawMarkdown(): Promise<void> {
  chooseUserAction("Settings");
  const checkbox = document.querySelector<HTMLInputElement>("[data-testid='raw-markdown-checkbox']")!;
  checkbox.checked = true;
  Array.from(document.querySelectorAll<HTMLButtonElement>("[data-testid='modal-button']"))
    .find((el) => el.textContent === "Done")!
    .click();
  await tick();
}

describe("offline mode", () => {
  it("hides the connectivity icon in the browser and shows it in Electron", async () => {
    mountShell(document.body, { bridge: {} as never });
    expect(document.querySelector('[data-testid="connectivity-toggle"]')).toBeNull();

    document.body.replaceChildren();
    window.localStorage.setItem("dockb.fileCacheDirectory", "/cache");
    const { api } = localModeApi();
    mountShell(document.body, { api: api as never, bridge: electronBridge() as never });
    await tick();

    expect(connectivityToggle()).not.toBeNull();
    expect(connectivityToggle().dataset.online).toBe("true");
  });

  it("stays online when the offline prompt is cancelled", async () => {
    window.localStorage.setItem("dockb.fileCacheDirectory", "/cache");
    const { api } = localModeApi();
    const bridge = electronBridge();
    mountShell(document.body, { api: api as never, bridge: bridge as never });
    await tick();

    connectivityToggle().click();
    await tick();
    clickModalButton("Cancel");

    expect(connectivityToggle().dataset.online).toBe("true");
    expect(bridge.cacheWrite).not.toHaveBeenCalled();
  });

  it("asks before going offline, caches missing chapters and disables backend-changing menus", async () => {
    window.localStorage.setItem("dockb.fileCacheDirectory", "/cache");
    const serverText = "# Opening 1\n\nServer body.";
    const { api } = localModeApi({
      getAppState: vi.fn(async () => ({ last_document_id: "d1", panel_widths: null, edit_mode: null })),
      listChapters: vi.fn(async () => [{ id: "c1", title: "Opening 1", act: "", index: 0 }]),
      getDocumentAttrs: vi.fn(async () => ({ id: "d1", title: "Novel", author: "", narrative_perspective: "" })),
      getChapterDocument: vi.fn(async () => ({ content: serverText, summary: null })),
    });
    const bridge = electronBridge();
    mountShell(document.body, { api: api as never, bridge: bridge as never });
    await tick();

    connectivityToggle().click();
    await tick();

    expect(document.querySelector('[data-testid="modal-title"]')?.textContent).toBe("Go offline?");
    clickModalButton("Yes");
    await tick();
    await tick();

    expect(bridge.cacheWrite).toHaveBeenCalledWith("Novel/Act None/Opening 1.md", serverText);
    expect(connectivityToggle().dataset.online).toBe("false");
    expect(connectivityToggle().querySelector('[data-testid="connectivity-offline-icon"]')).not.toBeNull();
    expect(
      document.querySelector<HTMLButtonElement>('[data-testid="menu-item-import"]')!.disabled,
    ).toBe(true);
  });

  it("asks before going back online and uploads backend-dirty cached chapters", async () => {
    window.localStorage.setItem("dockb.fileCacheDirectory", "/cache");
    const serverText = "# Opening 1\n\nServer body.";
    const dirtyText = "# Opening 1\n\nEdited while offline.";
    const saveChapterDocument = vi.fn(async (_id: string, content: string) => ({
      content,
      summary: null,
    }));
    const { api } = localModeApi({
      getAppState: vi.fn(async () => ({ last_document_id: "d1", panel_widths: null, edit_mode: null })),
      listChapters: vi.fn(async () => [{ id: "c1", title: "Opening 1", act: "", index: 0 }]),
      getDocumentAttrs: vi.fn(async () => ({ id: "d1", title: "Novel", author: "", narrative_perspective: "" })),
      getChapterDocument: vi.fn(async () => ({ content: serverText, summary: null })),
      saveChapterDocument,
    });
    const bridge = electronBridge(new Map([["Novel/Act None/Opening 1.md", dirtyText]]));
    mountShell(document.body, { api: api as never, bridge: bridge as never });
    await tick();

    connectivityToggle().click();
    await tick();
    clickModalButton("Yes");
    await tick();
    await tick();

    connectivityToggle().click();
    await tick();

    expect(document.querySelector('[data-testid="modal-title"]')?.textContent).toBe(
      "Go back online?",
    );
    clickModalButton("Yes");
    await tick();
    await tick();

    expect(saveChapterDocument).toHaveBeenCalledWith("c1", dirtyText);
    expect(connectivityToggle().dataset.online).toBe("true");
    expect(
      document.querySelector<HTMLButtonElement>('[data-testid="menu-item-import"]')!.disabled,
    ).toBe(false);
  });

  it("stays offline when the back-online prompt is cancelled", async () => {
    window.localStorage.setItem("dockb.fileCacheDirectory", "/cache");
    const saveChapterDocument = vi.fn(async (_id: string, content: string) => ({
      content,
      summary: null,
    }));
    const { api } = localModeApi({
      getAppState: vi.fn(async () => ({ last_document_id: "d1", panel_widths: null, edit_mode: null })),
      listChapters: vi.fn(async () => [{ id: "c1", title: "Opening 1", act: "", index: 0 }]),
      getChapterDocument: vi.fn(async () => ({
        content: "# Opening 1\n\nServer body.",
        summary: null,
      })),
      saveChapterDocument,
    });
    mountShell(document.body, { api: api as never, bridge: electronBridge() as never });
    await tick();

    connectivityToggle().click();
    await tick();
    clickModalButton("Yes");
    await tick();
    await tick();

    connectivityToggle().click();
    await tick();
    expect(document.querySelector('[data-testid="modal-title"]')?.textContent).toBe(
      "Go back online?",
    );
    clickModalButton("Cancel");

    expect(connectivityToggle().dataset.online).toBe("false");
    expect(saveChapterDocument).not.toHaveBeenCalled();
  });

  it("offers offline mode when any backend fetch fails in Electron", async () => {
    window.localStorage.setItem("dockb.fileCacheDirectory", "/cache");
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        if (url.endsWith("/auth/config")) {
          return new Response(JSON.stringify({ login_required: false, providers: [] }), { status: 200 });
        }
        if (url.endsWith("/auth/me")) {
          return new Response(
            JSON.stringify({
              user: { id: "u-1", username: "brian", email: "a@b.c", display_name: "Brian", avatar_url: "" },
              password_change_required: false,
            }),
            { status: 200 },
          );
        }
        throw new TypeError("Failed to fetch");
      }),
    );
    mountShell(document.body, { api: new ApiClient("/api") as never, bridge: electronBridge() as never });
    await tick();

    expect(document.querySelector('[data-testid="modal-title"]')?.textContent).toBe("Go offline?");
    clickModalButton("Cancel");
    expect(connectivityToggle().dataset.online).toBe("true");
  });
});

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

    chooseUserAction("Sign out");
    await tick();

    expect(api.logout).toHaveBeenCalledTimes(1);
    expect(document.querySelectorAll("[data-testid='chapter-row']")).toHaveLength(0);
    expect(editor.textContent ?? "").not.toContain("Some text.");
    expect(userLabel()?.closest(".menu")?.hasAttribute("hidden")).toBe(true);
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

    chooseUserAction("Sign out");
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

    chooseUserAction("Sign out");
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

    chooseUserAction("Sign out");
    await tick();

    expect(logout).not.toHaveBeenCalled();
    expect(signInForm()).not.toBeNull();
  });
});

describe("structural cache mirroring", () => {
  it("renames the cached document directory and uses the new title for later reads", async () => {
    window.localStorage.setItem("dockb.fileCacheDirectory", "/cache");
    const bridge = electronBridge(new Map([["Faith/Act None/Opening 1.md", "# Opening 1"]]));
    const { api } = localModeApi({
      getAppState: vi.fn(async () => ({ last_document_id: "d1", panel_widths: null, edit_mode: null })),
      listChapters: vi.fn(async () => [{ id: "c1", title: "Opening 1", act: "", index: 0 }]),
      getDocumentAttrs: vi.fn(async () => ({
        id: "d1",
        title: "Faith",
        author: "Paul",
        narrative_perspective: "",
      })),
      getNarrativePerspectives: vi.fn(async () => ({ perspectives: [] })),
      getChapterDocument: vi.fn(async () => ({ content: "# Opening 1\n\nText.", summary: null })),
      updateDocument: vi.fn(async () => ({ status: { code: "ok", message: "ok" } })),
    });
    mountShell(document.body, { api: api as never, bridge: bridge as never });
    await tick();

    document.querySelector<HTMLElement>("[data-testid='menu-Settings']")!.click();
    document.querySelector<HTMLElement>("[data-testid='menu-item-document']")!.click();
    await tick();
    const titleInput = document.querySelector<HTMLInputElement>("[data-testid='modal-input-title']")!;
    titleInput.value = "Hope";
    clickModalButton("Save");
    await tick();

    expect(bridge.cacheMoveDirectory).toHaveBeenCalledWith("Faith", "Hope");
    (document.querySelector<HTMLElement>("[data-testid='chapter-row']")!).click();
    await tick();
    expect(bridge.cacheRead).toHaveBeenCalledWith("Hope/Act None/Opening 1.md");
  });

  it("deletes the cached document's files when the document is deleted", async () => {
    window.localStorage.setItem("dockb.fileCacheDirectory", "/cache");
    const bridge = electronBridge(new Map([["Faith/Act None/Opening 1.md", "# Opening 1"]]));
    const { api } = localModeApi({
      getAppState: vi.fn(async () => ({ last_document_id: "d1", panel_widths: null, edit_mode: null })),
      listChapters: vi.fn(async () => [{ id: "c1", title: "Opening 1", act: "", index: 0 }]),
      listDocuments: vi.fn(async () => [
        { attrs: { id: "d1", title: "Faith", author: "Paul" }, chapter_summaries: [] },
      ]),
      deleteDocument: vi.fn(async () => ({ status: { code: "ok", message: "ok" } })),
    });
    mountShell(document.body, { api: api as never, bridge: bridge as never });
    await tick();

    document.querySelector<HTMLElement>("[data-testid='menu-File']")!.click();
    document.querySelector<HTMLElement>("[data-testid='menu-item-delete']")!.click();
    document.querySelector<HTMLElement>("[data-testid='menu-item-delete-document']")!.click();
    await tick();
    (document.querySelector<HTMLElement>("[data-testid='document-picker-item']")!).click();
    document.querySelector<HTMLElement>("[data-testid='document-picker-delete']")!.click();
    await tick();
    clickModalButton("Delete");
    await tick();

    expect(bridge.cacheDelete).toHaveBeenCalledWith("Faith/Act None/Opening 1.md");
  });

  it("leaves the cached directory alone when renaming the document fails", async () => {
    window.localStorage.setItem("dockb.fileCacheDirectory", "/cache");
    const bridge = electronBridge();
    const { api } = localModeApi({
      getAppState: vi.fn(async () => ({ last_document_id: "d1", panel_widths: null, edit_mode: null })),
      listChapters: vi.fn(async () => []),
      getDocumentAttrs: vi.fn(async () => ({
        id: "d1",
        title: "Faith",
        author: "Paul",
        narrative_perspective: "",
      })),
      getNarrativePerspectives: vi.fn(async () => ({ perspectives: [] })),
      updateDocument: vi.fn(async () => {
        throw new Error("conflict");
      }),
    });
    mountShell(document.body, { api: api as never, bridge: bridge as never });
    await tick();

    document.querySelector<HTMLElement>("[data-testid='menu-Settings']")!.click();
    document.querySelector<HTMLElement>("[data-testid='menu-item-document']")!.click();
    await tick();
    const titleInput = document.querySelector<HTMLInputElement>("[data-testid='modal-input-title']")!;
    titleInput.value = "Hope";
    clickModalButton("Save");
    await tick();

    expect(bridge.cacheMoveDirectory).not.toHaveBeenCalled();
  });

  it("leaves cached files alone when deleting the document fails", async () => {
    window.localStorage.setItem("dockb.fileCacheDirectory", "/cache");
    const bridge = electronBridge(new Map([["Faith/Act None/Opening 1.md", "# Opening 1"]]));
    const { api } = localModeApi({
      getAppState: vi.fn(async () => ({ last_document_id: "d1", panel_widths: null, edit_mode: null })),
      listChapters: vi.fn(async () => [{ id: "c1", title: "Opening 1", act: "", index: 0 }]),
      listDocuments: vi.fn(async () => [
        { attrs: { id: "d1", title: "Faith", author: "Paul" }, chapter_summaries: [] },
      ]),
      deleteDocument: vi.fn(async () => {
        throw new Error("conflict");
      }),
    });
    mountShell(document.body, { api: api as never, bridge: bridge as never });
    await tick();

    document.querySelector<HTMLElement>("[data-testid='menu-File']")!.click();
    document.querySelector<HTMLElement>("[data-testid='menu-item-delete']")!.click();
    document.querySelector<HTMLElement>("[data-testid='menu-item-delete-document']")!.click();
    await tick();
    (document.querySelector<HTMLElement>("[data-testid='document-picker-item']")!).click();
    document.querySelector<HTMLElement>("[data-testid='document-picker-delete']")!.click();
    await tick();
    clickModalButton("Delete");
    await tick();

    expect(bridge.cacheDelete).not.toHaveBeenCalled();
  });

  it("opens the reset modal from the reset-password query and removes the token", async () => {
    window.history.replaceState(null, "", "/editor/?reset-password=reset-token");
    const { api, bridge } = localModeApi({
      confirmPasswordReset: vi.fn(async () => undefined),
    });
    mountShell(document.body, { api: api as never, bridge: bridge as never });
    await tick();

    expect(document.querySelector("[data-testid='password-reset-submit']")).not.toBeNull();
    expect(window.location.search).not.toContain("reset-password");
    expect(api.confirmPasswordReset).not.toHaveBeenCalled();
  });
});
