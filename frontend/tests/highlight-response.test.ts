import { afterEach, describe, expect, it, vi } from "vitest";
import type { DocumentContentResponse } from "../src/renderer/api/types";
import { EditPanel, type EditPanelApi } from "../src/renderer/layout/editPanel";
import { WysiwygView } from "../src/renderer/layout/wysiwyg";

const BUFFER =
  '<span data-par-id="p1">\nRain fell on the plain.\nKarakas closed the door.\n</span>\n\n' +
  '<span data-par-id="p2">\nA second paragraph.\n</span>';

function doc(content: string): DocumentContentResponse {
  return { content, summary: null };
}

function fakeApi(overrides: Partial<EditPanelApi> = {}): EditPanelApi {
  return {
    getChapterDocument: vi.fn(async () => doc("")),
    saveChapterDocument: vi.fn(async (_id: string, content: string) => doc(content)),
    ...overrides,
  };
}

afterEach(() => {
  document.body.replaceChildren();
  vi.restoreAllMocks();
});

describe("WysiwygView sentence selection", () => {
  it("selects the nth sentence of a paragraph by its paragraph id", () => {
    const view = new WysiwygView();
    document.body.append(view.element);
    view.setContent(BUFFER);
    expect(view.selectSentences("p1", [0])).toBe(true);
    expect(view.selectedText()).toBe("Rain fell on the plain.");
    expect(view.selectSentences("p1", [1])).toBe(true);
    expect(view.selectedText()).toBe("Karakas closed the door.");
  });

  it("selects several sentences as one span over them", () => {
    const view = new WysiwygView();
    document.body.append(view.element);
    view.setContent(BUFFER);
    expect(view.selectSentences("p1", [1, 0])).toBe(true);
    expect(view.selectedText()).toBe("Rain fell on the plain. Karakas closed the door.");
  });

  it("scrolls the whole selected paragraph into view inside the editor's scroller", () => {
    const view = new WysiwygView();
    document.body.append(view.element);
    view.setContent(BUFFER);
    const paragraphs = Array.from(view.element.querySelectorAll("p")) as HTMLElement[];
    const scrolled: Array<[HTMLElement, ScrollIntoViewOptions | undefined]> = [];
    for (const paragraph of paragraphs) {
      (paragraph as { scrollIntoView?: unknown }).scrollIntoView = (options: ScrollIntoViewOptions) => {
        scrolled.push([paragraph, options]);
      };
    }
    view.selectSentences("p2", null);
    expect(scrolled).toEqual([[paragraphs[1], { block: "nearest" }]]);
  });

  it("ensures the selection's highlight is drawn by focusing the editor again", () => {
    const view = new WysiwygView();
    document.body.append(view.element);
    view.setContent(BUFFER);
    view.selectSentences("p1", [0]);
    expect(document.activeElement).toBe(view.element.querySelector(".ProseMirror"));
  });

  it("selects a whole paragraph when no sentence indexes are given", () => {
    const view = new WysiwygView();
    document.body.append(view.element);
    view.setContent(BUFFER);
    expect(view.selectSentences("p1", [])).toBe(true);
    expect(view.selectedText()).toBe("Rain fell on the plain. Karakas closed the door.");
  });

  it("refuses an unknown paragraph id without touching the selection", () => {
    const view = new WysiwygView();
    document.body.append(view.element);
    view.setContent(BUFFER);
    view.selectSentences("p1", [0]);
    expect(view.selectSentences("missing", [0])).toBe(false);
    expect(view.selectedText()).toBe("Rain fell on the plain.");
  });

  it("clamps out-of-range sentence indexes to the paragraph's last sentence", () => {
    const view = new WysiwygView();
    document.body.append(view.element);
    view.setContent(BUFFER);
    expect(view.selectSentences("p1", [9])).toBe(true);
    expect(view.selectedText()).toBe("Karakas closed the door.");
  });
});

describe("EditPanel sentence selection", () => {
  it("names the chapter it has open", async () => {
    const api = fakeApi({ getChapterDocument: vi.fn(async () => doc(BUFFER)) });
    const panel = new EditPanel({ api });
    document.body.append(panel.element);
    expect(panel.currentChapter()).toBeNull();
    await panel.load("c1");
    expect(panel.currentChapter()).toBe("c1");
  });

  it("selects sentences in the open chapter without dirtying the buffer", async () => {
    const api = fakeApi({ getChapterDocument: vi.fn(async () => doc(BUFFER)) });
    const panel = new EditPanel({ api });
    document.body.append(panel.element);
    await panel.load("c1");
    expect(panel.selectSentences("p2", [0])).toBe(true);
    expect(panel.isDirty()).toBe(false);
  });

  it("does not select anything while the raw view is showing", async () => {
    const api = fakeApi({ getChapterDocument: vi.fn(async () => doc(BUFFER)) });
    const panel = new EditPanel({ api });
    document.body.append(panel.element);
    await panel.load("c1");
    panel.setMode("raw");
    expect(panel.selectSentences("p1", [0])).toBe(false);
  });
});
