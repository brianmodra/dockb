// @vitest-environment node
import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const css = readFileSync(
  fileURLToPath(new URL("../src/renderer/styles.css", import.meta.url)),
  "utf8",
);

function ruleBody(selector: string): string {
  const escaped = selector.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const match = css.match(new RegExp(`${escaped}\\s*\\{([\\s\\S]*?)\\}`));
  if (!match) {
    throw new Error(`no rule for ${selector}`);
  }
  return match[1];
}

describe("theme colours", () => {
  it("colours the scrollbar thumb #c7d3c0", () => {
    expect(ruleBody("::-webkit-scrollbar-thumb")).toContain("#c7d3c0");
  });

  it("colours the menubar background #e0e7ff", () => {
    expect(ruleBody('[data-testid="menubar"]')).toContain("#e0e7ff");
  });

  it("highlights a dragged resize handle #a5b4fc", () => {
    expect(ruleBody(".resize-handle.is-dragging")).toContain("#a5b4fc");
  });

  it("colours the resize grip #3730a3", () => {
    expect(ruleBody(".resize-grip")).toContain("#3730a3");
  });

  it("colours the resize grip bars #c7d3c0", () => {
    expect(ruleBody(".resize-bar")).toContain("#c7d3c0");
  });

  it("colours the chat box background #f6f0f0", () => {
    expect(ruleBody(".chat-line")).toContain("#f6f0f0");
  });

  it("colours the message log and response area #eff3f2", () => {
    expect(ruleBody(".message-log")).toContain("#eff3f2");
    expect(ruleBody(".response-area")).toContain("#eff3f2");
  });

  it("colours the sparkles icon #ebc96d", () => {
    expect(ruleBody(".chat-sparkle")).toContain("#ebc96d");
  });

  it("styles the chapter header like the chapter list", () => {
    const header = ruleBody(".edit-panel .chapter-header");
    expect(header).toContain("font-family: var(--font-ui)");
    expect(header).toContain("font-size: 12px");
  });

  it("enlarges the settings cog to 18px", () => {
    expect(ruleBody('[data-testid="menu-Settings"]')).toContain("font-size: 18px");
  });
});
