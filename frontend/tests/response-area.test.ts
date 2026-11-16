import { afterEach, describe, expect, it, vi } from "vitest";
import {
  ResponseArea,
  parseResponseReply,
  proofreadingActionObjects,
  selectionActionObjects,
  unsavedChangesObjects,
} from "../src/renderer/layout/responseArea";
import type { SelectionContext, WysiwygDiagnostic } from "../src/renderer/layout/wysiwyg";

function button(area: ResponseArea, label: string): HTMLButtonElement {
  return Array.from(area.element.querySelectorAll<HTMLButtonElement>("button")).find(
    (el) => el.textContent === label,
  )!;
}

describe("ResponseArea", () => {
  afterEach(() => {
    document.body.replaceChildren();
    vi.restoreAllMocks();
  });

  it("starts out absent from the panel flow", () => {
    const area = new ResponseArea({});
    document.body.append(area.element);
    expect(area.element.hidden).toBe(true);
  });

  it("shows a spinner line while the model is working", () => {
    const area = new ResponseArea({});
    document.body.append(area.element);
    area.showSpinner();
    expect(area.element.hidden).toBe(false);
    const spinner = area.element.querySelector('[data-testid="response-spinner"]');
    expect(spinner).not.toBeNull();
    expect(spinner!.querySelector("svg.spinning-loader")).not.toBeNull();
    expect(spinner!.textContent).toBe("waiting for the model");
    expect(spinner!.textContent).not.toContain("⌛");
  });

  it("styles response buttons with the shared button classes", () => {
    const area = new ResponseArea({ functions: { highlight: vi.fn() } });
    document.body.append(area.element);
    area.show([{ button: { label: "Highlight sentence", function: "highlight" } }]);
    expect(button(area, "Highlight sentence").className).toBe("btn btn--secondary");
  });

  it("renders a reply: each text object on its own wrapping line, each button after them", () => {
    const area = new ResponseArea({});
    document.body.append(area.element);
    area.show([
      { text: "Hello world!" },
      { button: { label: "Highlight sentence", function: "highlight", args: { chapter_id: "c1" } } },
    ]);
    expect(area.element.hidden).toBe(false);
    const lines = Array.from(area.element.querySelectorAll(".response-line")).map((n) => n.textContent);
    expect(lines).toEqual(["Hello world!"]);
    expect(button(area, "Highlight sentence")).toBeInstanceOf(HTMLButtonElement);
    expect(area.element.querySelector('[data-testid="response-spinner"]')).toBeNull();
  });

  it("passes the button's args to the registered function named on the button", () => {
    const highlight = vi.fn();
    const area = new ResponseArea({ functions: { highlight } });
    document.body.append(area.element);
    const args = { chapter_id: "c1", paragraph_id: "p1" };
    area.show([{ button: { label: "Highlight sentence", function: "highlight", args } }]);
    button(area, "Highlight sentence").click();
    expect(highlight).toHaveBeenCalledWith(args);
  });

  it("renders a button naming no registered function disabled", () => {
    const area = new ResponseArea({});
    document.body.append(area.element);
    area.show([{ button: { label: "Highlight sentence", function: "highlight" } }]);
    expect(button(area, "Highlight sentence").disabled).toBe(true);
  });

  it("falls back to plain text until a reply replaces the spinner", () => {
    const area = new ResponseArea({});
    document.body.append(area.element);
    area.showSpinner();
    button(area, "Highlight sentence");
    area.show([{ text: "found nothing" }]);
    expect(area.element.querySelectorAll("button")).toHaveLength(0);
    area.clear();
    expect(area.element.hidden).toBe(true);
    expect(area.element.textContent).toBe("");
  });

  it("replaces the spinner and an earlier reply when a new reply arrives", () => {
    const area = new ResponseArea({});
    document.body.append(area.element);
    area.showSpinner();
    area.show([{ text: "first reply", button: { label: "Old", function: "nope" } }]);
    area.show([{ text: "second reply" }]);
    expect(area.element.querySelector('[data-testid="response-spinner"]')).toBeNull();
    expect(area.element.querySelectorAll("button")).toHaveLength(0);
    expect(area.element.textContent).toContain("second reply");
    expect(area.element.textContent).not.toContain("first reply");
  });
});

