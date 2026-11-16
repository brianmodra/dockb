import { describe, expect, it } from "vitest";
import { createUserRoundIcon } from "../src/renderer/layout/userIcon";

describe("createUserRoundIcon", () => {
  it("builds a Lucide user-round SVG", () => {
    const icon = createUserRoundIcon();

    expect(icon).toBeInstanceOf(SVGElement);
    expect(icon.tagName.toLowerCase()).toBe("svg");
    expect(icon.getAttribute("class")).toBe("user-icon");
    expect(icon.getAttribute("viewBox")).toBe("0 0 24 24");
    expect(icon.getAttribute("aria-hidden")).toBe("true");
    expect(icon.getAttribute("focusable")).toBe("false");

    const head = icon.querySelector("circle");
    expect(head?.getAttribute("cx")).toBe("12");
    expect(head?.getAttribute("cy")).toBe("8");
    expect(head?.getAttribute("r")).toBe("5");

    expect(Array.from(icon.querySelectorAll("path")).map((path) => path.getAttribute("d"))).toEqual([
      "M20 21a8 8 0 0 0-16 0",
    ]);
  });
});
