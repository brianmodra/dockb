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

  it("starts with the right panel at ten pixels and the seam still available", () => {
    const layout = new AppLayout({});
    document.body.append(layout.element);
    const right = layout.element.querySelector<HTMLElement>('[data-testid="panel-right"]')!;
    expect(right.style.width).toBe("10px");
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
    expect(parseInt(right.style.width, 10)).toBe(90);
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

  it("reports mode through the menubar and updates the edit panel", () => {
    const layout = new AppLayout({});
    document.body.append(layout.element);
    layout.element.querySelector<HTMLElement>('[data-testid="menu-Mode"]')?.click();
    layout.element.querySelector('[data-testid="menu-item-raw"]')?.dispatchEvent(new MouseEvent("click", { bubbles: true }));
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

  it("shows the dirty indicator when there are unsaved changes", () => {
    const layout = new AppLayout({});
    document.body.append(layout.element);
    const badge = layout.element.querySelector<HTMLElement>('[data-testid="dirty-indicator"]')!;
    expect(badge.hidden).toBe(true);
    layout.setDirty(true);
    expect(badge.hidden).toBe(false);
    layout.setDirty(false);
    expect(badge.hidden).toBe(true);
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
});