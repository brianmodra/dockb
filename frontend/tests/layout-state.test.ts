import { afterEach, describe, expect, it, vi } from "vitest";
import { AppLayout } from "../src/renderer/layout/layout";

afterEach(() => {
  document.body.replaceChildren();
  vi.restoreAllMocks();
});

describe("AppLayout state restore", () => {
  it("starts in wysiwyg mode by default", () => {
    const layout = new AppLayout();
    document.body.append(layout.element);
    expect(layout.mode).toBe("wysiwyg");
  });

  it("restores panel widths and edit mode from saved state", () => {
    const layout = new AppLayout();
    document.body.append(layout.element);
    layout.restoreState({ panel_widths: { left: 300, message: 48 }, edit_mode: "raw" });

    expect(layout.mode).toBe("raw");
    expect(layout.panelWidths().left).toBe(300);
    expect(layout.panelWidths().message).toBe(48);
    expect(layout.element.querySelector<HTMLElement>("[data-testid='panel-left']")?.style.width).toBe("300px");
    expect(layout.element.querySelector<HTMLElement>("[data-testid='panel-edit']")?.getAttribute("data-mode")).toBe("raw");
  });

  it("reports mode changes to the editor via onMode", () => {
    const onMode = vi.fn();
    const layout = new AppLayout({ onMode });
    layout.setMode("wysiwyg");
    layout.setMode("raw");
    expect(onMode).toHaveBeenCalledWith("raw");
  });

  it("wires File → Open in the menubar to onOpen", () => {
    const onOpen = vi.fn();
    const layout = new AppLayout({ onOpen });
    document.body.append(layout.element);
    layout.element.querySelector<HTMLElement>("[data-testid='menu-File']")?.click();
    layout.element.querySelector<HTMLElement>("[data-testid='menu-item-open']")?.click();
    expect(onOpen).toHaveBeenCalledTimes(1);
  });

  it("clamps restored widths to the panel minimums", () => {
    const layout = new AppLayout();
    document.body.append(layout.element);
    layout.restoreState({ panel_widths: { left: 8, right: 2, message: 3 } });

    expect(layout.panelWidths().left).toBe(120);
    expect(layout.panelWidths().right).toBe(10);
    expect(layout.panelWidths().message).toBe(24);
  });

  it("reports width changes through onWidthsChange after restore", () => {
    const onWidthsChange = vi.fn();
    const layout = new AppLayout({ onWidthsChange });
    layout.restoreState({ panel_widths: { left: 260 } });
    expect(onWidthsChange).toHaveBeenCalledWith(expect.objectContaining({ left: 260 }));
  });

  it("reports width changes through onWidthsChange when the user drags a seam", () => {
    const onWidthsChange = vi.fn();
    const layout = new AppLayout({ onWidthsChange });
    document.body.append(layout.element);
    const left = layout.element.querySelector('[data-testid="panel-left"]') as HTMLElement;
    const handle = layout.element.querySelector<HTMLElement>('[data-testid="resize-handle-v-left"]')!;
    const startWidth = parseInt(left.style.width, 10);

    handle.dispatchEvent(new MouseEvent("mousedown", { clientX: 200, clientY: 100, bubbles: true }));
    window.dispatchEvent(new MouseEvent("mousemove", { clientX: 260, clientY: 100, bubbles: true }));
    window.dispatchEvent(new MouseEvent("mouseup", { bubbles: true }));

    expect(onWidthsChange).toHaveBeenCalledWith(expect.objectContaining({ left: startWidth + 60 }));
  });
});