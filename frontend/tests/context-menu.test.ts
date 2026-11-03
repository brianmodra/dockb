import { afterEach, describe, expect, it, vi } from "vitest";
import { openContextMenu } from "../src/renderer/layout/contextMenu";

afterEach(() => {
  document.body.replaceChildren();
  vi.restoreAllMocks();
  delete (HTMLElement.prototype as { offsetWidth?: number }).offsetWidth;
  delete (HTMLElement.prototype as { offsetHeight?: number }).offsetHeight;
  delete (window as { innerHeight?: number }).innerHeight;
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

  it("renders a title above the items that is not a button", () => {
    const handle = openContextMenu(10, 20, [{ label: "Quote", onSelect: vi.fn() }], {
      title: "Edit",
    });

    const title = handle.element.querySelector<HTMLElement>(".context-title")!;
    expect(title.textContent).toBe("Edit");
    expect(title.tagName).not.toBe("BUTTON");
    const labels = Array.from(handle.element.querySelectorAll(".context-item")).map((n) => n.textContent);
    expect(labels).toEqual(["Quote"]);
  });

  it("opens a nested pulldown and highlights the current choice", () => {
    const onReading = vi.fn();
    const handle = openContextMenu(10, 20, [
      {
        label: "Edit",
        children: [
          {
            label: "Quote",
            children: [
              { label: "None" },
              { label: "Reading", checked: true, onSelect: onReading },
              { label: "Writing", onSelect: vi.fn() },
            ],
          },
        ],
      },
    ]);

    const editItem = handle.element.querySelector<HTMLElement>(".context-item")!;
    expect(editItem.textContent).toBe("Edit");
    editItem.click();
    const quoteItem = Array.from(handle.element.querySelectorAll<HTMLElement>(".context-item")).find(
      (n) => n.textContent === "Quote",
    )!;
    expect(quoteItem).not.toBeUndefined();
    quoteItem.click();
    const reading = Array.from(handle.element.querySelectorAll<HTMLElement>(".context-item")).find(
      (n) => n.textContent === "Reading" && n.classList.contains("is-checked"),
    );
    expect(reading).not.toBeUndefined();

    reading!.click();
    expect(onReading).toHaveBeenCalled();
    expect(handle.element.isConnected).toBe(false);
  });

  it("keeps the menu open while walking the submenus", () => {
    const handle = openContextMenu(0, 0, [
      { label: "Edit", children: [{ label: "Quote", children: [{ label: "None" }] }] },
    ]);
    handle.element.querySelector<HTMLElement>(".context-item")!.click();
    Array.from(handle.element.querySelectorAll<HTMLElement>(".context-item"))
      .find((n) => n.textContent === "Quote")!
      .click();
    expect(handle.element.isConnected).toBe(true);
  });

  it("clamps the menu inside the window on both axes", () => {
    Object.defineProperty(HTMLElement.prototype, "offsetWidth", { configurable: true, value: 200 });
    Object.defineProperty(HTMLElement.prototype, "offsetHeight", { configurable: true, value: 300 });
    Object.defineProperty(window, "innerHeight", { configurable: true, value: 768 });

    const handle = openContextMenu(900, 700, [{ label: "Quote", onSelect: vi.fn() }]);
    expect(handle.element.style.left).toBe("824px");
    expect(handle.element.style.top).toBe("468px");
  });

  it("never places the menu above or left of the window", () => {
    Object.defineProperty(HTMLElement.prototype, "offsetWidth", { configurable: true, value: 200 });
    Object.defineProperty(HTMLElement.prototype, "offsetHeight", { configurable: true, value: 300 });
    Object.defineProperty(window, "innerHeight", { configurable: true, value: 768 });

    const handle = openContextMenu(-50, -10, [{ label: "Quote", onSelect: vi.fn() }]);
    expect(handle.element.style.left).toBe("0px");
    expect(handle.element.style.top).toBe("0px");
  });

  it("clamps an open submenu so it stays inside the window too", () => {
    Object.defineProperty(HTMLElement.prototype, "offsetWidth", { configurable: true, value: 200 });
    Object.defineProperty(HTMLElement.prototype, "offsetHeight", { configurable: true, value: 300 });
    Object.defineProperty(window, "innerHeight", { configurable: true, value: 490 });

    const handle = openContextMenu(10, 700, [
      { label: "Edit", children: [{ label: "Quote", children: [{ label: "None" }] }] },
    ]);
    handle.element.querySelector<HTMLElement>(".context-item")!.click();
    const submenu = handle.element.querySelector<HTMLElement>(".context-submenu")!;
    Object.defineProperty(submenu, "offsetHeight", { configurable: true, value: 500 });
    handle.element.querySelector<HTMLElement>(".context-item")!.click();
    handle.element.querySelector<HTMLElement>(".context-item")!.click();

    expect(submenu.style.top).toBe("-190px");
  });
});