describe("ResponseArea menu mode", () => {
  function menuArea(onDismiss: () => void = () => {}): ResponseArea {
    const area = new ResponseArea({
      functions: { format: vi.fn() },
    });
    document.body.append(area.element);
    area.showMenu(
      [
        { button: { label: "Italic", function: "format", args: { changes: { style: "italic" } } } },
        { button: { label: "Bold", function: "format", args: { changes: { weight: "bold" } } } },
      ],
      onDismiss,
    );
    return area;
  }

  function buttons(area: ResponseArea): HTMLButtonElement[] {
    return Array.from(area.element.querySelectorAll<HTMLButtonElement>("button"));
  }

  it("focuses the first button when the menu appears", () => {
    const area = menuArea();
    expect(document.activeElement).toBe(buttons(area)[0]);
  });

  it("moves the highlight right and left with the arrow keys", () => {
    const area = menuArea();
    area.element.dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowRight", bubbles: true }));
    expect(document.activeElement).toBe(buttons(area)[1]);
    area.element.dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowLeft", bubbles: true }));
    expect(document.activeElement).toBe(buttons(area)[0]);
  });

  it("clamps the highlight at both ends", () => {
    const area = menuArea();
    area.element.dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowLeft", bubbles: true }));
    expect(document.activeElement).toBe(buttons(area)[0]);
    area.element.dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowRight", bubbles: true }));
    area.element.dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowRight", bubbles: true }));
    expect(document.activeElement).toBe(buttons(area)[1]);
  });

  it("activates the focused button on Enter and dismisses the menu", () => {
    const format = vi.fn();
    const onDismiss = vi.fn();
    const area = new ResponseArea({ functions: { format } });
    document.body.append(area.element);
    area.showMenu(
      [{ button: { label: "Italic", function: "format", args: { changes: { style: "italic" } } } }],
      onDismiss,
    );

    area.element.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true }));

    expect(format).toHaveBeenCalledWith({ changes: { style: "italic" } });
    expect(onDismiss).toHaveBeenCalledTimes(1);
    expect(area.element.hidden).toBe(true);
  });

  it("dismisses the menu on Escape and runs onDismiss", () => {
    const onDismiss = vi.fn();
    const area = menuArea(onDismiss);

    area.element.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));

    expect(onDismiss).toHaveBeenCalledTimes(1);
    expect(area.element.hidden).toBe(true);
  });

  it("does not react to the arrow keys outside menu mode", () => {
    const area = new ResponseArea({});
    document.body.append(area.element);
    area.show([{ button: { label: "Highlight", function: "highlight" } }]);

    area.element.dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowRight", bubbles: true }));

    expect(document.activeElement).not.toBe(area.element.querySelector("button"));
  });
});

describe("parseResponseReply", () => {
  it("lifts the response array out of the model's reply object", () => {
    const reply = JSON.stringify({
      response: [{ text: "Hello world!" }, { button: { label: "Highlight", function: "highlight" } }],
    });
    expect(parseResponseReply(reply)).toEqual([
      { text: "Hello world!" },
      { button: { label: "Highlight", function: "highlight" } },
    ]);
  });

  it("also accepts a bare response array as the whole reply", () => {
    const reply = JSON.stringify([{ text: "Hello world!" }]);
    expect(parseResponseReply(reply)).toEqual([{ text: "Hello world!" }]);
  });

  it("refuses a reply that is not response syntax", () => {
    expect(parseResponseReply("just some prose")).toBeNull();
    expect(parseResponseReply("{}")).toBeNull();
    expect(parseResponseReply(JSON.stringify({ response: "nope" }))).toBeNull();
    expect(parseResponseReply(JSON.stringify([{ text: null }]))).toBeNull();
    expect(parseResponseReply(
      JSON.stringify([{ button: { label: "Highlight", function: 42 } }]),
    )).toBeNull();
    expect(parseResponseReply(JSON.stringify([{ unknown: 1 }]))).toBeNull();
  });
});

function sampleContext(overrides: Partial<SelectionContext> = {}): SelectionContext {
  return {
    text: "Rain fell on the plain.",
    paragraphIds: ["p1"],
    paragraphIndexes: [0],
    layout: { kind: "normal", variant: "" },
    wholeParagraph: false,
    start: { paragraphId: "p1", paragraphIndex: 0, sentenceIndex: 0, offset: 0 },
    end: { paragraphId: "p1", paragraphIndex: 0, sentenceIndex: 0, offset: 23 },
    ...overrides,
  };
}

