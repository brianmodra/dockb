import { afterEach, describe, expect, it, vi } from "vitest";
import { ResizeHandle } from "../src/renderer/layout/ResizeHandle";

afterEach(() => {
  document.body.replaceChildren();
  vi.restoreAllMocks();
});

function mousedown(el: HTMLElement, x: number, y: number): void {
  el.dispatchEvent(new MouseEvent("mousedown", { clientX: x, clientY: y, bubbles: true }));
}

function mousemove(x: number, y: number): void {
  window.dispatchEvent(new MouseEvent("mousemove", { clientX: x, clientY: y, bubbles: true }));
}

function mouseup(): void {
  window.dispatchEvent(new MouseEvent("mouseup", { bubbles: true }));
}

describe("ResizeHandle", () => {
  it("renders a vertical seam with a grip and three bars", () => {
    const handle = new ResizeHandle({ orientation: "vertical" });
    document.body.append(handle.element);
    expect(handle.element.getAttribute("data-testid")).toBe("resize-handle-vertical");
    expect(handle.element.querySelector(".resize-grip")).not.toBeNull();
    expect(handle.element.querySelectorAll(".resize-bar")).toHaveLength(3);
  });

  it("renders a horizontal seam with the same parametric shape", () => {
    const handle = new ResizeHandle({ orientation: "horizontal" });
    document.body.append(handle.element);
    expect(handle.element.getAttribute("data-testid")).toBe("resize-handle-horizontal");
    expect(handle.element.querySelectorAll(".resize-bar")).toHaveLength(3);
  });

  it("reports horizontal drag deltas as the pointer moves", () => {
    const onDrag = vi.fn();
    const handle = new ResizeHandle({ orientation: "vertical", onDrag });
    document.body.append(handle.element);
    mousedown(handle.element, 100, 100);
    mousemove(140, 100);
    expect(onDrag).toHaveBeenCalledWith(40);
    mousemove(130, 100);
    expect(onDrag).toHaveBeenCalledWith(-10);
  });

  it("reports vertical drag deltas for the horizontal orientation", () => {
    const onDrag = vi.fn();
    const handle = new ResizeHandle({ orientation: "horizontal", onDrag });
    document.body.append(handle.element);
    mousedown(handle.element, 100, 100);
    mousemove(100, 124);
    expect(onDrag).toHaveBeenCalledWith(24);
  });

  it("highlights while a drag is held and releases on mouseup", () => {
    const onDragEnd = vi.fn();
    const handle = new ResizeHandle({ orientation: "vertical", onDragEnd });
    document.body.append(handle.element);
    expect(handle.element.classList.contains("is-dragging")).toBe(false);
    mousedown(handle.element, 0, 0);
    expect(handle.element.classList.contains("is-dragging")).toBe(true);
    mouseup();
    expect(handle.element.classList.contains("is-dragging")).toBe(false);
    expect(onDragEnd).toHaveBeenCalledOnce();
  });

  it("ignores drags that never start on the handle", () => {
    const onDrag = vi.fn();
    new ResizeHandle({ orientation: "vertical", onDrag });
    mousemove(50, 50);
    expect(onDrag).not.toHaveBeenCalled();
  });
});