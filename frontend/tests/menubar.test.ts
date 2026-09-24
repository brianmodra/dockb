import { afterEach, describe, expect, it, vi } from "vitest";
import { buildMenubar } from "../src/renderer/layout/menubar";

afterEach(() => {
  document.body.replaceChildren();
});

function openMenu(bar: { element: HTMLElement }, key: string): void {
  bar.element.querySelector<HTMLElement>(`[data-testid="menu-${key}"]`)?.click();
}

function dropdown(bar: { element: HTMLElement }, key: string): HTMLElement {
  return bar.element.querySelector<HTMLElement>(`[data-testid="menu-${key}-dropdown"]`)!;
}

describe("menubar", () => {
  it("renders the in-window File, Mode and Settings (cog) menus", () => {
    const bar = buildMenubar({});
    document.body.append(bar.element);
    expect(bar.element.getAttribute("data-testid")).toBe("menubar");
    expect(bar.element.querySelector('[data-testid="menu-File"]')?.textContent).toBe("File");
    expect(bar.element.querySelector('[data-testid="menu-Mode"]')?.textContent).toBe("Mode");
    expect(bar.element.querySelector('[data-testid="menu-Settings"]')?.textContent).toBe("⚙");
  });

  it("opens File with Open, Save and Quit", () => {
    const bar = buildMenubar({});
    document.body.append(bar.element);
    openMenu(bar, "File");
    const itemLabels = Array.from(dropdown(bar, "File").querySelectorAll(".menu-item")).map(
      (n) => n.textContent,
    );
    expect(itemLabels).toEqual(["Open", "Save", "Quit"]);
  });

  it("safely handles File clicks (Open/Save/Quit wire later)", () => {
    const bar = buildMenubar({});
    document.body.append(bar.element);
    openMenu(bar, "File");
    for (const key of ["open", "save", "quit"]) {
      expect(() =>
        bar.element
          .querySelector(`[data-testid="menu-item-${key}"]`)
          ?.dispatchEvent(new MouseEvent("click", { bubbles: true })),
      ).not.toThrow();
    }
  });

  it("reports File → Open to onOpen", () => {
    const onOpen = vi.fn();
    const bar = buildMenubar({ onOpen });
    document.body.append(bar.element);
    openMenu(bar, "File");
    bar.element.querySelector('[data-testid="menu-item-open"]')?.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    expect(onOpen).toHaveBeenCalledTimes(1);
  });

  it("reports File → Quit to onQuit", () => {
    const onQuit = vi.fn();
    const bar = buildMenubar({ onQuit });
    document.body.append(bar.element);
    openMenu(bar, "File");
    bar.element.querySelector('[data-testid="menu-item-quit"]')?.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    expect(onQuit).toHaveBeenCalledTimes(1);
  });

  it("reports File → Save to onSave", () => {
    const onSave = vi.fn();
    const bar = buildMenubar({ onSave });
    document.body.append(bar.element);
    openMenu(bar, "File");
    bar.element.querySelector('[data-testid="menu-item-save"]')?.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    expect(onSave).toHaveBeenCalledTimes(1);
  });

  it("offers WYSIWYG and Raw MD modes, reporting the selection", () => {
    const onMode = vi.fn();
    const bar = buildMenubar({ onMode });
    document.body.append(bar.element);
    openMenu(bar, "Mode");
    const items = Array.from(dropdown(bar, "Mode").querySelectorAll(".menu-item")).map(
      (n) => n.textContent,
    );
    expect(items).toEqual(["WYSIWYG", "Raw MD"]);
    bar.element.querySelector('[data-testid="menu-item-raw"]')?.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    expect(onMode).toHaveBeenCalledWith("raw");
    openMenu(bar, "Mode");
    bar.element.querySelector('[data-testid="menu-item-wysiwyg"]')?.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    expect(onMode).toHaveBeenCalledWith("wysiwyg");
  });

  it("closes the dropdown when clicking outside the menu", () => {
    const bar = buildMenubar({});
    document.body.append(bar.element);
    openMenu(bar, "File");
    expect(dropdown(bar, "File").classList.contains("menu-dropdown--open")).toBe(true);

    document.body.dispatchEvent(new MouseEvent("mousedown", { bubbles: true, clientX: 500, clientY: 500 }));
    expect(dropdown(bar, "File").classList.contains("menu-dropdown--open")).toBe(false);
  });

  it("keeps the dropdown open when clicking inside the menu", () => {
    const bar = buildMenubar({});
    document.body.append(bar.element);
    openMenu(bar, "File");

    dropdown(bar, "File").dispatchEvent(new MouseEvent("mousedown", { bubbles: true }));
    expect(dropdown(bar, "File").classList.contains("menu-dropdown--open")).toBe(true);
  });

  it("closes the dropdown on Escape", () => {
    const bar = buildMenubar({});
    document.body.append(bar.element);
    openMenu(bar, "File");

    window.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" }));
    expect(dropdown(bar, "File").classList.contains("menu-dropdown--open")).toBe(false);
  });

  it("reopens a closed dropdown and can close it again", () => {
    const bar = buildMenubar({});
    document.body.append(bar.element);
    openMenu(bar, "File");
    openMenu(bar, "File");
    expect(dropdown(bar, "File").classList.contains("menu-dropdown--open")).toBe(false);
    openMenu(bar, "File");
    expect(dropdown(bar, "File").classList.contains("menu-dropdown--open")).toBe(true);
  });

  it("renders Settings with a General item that does nothing", () => {
    const bar = buildMenubar({});
    document.body.append(bar.element);
    openMenu(bar, "Settings");
    const item = dropdown(bar, "Settings").querySelector<HTMLElement>(".menu-item");
    expect(item?.textContent).toBe("General");
    expect(() => item?.dispatchEvent(new MouseEvent("click", { bubbles: true }))).not.toThrow();
  });
});