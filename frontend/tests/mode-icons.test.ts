import { describe, expect, it } from "vitest";
import { createALargeSmallIcon, createMarkdownIcon } from "../src/renderer/layout/modeIcons";

describe("createMarkdownIcon", () => {
  it("builds a Lucide markdown SVG", () => {
    const icon = createMarkdownIcon();

    expect(icon).toBeInstanceOf(SVGElement);
    expect(icon.tagName.toLowerCase()).toBe("svg");
    expect(icon.getAttribute("class")).toBe("mode-icon");
    expect(icon.getAttribute("viewBox")).toBe("0 0 24 24");
    expect(icon.getAttribute("aria-hidden")).toBe("true");
    expect(icon.getAttribute("focusable")).toBe("false");

    const rect = icon.querySelector("rect");
    expect(rect?.getAttribute("width")).toBe("20");
    expect(rect?.getAttribute("height")).toBe("14");
    expect(rect?.getAttribute("x")).toBe("2");
    expect(rect?.getAttribute("y")).toBe("5");
    expect(rect?.getAttribute("rx")).toBe("2");

    expect(Array.from(icon.querySelectorAll("path")).map((path) => path.getAttribute("d"))).toEqual([
      "M6 15V9l3 3 3-3v6",
      "M17 9v6",
      "m15 13 2 2 2-2",
    ]);
  });
});

describe("createALargeSmallIcon", () => {
  it("builds a Lucide a-large-small SVG", () => {
    const icon = createALargeSmallIcon();

    expect(icon).toBeInstanceOf(SVGElement);
    expect(icon.tagName.toLowerCase()).toBe("svg");
    expect(icon.getAttribute("class")).toBe("mode-icon");
    expect(icon.getAttribute("viewBox")).toBe("0 0 24 24");
    expect(icon.getAttribute("aria-hidden")).toBe("true");
    expect(icon.getAttribute("focusable")).toBe("false");

    expect(Array.from(icon.querySelectorAll("path")).map((path) => path.getAttribute("d"))).toEqual([
      "m15 16 2.536-7.328a1.02 1.02 1 0 1 1.928 0L22 16",
      "M15.697 14h5.606",
      "m2 16 4.039-9.69a.5.5 0 0 1 .923 0L11 16",
      "M3.304 13h6.392",
    ]);
  });
});
