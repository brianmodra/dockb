import { afterEach, describe, expect, it, vi } from "vitest";
import { openContextMenu } from "../src/renderer/layout/contextMenu";

afterEach(() => {
  document.body.replaceChildren();
  vi.restoreAllMocks();
});

describe("context menu", () => {
  it("renders items at the pointer and reports selection", () => {
    const onEdit = vi.fn();
    const handle = openContextMenu(40, 50, [
      { label: "Edit", onSelect: onEdit },
      { label: "Rename", onSelect: vi.fn() },
    ]);
    document.body.append(handle.element);

    expect(handle.element.dataset.testid).toBe("context-menu");
    const labels = Array.from(handle.element.querySelectorAll(".context-item")).map((n) => n.textContent);
    expect(labels).toEqual(["Edit", "Rename"]);
    expect(handle.element.style.left).toBe("40px");
    expect(handle.element.style.top).toBe("50px");

    handle.element.querySelector<HTMLElement>(".context-item")!.click();
    expect(onEdit).toHaveBeenCalled();
  });

  it("closes when a background click happens", () => {
    const handle = openContextMenu(0, 0, [{ label: "Edit", onSelect: vi.fn() }]);
    document.body.append(handle.element);

    document.body.dispatchEvent(new MouseEvent("mousedown", { bubbles: true, clientX: 300, clientY: 300 }));
    expect(handle.element.isConnected).toBe(false);
  });

  it("closes on Esc", () => {
    const handle = openContextMenu(0, 0, [{ label: "Edit", onSelect: vi.fn() }]);
    document.body.append(handle.element);

    window.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" }));
    expect(handle.element.isConnected).toBe(false);
  });

  it("keeps the menu open when clicking inside it", () => {
    const handle = openContextMenu(0, 0, [{ label: "Edit", onSelect: vi.fn() }]);
    document.body.append(handle.element);

    handle.element.dispatchEvent(new MouseEvent("mousedown", { bubbles: true }));
    const removed = handle.element.isConnected;
    expect(removed).toBe(true);
  });

  it("close() removes the menu", () => {
    const handle = openContextMenu(0, 0, [{ label: "Edit", onSelect: vi.fn() }]);
    document.body.append(handle.element);
    handle.close();
    expect(handle.element.isConnected).toBe(false);
  });
});