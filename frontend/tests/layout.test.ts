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

  it("starts with the right panel at zero width and the seam still available", () => {
    const layout = new AppLayout({});
    document.body.append(layout.element);
    const right = layout.element.querySelector<HTMLElement>('[data-testid="panel-right"]')!;
    expect(right.style.width).toBe("0px");
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

  it("opens the right panel by dragging its seam rightwards", () => {
    const layout = new AppLayout({});
    document.body.append(layout.element);
    const right = layout.element.querySelector<HTMLElement>('[data-testid="panel-right"]')!;
    drag(rightHandle(layout), 900, 100, 80, 0);
    expect(parseInt(right.style.width, 10)).toBe(80);
  });

  it("grows the message panel upward through the bottom seam", () => {
    const layout = new AppLayout({});
    document.body.append(layout.element);
    const message = layout.element.querySelector<HTMLElement>('[data-testid="panel-message"]')!;
    drag(bottomHandle(layout), 100, 500, 0, -60);
    expect(parseInt(message.style.height, 10)).toBeGreaterThan(0);
  });

  it("enforces a minimum left-panel width", () => {
    const layout = new AppLayout({});
    document.body.append(layout.element);
    const left = layout.element.querySelector<HTMLElement>('[data-testid="panel-left"]')!;
    drag(leftHandle(layout), 200, 100, -1000, 0);
    expect(parseInt(left.style.width, 10)).toBeGreaterThanOrEqual(120);
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
});