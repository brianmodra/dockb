import { describe, expect, it } from "vitest";
import {
  mapRawProofreadingDiagnostics,
  rawProofreadingParagraphAt,
  rawProofreadingParagraphFor,
} from "../src/renderer/layout/rawProofreading";

const CANONICAL = [
  "---",
  "title: Test",
  "---",
  "",
  '<span data-par-id="p-1">',
  "teh cat",
  "&amp; dog",
  "</span>",
  "",
  '<span data-par-id="p-2">',
  "Other",
  "</span>",
  "",
].join("\n");

function cursorIn(text: string, needle: string): number {
  const at = text.indexOf(needle);
  if (at < 0) {
    throw new Error(`missing ${needle}`);
  }
  return at;
}

describe("raw proofreading paragraphs", () => {
  it("maps the paragraph under the cursor, stripping span markup", () => {
    const paragraph = rawProofreadingParagraphAt(CANONICAL, cursorIn(CANONICAL, "teh cat"));

    expect(paragraph?.context.paragraphId).toBe("p-1");
    expect(paragraph?.context.paragraphIndex).toBe(0);
    expect(paragraph?.context.text).toBe("teh cat\n& dog");
    expect(paragraph?.context.focus).toEqual({ start: 0, end: 7 });
  });

  it("strips inline span markup without losing offsets", () => {
    const buffer = '<span data-par-id="p-1">\nA <span data-spo>secret</span> word\n</span>';
    const paragraph = rawProofreadingParagraphAt(buffer, cursorIn(buffer, "secret"));

    expect(paragraph?.context.text).toBe("A secret word");
    const mapped = mapRawProofreadingDiagnostics(paragraph!, [
      { start: 2, end: 8, message: "Hidden", rule_id: "SPOILER", severity: "info" },
    ]);
    expect(mapped[0]).toMatchObject({
      from: cursorIn(buffer, "secret"),
      to: cursorIn(buffer, "secret") + "secret".length,
      word: "secret",
    });
  });

  it("keeps the sentence line breaks that the writer sees", () => {
    const paragraph = rawProofreadingParagraphAt(CANONICAL, cursorIn(CANONICAL, "&amp; dog"));

    expect(paragraph?.context.text).toBe("teh cat\n& dog");
    expect(paragraph?.context.focus).toEqual({ start: 8, end: 13 });
  });

  it("numbers paragraphs the way the wysiwyg view does", () => {
    const paragraph = rawProofreadingParagraphAt(CANONICAL, cursorIn(CANONICAL, "Other"));

    expect(paragraph?.context.paragraphId).toBe("p-2");
    expect(paragraph?.context.paragraphIndex).toBe(1);
  });

  it("has no paragraph for the front matter", () => {
    expect(rawProofreadingParagraphAt(CANONICAL, 0)).toBeNull();
  });

  it("maps diagnostics back through entities and markup", () => {
    const paragraph = rawProofreadingParagraphAt(CANONICAL, cursorIn(CANONICAL, "teh cat"));
    if (!paragraph) {
      throw new Error("missing paragraph");
    }
    const mapped = mapRawProofreadingDiagnostics(paragraph, [
      { start: 0, end: 3, message: "Possible spelling mistake", rule_id: "MORFOLOGIK_RULE_EN_US", severity: "warning" },
      { start: 8, end: 9, message: "Use an ampersand", rule_id: "AMPERSAND", severity: "info" },
      { start: 99, end: 100, message: "out of range", rule_id: "BAD", severity: "warning" },
    ]);

    expect(mapped).toHaveLength(2);
    expect(mapped[0]).toMatchObject({
      from: cursorIn(CANONICAL, "teh"),
      to: cursorIn(CANONICAL, "teh") + 3,
      word: "teh",
    });
    expect(mapped[1]).toMatchObject({
      from: cursorIn(CANONICAL, "&amp;"),
      to: cursorIn(CANONICAL, "&amp;") + 5,
      word: "&",
    });
  });

  it("rebuilds the mapping for a captured context", () => {
    const paragraph = rawProofreadingParagraphAt(CANONICAL, cursorIn(CANONICAL, "Other"));
    if (!paragraph) {
      throw new Error("missing paragraph");
    }

    expect(rawProofreadingParagraphFor(CANONICAL, paragraph.context)?.context.text).toBe("Other");
    expect(
      rawProofreadingParagraphFor(CANONICAL, { ...paragraph.context, text: "changed" }),
    ).toBeNull();
  });
});
