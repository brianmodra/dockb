import { afterEach, describe, expect, it, vi } from "vitest";
import {
  WysiwygView,
  bufferToDoc,
  docToString,
  findHeadingLines,
} from "../src/renderer/layout/wysiwyg";
import MarkdownIt from "markdown-it";

const md = new MarkdownIt();

afterEach(() => {
  document.body.replaceChildren();
  vi.restoreAllMocks();
});

describe("WysiwygView buffer model", () => {
  it("preserves the buffer byte-for-byte through the paragraph-per-line doc", () => {
    const buffer = "# Act I\n\nChapter text.\n\nNext paragraph.";
    const doc = bufferToDoc(buffer);
    const rendered = docToString(doc);
    expect(rendered).toBe(buffer);
  });

  it("keeps blank lines (empty paragraphs) in the round trip", () => {
    const buffer = "a\n\n\nb";
    expect(docToString(bufferToDoc(buffer))).toBe(buffer);
  });

  it("builds one paragraph per line", () => {
    const doc = bufferToDoc("one\ntwo\nthree") as { childCount: number };
    expect(doc.childCount).toBe(3);
  });

  it("uses a flat doc with no heading semantics", () => {
    const doc = bufferToDoc("# Head");
    expect((doc as { type: { name: string } }).type.name).toBe("doc");
    expect((doc as { childCount: number }).childCount).toBe(1);
  });

  it("parses with paragraph nodes holding raw line text", () => {
    const doc = bufferToDoc("# H1");
    const first = (doc as { child: (i: number) => { type: { name: string }; textContent: string } }).child(
      0,
    );
    expect(first.type.name).toBe("paragraph");
    expect(first.textContent).toBe("# H1");
  });
});

describe("markdown-it heading detection", () => {
  it("marks heading lines and skips plain, fence, and list lines", () => {
    const buffer = [
      "# Title",
      "",
      "Body.",
      "",
      "## Sub",
      "",
      "```",
      "# not a heading",
      "```",
      "* Item",
    ].join("\n");
    const headings = findHeadingLines(buffer, md);
    expect(headings.has(0)).toBe(true);
    expect(headings.has(4)).toBe(true);
    expect(headings.has(2)).toBe(false);
    expect(headings.has(7)).toBe(false);
    expect(headings.has(9)).toBe(false);
  });
});

describe("WysiwygView", () => {
  it("renders into its element and exposes the buffer", () => {
    const view = new WysiwygView();
    document.body.append(view.element);
    view.setContent("hello\nworld");

    expect(view.content()).toBe("hello\nworld");
    expect(view.element.querySelector("p")?.textContent).toBe("hello");
  });

  it("does not fire onChange for programmatic setContent", () => {
    const onChange = vi.fn();
    const view = new WysiwygView({ onChange });
    document.body.append(view.element);
    view.setContent("one");
    view.setContent("two");
    expect(onChange).not.toHaveBeenCalled();
  });

  it("fires onChange with the edited buffer when the user types", () => {
    const onChange = vi.fn();
    const view = new WysiwygView({ onChange });
    document.body.append(view.element);
    view.setContent("a\nb");

    const tr = view.view.state.tr;
    tr.insertText("X", 2);
    view.view.dispatch(tr);

    expect(onChange).toHaveBeenCalledWith("aX\nb");
    expect(view.content()).toBe("aX\nb");
  });

  it("styling marks heading paragraphs through markdown-it decorations", () => {
    const view = new WysiwygView();
    document.body.append(view.element);
    view.setContent("# Title\n\nBody.");

    const heading = view.element.querySelector<HTMLElement>(".prose-heading");
    expect(heading?.textContent).toBe("# Title");
  });

  it("decorates each heading line without skipping non-heading lines", () => {
    const view = new WysiwygView();
    document.body.append(view.element);
    view.setContent("# One\nBody.\n\n## Two");

    const headings = [...view.element.querySelectorAll<HTMLElement>(".prose-heading")];
    expect(headings.map((h) => h.textContent)).toEqual(["# One", "## Two"]);
  });

  it("destroy detaches the editor", () => {
    const view = new WysiwygView();
    document.body.append(view.element);
    view.setContent("x");
    view.destroy();

    expect(view.element.querySelector("p")).toBeNull();
  });
});