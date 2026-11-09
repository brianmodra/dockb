import { describe, expect, it } from "vitest";
import { createSpinner } from "../src/renderer/layout/spinner";

describe("createSpinner", () => {
  it("builds an animated Lucide loader-circle SVG", () => {
    const spinner = createSpinner();

    expect(spinner).toBeInstanceOf(SVGElement);
    expect(spinner.tagName.toLowerCase()).toBe("svg");
    expect(spinner.getAttribute("class")).toBe("spinning-loader");
    expect(spinner.getAttribute("viewBox")).toBe("0 0 24 24");
    expect(spinner.getAttribute("aria-hidden")).toBe("true");
    expect(spinner.querySelector("path")?.getAttribute("d")).toBe(
      "M21 12a9 9 0 1 1-6.219-8.56",
    );
  });
});