describe("selectionActionObjects", () => {
  it("asks what to do with the text and offers the formatting buttons for a partial selection", () => {
    const objects = selectionActionObjects(sampleContext());

    expect(objects[0]).toEqual({
      text: 'What do you want to do with this text: "Rain fell on the plain."',
    });
    const format = objects.filter((item) => item.button?.function === "format");
    expect(format.map((item) => item.button?.label)).toEqual([
      "Italic",
      "Bold",
      "Underline",
      "Monospace",
      "Normal font",
      "Large",
      "Small",
      "Normal size",
      "Clear formatting",
    ]);
    expect(objects.filter((item) => item.button?.function === "quote")).toHaveLength(0);
  });

  it("passes each button's formatting patch as its args", () => {
    const objects = selectionActionObjects(sampleContext());
    const format = objects.filter((item) => item.button?.function === "format");
    expect(format.map((item) => (item.button?.args as { changes: unknown }).changes)).toEqual([
      { style: "italic" },
      { weight: "bold" },
      { style: "underline" },
      { family: "monospace" },
      { style: "", weight: "", family: "" },
      { size: "1.5em" },
      { size: "0.75em" },
      { size: "1em" },
      { style: "", weight: "", family: "", size: "1em" },
    ]);
  });

  it("offers the quote-paragraph buttons when the whole paragraph is selected", () => {
    const objects = selectionActionObjects(sampleContext({ wholeParagraph: true }));

    const quotes = objects.filter((item) => item.button?.function === "quote");
    expect(quotes.map((item) => item.button?.label)).toEqual([
      'Quote para "reading"',
      'Quote para "writing"',
    ]);
    expect(quotes[0].button?.args).toEqual({
      layout: { kind: "quoted", variant: "reading" },
      paragraph_ids: ["p1"],
      paragraph_indexes: [0],
      start: { paragraph_id: "p1", paragraph_index: 0, sentence_index: 0, offset: 0 },
      end: { paragraph_id: "p1", paragraph_index: 0, sentence_index: 0, offset: 23 },
      text: "Rain fell on the plain.",
    });
  });

  it("offers only the quote that changes it when the whole paragraph is already quoted", () => {
    const reading = selectionActionObjects(
      sampleContext({ wholeParagraph: true, layout: { kind: "quoted", variant: "reading" } }),
    );
    expect(
      reading.filter((item) => item.button?.function === "quote").map((item) => item.button?.label),
    ).toEqual(['Quote para "writing"']);

    const writing = selectionActionObjects(
      sampleContext({ wholeParagraph: true, layout: { kind: "quoted", variant: "writing" } }),
    );
    expect(
      writing.filter((item) => item.button?.function === "quote").map((item) => item.button?.label),
    ).toEqual(['Quote para "reading"']);
  });

  it("truncates the prompt snippet after 40 characters with an ellipsis while keeping full text in args", () => {
    const forty = "1234567890123456789012345678901234567890";
    expect(selectionActionObjects(sampleContext({ text: forty }))[0]).toEqual({
      text: `What do you want to do with this text: "${forty}"`,
    });

    const longer = `${forty} extra words after the limit`;
    const objects = selectionActionObjects(sampleContext({ text: longer, wholeParagraph: true }));
    expect(objects[0]).toEqual({
      text: `What do you want to do with this text: "${forty}…"`,
    });
    const quote = objects.find((item) => item.button?.function === "quote");
    expect((quote!.button?.args as { text: string }).text).toBe(longer);
  });
});

function sampleDiagnostic(overrides: Partial<WysiwygDiagnostic> = {}): WysiwygDiagnostic {
  return {
    rule_id: "MORFOLOGIK_RULE_EN_US",
    category: "TYPOS",
    severity: "warning",
    message: "Possible spelling mistake found.",
    start: 0,
    end: 3,
    replacements: ["the", "tea"],
    in_focus: true,
    from: 1,
    to: 4,
    word: "teh",
    ...overrides,
  };
}

describe("unsavedChangesObjects", () => {
  it("names the unsaved-change count and offers a Save chapter button", () => {
    expect(unsavedChangesObjects(12)).toEqual([
      { text: "The chapter has 12 unsaved changes" },
      { button: { label: "Save chapter", function: "save-chapter" } },
    ]);
  });
});

describe("proofreadingActionObjects", () => {
  it("names the word and message, then the replacements and Add to dictionary", () => {
    const objects = proofreadingActionObjects(sampleDiagnostic());

    expect(objects).toEqual([
      { text: '"teh" — Possible spelling mistake found.' },
      { button: { label: "the", function: "proofreading-replace", args: { replacement: "the" } } },
      { button: { label: "tea", function: "proofreading-replace", args: { replacement: "tea" } } },
      { button: { label: "Add to dictionary", function: "proofreading-add-word", args: { word: "teh" } } },
    ]);
  });

  it("offers at most five replacements", () => {
    const objects = proofreadingActionObjects(
      sampleDiagnostic({ replacements: ["a", "b", "c", "d", "e", "f", "g"] }),
    );

    const labels = objects.slice(1, -1).map((item) => item.button?.label);
    expect(labels).toEqual(["a", "b", "c", "d", "e"]);
  });

  it("offers the message and Add to dictionary alone when there are no replacements", () => {
    const objects = proofreadingActionObjects(sampleDiagnostic({ replacements: [] }));

    expect(objects).toEqual([
      { text: '"teh" — Possible spelling mistake found.' },
      { button: { label: "Add to dictionary", function: "proofreading-add-word", args: { word: "teh" } } },
    ]);
  });

  it("offers a quote-pair fix when the diagnostic carries a pair", () => {
    const objects = proofreadingActionObjects(
      sampleDiagnostic({ pair: { replacement: "\u201d", from: 1, to: 2, partnerReplacement: "\u201c" } }),
    );

    expect(objects).toEqual([
      { text: '"teh" — Possible spelling mistake found.' },
      { button: { label: "the", function: "proofreading-replace", args: { replacement: "the" } } },
      { button: { label: "tea", function: "proofreading-replace", args: { replacement: "tea" } } },
      { button: { label: "Fix \u201c \u2026 \u201d", function: "proofreading-fix-pair" } },
      { button: { label: "Add to dictionary", function: "proofreading-add-word", args: { word: "teh" } } },
    ]);
  });
});
