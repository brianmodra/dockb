import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { TextSelection } from "prosemirror-state";

beforeAll(() => {
  // jsdom omits getClientRects; ProseMirror needs it to scroll to the selection.
  for (const proto of [
    Node.prototype,
    Element.prototype,
    HTMLElement.prototype,
    CharacterData.prototype,
    Text.prototype,
    Range.prototype,
  ]) {
    (proto as { getClientRects?: () => DOMRectList }).getClientRects ??= () =>
      [] as unknown as DOMRectList;
  }
  (Range.prototype as { getBoundingClientRect?: () => DOMRect }).getBoundingClientRect ??= () =>
    ({ x: 0, y: 0, top: 0, right: 0, bottom: 0, left: 0, width: 0, height: 0 }) as DOMRect;
});
import {
  WysiwygView,
  bufferToDoc,
  bufferToDocWithIds,
  chapterBody,
  docToCanonical,
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

  it("groups consecutive sentence lines into a single paragraph", () => {
    const doc = bufferToDoc("one\ntwo\nthree") as { childCount: number };
    expect(doc.childCount).toBe(1);
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

  it("joins a paragraph's sentence lines with a single space", () => {
    const doc = bufferToDoc("one\ntwo");
    const first = (doc as { child: (i: number) => { type: { name: string }; textContent: string } }).child(
      0,
    );
    expect(first.type.name).toBe("paragraph");
    expect(first.textContent).toBe("one two");
  });

  it("keeps paragraphs separated by a blank line without an empty paragraph", () => {
    const doc = bufferToDoc("a\n\nb") as { childCount: number };
    expect(doc.childCount).toBe(2);
  });

  it("turns a trailing backslash into a hard line break and hides the escape", () => {
    const view = new WysiwygView();
    document.body.append(view.element);
    view.setContent("Line one.\\\nLine two.");

    expect(view.content()).toBe("Line one.\\\nLine two.");
    expect(view.element.querySelector("br")).not.toBeNull();
    expect(view.element.textContent).not.toContain("\\");
  });

  it("splits escaped lines inside a paragraph without empty paragraph blocks", () => {
    const doc = bufferToDoc("first\\\nsecond");
    const first = (doc as { child: (i: number) => { type: { name: string } } }).child(0);
    expect(first.type.name).toBe("paragraph");
    const firstNode = first as unknown as { forEach: (fn: (n: { type: { name: string }; textContent?: string }) => void) => void };
    const names: string[] = [];
    firstNode.forEach((n) => names.push(n.type.name));
    expect(names).toEqual(["text", "hardBreak", "text"]);
  });

  it("renders a blank-line paragraph delimiter as a single newline gap", () => {
    const view = new WysiwygView();
    document.body.append(view.element);
    view.setContent("One.\n\nTwo.");

    const paragraphs = [...view.element.querySelectorAll("p")];
    expect(paragraphs).toHaveLength(2);
    expect(paragraphs.map((p) => p.textContent)).toEqual(["One.", "Two."]);
    expect(view.content()).toBe("One.\n\nTwo.");
  });
});

describe("chapterBody (canonical file → visible body)", () => {
  it("strips the front-matter block", () => {
    const buffer = [
      "---",
      "id: c1",
      "title: Opening 1",
      "---",
      "",
      "Body text.",
    ].join("\n");
    expect(chapterBody(buffer)).toBe("Body text.");
  });

  it("leaves a buffer without front matter untouched", () => {
    expect(chapterBody("# Head\n\nBody.")).toBe("# Head\n\nBody.");
  });

  it("removes paragraph span tags and their own lines", () => {
    const buffer = [
      '<span data-par-id="p-1">',
      "First paragraph line.",
      "Second line.",
      "</span>",
      "",
      '<span data-par-id="p-2">',
      "Next paragraph.",
      "</span>",
    ].join("\n");
    expect(chapterBody(buffer)).toBe("First paragraph line.\nSecond line.\n\nNext paragraph.");
  });

  it("strips inline span tags and unescapes entities", () => {
    const buffer = 'A <span data-par-id="p-1">Tom &amp; Jerry said &quot;hi&quot;</span>.';
    expect(chapterBody(buffer)).toBe('A Tom & Jerry said "hi".');
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
    expect(view.element.querySelector("p")?.textContent).toBe("hello world");
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
    tr.insertText("X", 4);
    view.view.dispatch(tr);

    expect(onChange).toHaveBeenCalledWith("a\nbX");
    expect(view.content()).toBe("a\nbX");
  });

  it("styling marks heading paragraphs through markdown-it decorations", () => {
    const view = new WysiwygView();
    document.body.append(view.element);
    view.setContent("# Title\n\nBody.");

    const heading = view.element.querySelector<HTMLElement>(".prose-heading");
    expect(heading?.textContent).toBe("# Title");
  });

  it("decorates a heading that starts a paragraph even when followed by body lines", () => {
    const view = new WysiwygView();
    document.body.append(view.element);
    view.setContent("# One\nBody.\n\n## Two");

    const headings = [...view.element.querySelectorAll<HTMLElement>(".prose-heading")];
    expect(headings.map((h) => h.textContent)).toEqual(["# One Body.", "## Two"]);
  });

  it("renders the file's body without front matter or span markup", () => {
    const view = new WysiwygView();
    document.body.append(view.element);
    const file = [
      "---",
      "id: c1",
      "title: Opening 1",
      "---",
      "",
      '<span data-par-id="p-1">',
      "Chapter text.",
      "</span>",
    ].join("\n");
    view.setContent(file);

    expect(view.content()).toBe(file);
    expect(view.element.textContent).not.toContain("<span");
    expect(view.element.textContent).not.toContain("title:");
    expect(view.element.querySelector("p")?.textContent).toBe("Chapter text.");
  });

  it("plain Enter splits the paragraph into two", () => {
    const view = new WysiwygView();
    document.body.append(view.element);
    view.setContent("one\ntwo");
    const pm = view.element.querySelector(".ProseMirror") as HTMLElement;
    pm.focus();
    view.view.dispatch(view.view.state.tr.setSelection(TextSelection.create(view.view.state.doc, 3)));

    pm.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true, cancelable: true }));

    expect(view.content()).toBe("on\n\ne\ntwo");
    expect(view.element.querySelectorAll("p")).toHaveLength(2);
  });

  it("Shift-Enter inserts a hard line break inside the paragraph", () => {
    const view = new WysiwygView();
    document.body.append(view.element);
    view.setContent("one\ntwo");
    const pm = view.element.querySelector(".ProseMirror") as HTMLElement;
    pm.focus();
    view.view.dispatch(view.view.state.tr.setSelection(TextSelection.create(view.view.state.doc, 3)));

    pm.dispatchEvent(
      new KeyboardEvent("keydown", { key: "Enter", shiftKey: true, bubbles: true, cancelable: true }),
    );

    expect(view.content()).toBe("on\\\ne\ntwo");
    expect(view.element.querySelector("p")).not.toBeNull();
    expect(pm.querySelector("br")).not.toBeNull();
  });

  it("defaults the editable language to en-US", () => {
    const view = new WysiwygView();
    document.body.append(view.element);
    view.setContent("hello");

    expect(view.element.querySelector(".ProseMirror")?.getAttribute("lang")).toBe("en-US");
    expect(view.getLanguage()).toBe("en-US");
  });

  it("setLanguage writes the lang attribute onto the editable", () => {
    const view = new WysiwygView();
    document.body.append(view.element);
    view.setContent("hello");
    view.setLanguage("en-GB");

    expect(view.element.querySelector(".ProseMirror")?.getAttribute("lang")).toBe("en-GB");
    expect(view.getLanguage()).toBe("en-GB");
  });

  it("keeps the chosen language across setContent", () => {
    const view = new WysiwygView();
    document.body.append(view.element);
    view.setContent("one");
    view.setLanguage("de");
    view.setContent("two");

    expect(view.element.querySelector(".ProseMirror")?.getAttribute("lang")).toBe("de");
  });

  it("destroy detaches the editor", () => {
    const view = new WysiwygView();
    document.body.append(view.element);
    view.setContent("x");
    view.destroy();

    expect(view.element.querySelector("p")).toBeNull();
  });
});

