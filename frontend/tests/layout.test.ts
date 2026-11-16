import { afterEach, describe, expect, it, vi } from "vitest";
import { AppLayout } from "../src/renderer/layout/layout";

afterEach(() => {
  document.body.replaceChildren();
  vi.restoreAllMocks();
});

function drag(handleEl: HTMLElement, fromX: number, fromY: number, dx: number, dy: number): void {
  handleEl.dispatchEvent(new MouseEvent("mousedown", { clientX: fromX, clientY: fromY, bubbles: true }));
  window.dispatchEvent(new MouseEvent("mousemove", { clientX: fromX + dx, clientY: fromY + dy, bubbles: true }));
  window.dispatchEvent(new MouseEvent("mouseup", { bubbles: true }));
}

function leftHandle(layout: AppLayout): HTMLElement {
  return layout.element.querySelector<HTMLElement>('[data-testid="resize-handle-v-left"]')!;
}

function rightHandle(layout: AppLayout): HTMLElement {
  return layout.element.querySelector<HTMLElement>('[data-testid="resize-handle-v-right"]')!;
}

function bottomHandle(layout: AppLayout): HTMLElement {
  return layout.element.querySelector<HTMLElement>('[data-testid="resize-handle-h-bottom"]')!;
}

describe("AppLayout", () => {
  it("renders menubar, left/edit/right panels and a message panel", () => {
    const layout = new AppLayout({});
    document.body.append(layout.element);
    expect(layout.element.querySelector('[data-testid="menubar"]')).not.toBeNull();
    expect(layout.element.querySelector('[data-testid="panel-left"]')).not.toBeNull();
    expect(layout.element.querySelector('[data-testid="panel-edit"]')).not.toBeNull();
    expect(layout.element.querySelector('[data-testid="panel-right"]')).not.toBeNull();
    expect(layout.element.querySelector('[data-testid="panel-message"]')).not.toBeNull();
  });

  it("starts with the right panel at the chapter-list width and the seam still available", () => {
    const layout = new AppLayout({});
    document.body.append(layout.element);
    const right = layout.element.querySelector<HTMLElement>('[data-testid="panel-right"]')!;
    expect(right.style.width).toBe("240px");
    expect(layout.element.querySelector('[data-testid="resize-handle-v-right"]')).not.toBeNull();
  });

  it("resizes the left panel through its vertical seam", () => {
    const layout = new AppLayout({});
    document.body.append(layout.element);
    const left = layout.element.querySelector<HTMLElement>('[data-testid="panel-left"]')!;
    const startWidth = parseInt(left.style.width, 10);
    drag(leftHandle(layout), 200, 100, 60, 0);
    expect(parseInt(left.style.width, 10)).toBe(startWidth + 60);
  });

  it("opens the right panel by dragging its seam leftwards, following the mouse", () => {
    const layout = new AppLayout({});
    document.body.append(layout.element);
    const right = layout.element.querySelector<HTMLElement>('[data-testid="panel-right"]')!;
    drag(rightHandle(layout), 900, 100, -80, 0);
    expect(parseInt(right.style.width, 10)).toBe(320);
  });

  it("closes the right panel when dragging its seam rightwards", () => {
    const layout = new AppLayout({});
    document.body.append(layout.element);
    const right = layout.element.querySelector<HTMLElement>('[data-testid="panel-right"]')!;
    drag(rightHandle(layout), 900, 100, 1000, 0);
    expect(parseInt(right.style.width, 10)).toBe(10);
  });

  it("grows the message panel when the bottom seam is dragged up, following the mouse", () => {
    const layout = new AppLayout({});
    document.body.append(layout.element);
    const message = layout.element.querySelector<HTMLElement>('[data-testid="panel-message"]')!;
    drag(bottomHandle(layout), 100, 500, 0, -60);
    expect(parseInt(message.style.height, 10)).toBe(84);
  });

  it("shrinks the message panel when the bottom seam is dragged down", () => {
    const layout = new AppLayout({});
    document.body.append(layout.element);
    const message = layout.element.querySelector<HTMLElement>('[data-testid="panel-message"]')!;
    expect(parseInt(message.style.height, 10)).toBe(24);
    drag(bottomHandle(layout), 100, 500, 0, 200);
    expect(parseInt(message.style.height, 10)).toBe(24);
  });

  it("enforces a minimum left-panel width", () => {
    const layout = new AppLayout({});
    document.body.append(layout.element);
    const left = layout.element.querySelector<HTMLElement>('[data-testid="panel-left"]')!;
    drag(leftHandle(layout), 200, 100, -1000, 0);
    expect(parseInt(left.style.width, 10)).toBeGreaterThanOrEqual(120);
  });

  it("keeps a ten-pixel minimum right-panel width when dragging the seam rightwards", () => {
    const layout = new AppLayout({});
    document.body.append(layout.element);
    const right = layout.element.querySelector<HTMLElement>('[data-testid="panel-right"]')!;
    drag(rightHandle(layout), 900, 100, 5000, 0);
    expect(parseInt(right.style.width, 10)).toBeGreaterThanOrEqual(10);
  });

  it("enforces a minimum message-panel height", () => {
    const layout = new AppLayout({});
    document.body.append(layout.element);
    const message = layout.element.querySelector<HTMLElement>('[data-testid="panel-message"]')!;
    drag(bottomHandle(layout), 100, 500, 0, 5000);
    expect(parseInt(message.style.height, 10)).toBeGreaterThanOrEqual(24);
  });

  it("opens the language settings dialog from the Settings menu", () => {
    const onOpenLanguageSettings = vi.fn();
    const layout = new AppLayout({ onOpenLanguageSettings });
    document.body.append(layout.element);
    layout.element.querySelector<HTMLElement>('[data-testid="menu-Settings"]')?.click();
    layout.element.querySelector('[data-testid="menu-item-language"]')?.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    expect(onOpenLanguageSettings).toHaveBeenCalledTimes(1);
  });

  it("reports mode through the mode toggle and updates the edit panel", () => {
    const layout = new AppLayout({});
    document.body.append(layout.element);
    layout.setRawMarkdownEnabled(true);
    layout.element.querySelector<HTMLElement>('[data-testid="mode-toggle"]')?.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    const edit = layout.element.querySelector<HTMLElement>('[data-testid="panel-edit"]')!;
    expect(layout.mode).toBe("raw");
    expect(edit.getAttribute("data-mode")).toBe("raw");
  });

  it("exposes a message sink for console output", () => {
    const layout = new AppLayout({});
    document.body.append(layout.element);
    layout.pushMessage("hello console");
    const message = layout.element.querySelector<HTMLElement>('[data-testid="panel-message"]')!;
    expect(message.textContent).toContain("hello console");
  });

  it("shows the chat line with a greyed-out hint", () => {
    const layout = new AppLayout({});
    document.body.append(layout.element);
    const chat = layout.element.querySelector<HTMLTextAreaElement>('[data-testid="chat-line"]')!;
    expect(chat).toBeInstanceOf(HTMLTextAreaElement);
    expect(chat.parentElement?.dataset.testid).toBe("panel-message");
    expect(chat.placeholder).toBe("Prompt AI here");
  });

  it("shows only the chat box when the message panel is one line high", () => {
    const layout = new AppLayout({});
    document.body.append(layout.element);
    const message = layout.element.querySelector<HTMLElement>('[data-testid="panel-message"]')!;
    const log = layout.element.querySelector<HTMLElement>('[data-testid="message-log"]')!;
    const chat = layout.element.querySelector<HTMLTextAreaElement>('[data-testid="chat-line"]')!;
    expect(parseInt(message.style.height, 10)).toBe(24);
    expect(log.hidden).toBe(true);
    expect(parseInt(chat.style.height, 10)).toBe(24);
  });

  it("reveals the log above a one-line chat box once the panel grows past one line", () => {
    const layout = new AppLayout({});
    document.body.append(layout.element);
    const log = layout.element.querySelector<HTMLElement>('[data-testid="message-log"]')!;
    const chat = layout.element.querySelector<HTMLTextAreaElement>('[data-testid="chat-line"]')!;
    drag(bottomHandle(layout), 100, 500, 0, -40);
    expect(log.hidden).toBe(false);
    expect(parseInt(chat.style.height, 10)).toBe(22);
  });

  it("defaults the chat box to about one third of the panel in whole lines", () => {
    const layout = new AppLayout({});
    document.body.append(layout.element);
    const message = layout.element.querySelector<HTMLElement>('[data-testid="panel-message"]')!;
    const chat = layout.element.querySelector<HTMLTextAreaElement>('[data-testid="chat-line"]')!;
    drag(bottomHandle(layout), 100, 500, 0, -100);
    const panel = parseInt(message.style.height, 10);
    const defaultLines = Math.max(1, Math.round((panel / 3) / 22));
    expect(parseInt(chat.style.height, 10)).toBe(defaultLines * 22);
  });

  it("extends the chat box in whole lines to fit the text being typed", () => {
    const layout = new AppLayout({});
    document.body.append(layout.element);
    const chat = layout.element.querySelector<HTMLTextAreaElement>('[data-testid="chat-line"]')!;
    drag(bottomHandle(layout), 100, 500, 0, -100);
    chat.value = "first\nsecond\nthird";
    chat.dispatchEvent(new Event("input", { bubbles: true }));
    expect(parseInt(chat.style.height, 10)).toBe(66);
  });

  it("returns the chat box to its default once the text is cleared", () => {
    const layout = new AppLayout({});
    document.body.append(layout.element);
    const message = layout.element.querySelector<HTMLElement>('[data-testid="panel-message"]')!;
    const chat = layout.element.querySelector<HTMLTextAreaElement>('[data-testid="chat-line"]')!;
    drag(bottomHandle(layout), 100, 500, 0, -100);
    const defaultHeight = parseInt(chat.style.height, 10);
    chat.value = "first\nsecond\nthird";
    chat.dispatchEvent(new Event("input", { bubbles: true }));
    chat.value = "";
    chat.dispatchEvent(new Event("input", { bubbles: true }));
    expect(parseInt(chat.style.height, 10)).toBe(defaultHeight);
    expect(parseInt(message.style.height, 10)).toBe(124);
  });

  it("submits the chat prompt on Enter and clears the line", () => {
    const onPrompt = vi.fn();
    const layout = new AppLayout({ onPrompt });
    document.body.append(layout.element);
    const chat = layout.element.querySelector<HTMLTextAreaElement>('[data-testid="chat-line"]')!;
    chat.value = "who wrote this?";
    chat.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
    expect(onPrompt).toHaveBeenCalledWith("who wrote this?");
    expect(chat.value).toBe("");
  });

  it("moves the submitted prompt into the log as its newest line and keeps focus", () => {
    const onPrompt = vi.fn();
    const layout = new AppLayout({ onPrompt });
    document.body.append(layout.element);
    layout.pushMessage("earlier line");
    const chat = layout.element.querySelector<HTMLTextAreaElement>('[data-testid="chat-line"]')!;
    const log = layout.element.querySelector<HTMLElement>('[data-testid="message-log"]')!;
    chat.value = "who wrote this?";
    chat.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
    const lines = Array.from(log.querySelectorAll(".message-line")).map((n) => n.textContent);
    expect(lines).toEqual(["earlier line", "who wrote this?"]);
    expect(chat.value).toBe("");
    expect(document.activeElement).toBe(chat);
  });

  it("keeps the log scrolled to its newest line", () => {
    const layout = new AppLayout({});
    document.body.append(layout.element);
    const log = layout.element.querySelector<HTMLElement>('[data-testid="message-log"]')!;
    Object.defineProperty(log, "scrollHeight", { value: 400, configurable: true });
    layout.pushMessage("last line");
    expect(log.scrollTop).toBe(400);
  });

  it("lays a pushed multi-line message out as one log line per text line", () => {
    const layout = new AppLayout({});
    document.body.append(layout.element);
    layout.pushMessage("a reply\nover several\nlines");
    const log = layout.element.querySelector<HTMLElement>('[data-testid="message-log"]')!;
    const lines = Array.from(log.querySelectorAll(".message-line")).map((n) => n.textContent);
    expect(lines).toEqual(["a reply", "over several", "lines"]);
  });

  it("ignores an empty or whitespace-only chat prompt and shift-enter", () => {
    const onPrompt = vi.fn();
    const layout = new AppLayout({ onPrompt });
    document.body.append(layout.element);
    const chat = layout.element.querySelector<HTMLTextAreaElement>('[data-testid="chat-line"]')!;
    chat.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
    expect(onPrompt).not.toHaveBeenCalled();
    chat.value = "   ";
    chat.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
    expect(onPrompt).not.toHaveBeenCalled();
    chat.value = "draft text";
    chat.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", shiftKey: true, bubbles: true }));
    expect(onPrompt).not.toHaveBeenCalled();
    expect(chat.value).toBe("draft text");
  });

  it("collapses the chat box and shows the response spinner while the model is working", () => {
    const layout = new AppLayout({});
    document.body.append(layout.element);
    layout.beginResponse();
    const chat = layout.element.querySelector<HTMLTextAreaElement>('[data-testid="chat-line"]')!;
    const panel = layout.element.querySelector<HTMLElement>('[data-testid="panel-message"]')!;
    const area = layout.element.querySelector<HTMLElement>('[data-testid="panel-response"]')!;
    expect(chat.hidden).toBe(true);
    expect(area.hidden).toBe(false);
    expect(area.querySelector('[data-testid="response-spinner"]')).not.toBeNull();
    const ids = Array.from(panel.children).map((n) => (n as HTMLElement).dataset.testid);
    expect(ids).toEqual(["message-log", "panel-response", "chat-line"]);
  });

  it("shows the parsed reply in the response area and brings the chat box back under it", () => {
    const highlight = vi.fn();
    const layout = new AppLayout({ responseFunctions: { highlight } });
    document.body.append(layout.element);
    layout.beginResponse();
    layout.showResponse([
      { text: "Hello world!" },
      { button: { label: "Highlight sentence", function: "highlight", args: { chapter_id: "c1" } } },
    ]);
    const chat = layout.element.querySelector<HTMLTextAreaElement>('[data-testid="chat-line"]')!;
    const area = layout.element.querySelector<HTMLElement>('[data-testid="panel-response"]')!;
    expect(chat.hidden).toBe(false);
    expect(area.textContent).toContain("Hello world!");
    const found = Array.from(area.querySelectorAll<HTMLButtonElement>("button")).find(
      (el) => el.textContent === "Highlight sentence",
    )!;
    found.click();
    expect(highlight).toHaveBeenCalledWith({ chapter_id: "c1" });
  });

  it("drops the response area and restores the chat box when the prompt fails", () => {
    const layout = new AppLayout({});
    document.body.append(layout.element);
    layout.beginResponse();
    layout.cancelResponse();
    const chat = layout.element.querySelector<HTMLTextAreaElement>('[data-testid="chat-line"]')!;
    const area = layout.element.querySelector<HTMLElement>('[data-testid="panel-response"]')!;
    expect(chat.hidden).toBe(false);
    expect(area.hidden).toBe(true);
    expect(area.textContent).toBe("");
  });

  it("grows the busy panel to show every prompt line and the spinner line", () => {
    const onPrompt = vi.fn();
    const layout = new AppLayout({ onPrompt });
    document.body.append(layout.element);
    const chat = layout.element.querySelector<HTMLTextAreaElement>('[data-testid="chat-line"]')!;
    const log = layout.element.querySelector<HTMLElement>('[data-testid="message-log"]')!;
    const panel = layout.element.querySelector<HTMLElement>('[data-testid="panel-message"]')!;
    expect(parseInt(panel.style.height, 10)).toBe(24);
    chat.value = "one\ntwo\nthree";
    chat.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
    layout.beginResponse();
    expect(parseInt(panel.style.height, 10)).toBe(88);
    expect(log.hidden).toBe(false);
    expect(chat.hidden).toBe(true);
  });

  it("leaves an already-tall panel alone while the model is busy", () => {
    const onPrompt = vi.fn();
    const layout = new AppLayout({ onPrompt });
    document.body.append(layout.element);
    const chat = layout.element.querySelector<HTMLTextAreaElement>('[data-testid="chat-line"]')!;
    const panel = layout.element.querySelector<HTMLElement>('[data-testid="panel-message"]')!;
    drag(bottomHandle(layout), 100, 500, 0, -100);
    const before = panel.style.height;
    chat.value = "hello";
    chat.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
    layout.beginResponse();
    expect(panel.style.height).toBe(before);
  });

  it("grows the panel to fit a whole reply, capped at half the window", () => {
    const layout = new AppLayout({});
    document.body.append(layout.element);
    Object.defineProperty(window, "innerHeight", { value: 200, configurable: true });
    const panel = layout.element.querySelector<HTMLElement>('[data-testid="panel-message"]')!;
    layout.beginResponse();
    layout.showResponse(
      Array.from({ length: 10 }, (_, i) => ({ text: `line ${i}` })),
    );
    expect(parseInt(panel.style.height, 10)).toBe(100);
  });

  it("shows the save button when there are unsaved changes", () => {
    const layout = new AppLayout({});
    document.body.append(layout.element);
    const save = layout.element.querySelector<HTMLElement>('[data-testid="save-button"]')!;
    expect(save.hidden).toBe(true);
    layout.setDirty(true);
    expect(save.hidden).toBe(false);
    layout.setDirty(false);
    expect(save.hidden).toBe(true);
  });

  it("describes the save button with an icon and tooltip", () => {
    const layout = new AppLayout({});
    document.body.append(layout.element);
    const save = layout.element.querySelector<HTMLButtonElement>('[data-testid="save-button"]')!;
    expect(save.title).toBe("Save the chapter");
    expect(save.getAttribute("aria-label")).toBe("Save the chapter");
    expect(save.querySelector("svg.save-icon")).not.toBeNull();
    expect(save.textContent).toBe("");
  });

  it("saves the chapter when the save button is clicked", () => {
    const onSave = vi.fn();
    const layout = new AppLayout({ onSave });
    document.body.append(layout.element);
    layout.setDirty(true);
    layout.element
      .querySelector<HTMLButtonElement>('[data-testid="save-button"]')!
      .dispatchEvent(new MouseEvent("click", { bubbles: true }));
    expect(onSave).toHaveBeenCalledTimes(1);
  });

  it("puts the save button and username with the cog on the right", () => {
    const layout = new AppLayout({});
    document.body.append(layout.element);
    layout.setDirty(true);
    layout.setUser("brian");
    const right = layout.element.querySelector<HTMLElement>(".menubar-right")!;
    const [save, settings, username] = Array.from(right.children) as HTMLElement[];
    expect(save.dataset.testid).toBe("save-button");
    expect(settings.querySelector('[data-testid="menu-Settings"]')).not.toBeNull();
    expect(username.querySelector('[data-testid="user-label"]')).not.toBeNull();
  });

  it("renders the signed-in username in the menubar", () => {
    const layout = new AppLayout({});
    document.body.append(layout.element);
    layout.setUser("brian");
    const label = layout.element.querySelector<HTMLElement>('[data-testid="user-label"]')!;
    expect(label).not.toBeNull();
    expect(label.textContent).toBe("brian");
  });

  it("replaces the username label on setUser again", () => {
    const layout = new AppLayout({});
    document.body.append(layout.element);
    layout.setUser("brian");
    layout.setUser("kate");
    const label = layout.element.querySelector<HTMLElement>('[data-testid="user-label"]')!;
    expect(label.textContent).toBe("kate");
    expect(layout.element.querySelectorAll('[data-testid="user-label"]')).toHaveLength(1);
  });

  it("renders the signed-in username as a button with a user icon and the name", () => {
    const layout = new AppLayout({});
    document.body.append(layout.element);
    layout.setUser("brian");
    const button = layout.element.querySelector<HTMLButtonElement>('[data-testid="user-label"]')!;
    expect(button).toBeInstanceOf(HTMLButtonElement);
    expect(button.querySelector("svg.user-icon")).not.toBeNull();
    expect(button.textContent).toBe("brian");
    expect(button.hidden).toBe(false);
  });

  it("hides the user menu while no one is signed in", () => {
    const layout = new AppLayout({});
    document.body.append(layout.element);
    const button = layout.element.querySelector<HTMLButtonElement>('[data-testid="user-label"]')!;
    expect(button.closest(".menu")?.hasAttribute("hidden")).toBe(true);
  });

  it("opens the user menu as a menubar dropdown, not in the response area", () => {
    const layout = new AppLayout({});
    document.body.append(layout.element);
    layout.setUser("brian");
    layout.element.querySelector<HTMLButtonElement>('[data-testid="user-label"]')!.click();

    const dropdown = layout.element.querySelector<HTMLElement>('[data-testid="menu-user-dropdown"]')!;
    expect(dropdown.classList.contains("menu-dropdown--open")).toBe(true);
    const labels = Array.from(dropdown.querySelectorAll(".menu-item")).map((n) => n.textContent);
    expect(labels).toEqual(["Sign out", "Settings"]);
    expect(layout.element.querySelector<HTMLElement>('[data-testid="panel-response"]')!.hidden).toBe(true);
  });

  it("reports the user menu's Sign out to onSignOut", () => {
    const onSignOut = vi.fn();
    const layout = new AppLayout({ onSignOut });
    document.body.append(layout.element);
    layout.element
      .querySelector('[data-testid="menu-item-sign-out"]')!
      .dispatchEvent(new MouseEvent("click", { bubbles: true }));
    expect(onSignOut).toHaveBeenCalledTimes(1);
  });

  it("disables the mode toggle by default and enables it when raw markdown is allowed", () => {
    const layout = new AppLayout({});
    document.body.append(layout.element);
    const toggle = layout.element.querySelector<HTMLButtonElement>('[data-testid="mode-toggle"]')!;
    expect(toggle.disabled).toBe(true);

    layout.setRawMarkdownEnabled(true);
    expect(toggle.disabled).toBe(false);
  });

  it("drops the editor back to WYSIWYG when raw markdown is turned off while raw", () => {
    const onMode = vi.fn();
    const layout = new AppLayout({ onMode });
    document.body.append(layout.element);
    layout.setRawMarkdownEnabled(true);
    layout.setMode("raw");
    expect(layout.mode).toBe("raw");

    layout.setRawMarkdownEnabled(false);
    expect(layout.mode).toBe("wysiwyg");
    expect(onMode).toHaveBeenLastCalledWith("wysiwyg");
  });
});