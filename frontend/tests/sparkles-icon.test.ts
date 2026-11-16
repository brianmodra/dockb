import { describe, expect, it } from "vitest";
import { createSparklesIcon } from "../src/renderer/layout/sparklesIcon";

describe("createSparklesIcon", () => {
  it("builds a Lucide sparkles SVG", () => {
    const icon = createSparklesIcon();

    expect(icon).toBeInstanceOf(SVGElement);
    expect(icon.tagName.toLowerCase()).toBe("svg");
    expect(icon.getAttribute("class")).toBe("chat-sparkle");
    expect(icon.getAttribute("viewBox")).toBe("0 0 24 24");
    expect(icon.getAttribute("aria-hidden")).toBe("true");
    expect(icon.getAttribute("stroke")).toBe("currentColor");
    expect(Array.from(icon.querySelectorAll("path")).map((path) => path.getAttribute("d"))).toEqual([
      "M11.017 2.814a1 1 0 0 1 1.966 0l1.051 5.558a2 2 0 0 0 1.594 1.594l5.558 1.051a1 1 0 0 1 0 1.966l-5.558 1.051a2 2 0 0 0-1.594 1.594l-1.051 5.558a1 1 0 0 1-1.966 0l-1.051-5.558a2 2 0 0 0-1.594-1.594l-5.558-1.051a1 1 0 0 1 0-1.966l5.558-1.051a2 2 0 0 0 1.594-1.594z",
      "M20 2v4",
      "M22 4h-4",
    ]);
    const circle = icon.querySelector("circle");
    expect(circle?.getAttribute("cx")).toBe("4");
    expect(circle?.getAttribute("cy")).toBe("20");
    expect(circle?.getAttribute("r")).toBe("2");
  });
});