describe("WysiwygView canonical round trip", () => {
  it("round-trips a canonical file byte-for-byte including front matter and span ids", () => {
    const file = [
      "---",
      "id: c1",
      "title: Opening 1",
      "---",
      "",
      '<span data-par-id="p-1">',
      "One.",
      "Two.",
      "</span>",
      "",
      '<span data-par-id="p-2">',
      "Three.",
      "</span>",
    ].join("\n");
    const view = new WysiwygView();
    document.body.append(view.element);
    view.setContent(file);

    expect(view.element.textContent).not.toContain("data-par-id");
    expect(view.element.textContent).not.toContain("title:");
    expect(view.content()).toBe(file);
  });

  it("keeps a paragraph's id when its text is edited", () => {
    const view = new WysiwygView();
    document.body.append(view.element);
    view.setContent('<span data-par-id="p-1">\nChapter text.\n</span>');

    const tr = view.view.state.tr;
    tr.insertText("X", 4);
    view.view.dispatch(tr);

    expect(view.content()).toBe('<span data-par-id="p-1">\nChaXpter text.\n</span>');
  });

  it("re-emits a hard-break line as backslash and hides it from view", () => {
    const view = new WysiwygView();
    document.body.append(view.element);
    view.setContent('<span data-par-id="p-1">\nLine one.\\\nLine two.\n</span>');

    expect(view.element.textContent).not.toContain("\\");
    expect(view.element.querySelector("br")).not.toBeNull();
    expect(view.content()).toBe('<span data-par-id="p-1">\nLine one.\\\nLine two.\n</span>');
  });

  it("exposes the visible body separately for dirty comparison", () => {
    const view = new WysiwygView();
    document.body.append(view.element);
    view.setContent('<span data-par-id="p-1">\nOne.\nTwo.\n</span>\n\n<span data-par-id="p-2">\nThree.\n</span>');

    expect(view.plainContent()).toBe("One.\nTwo.\n\nThree.");
  });

  it("lets a duplicated paragraph id fall back to a new (span-free) paragraph", () => {
    const doc = bufferToDocWithIds("X.\n\nY.", ["dup", "dup"]);
    expect(docToCanonical(doc)).toBe('<span data-par-id="dup">\nX.\n</span>\n\nY.');
  });
});