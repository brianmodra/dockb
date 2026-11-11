import { afterEach, describe, expect, it, vi } from "vitest";
import {
  ResponseArea,
  parseResponseReply,
  proofreadingActionObjects,
  selectionActionObjects,
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
    quoteType: "",
    start: { paragraphId: "p1", paragraphIndex: 0, sentenceIndex: 0, offset: 0 },
    end: { paragraphId: "p1", paragraphIndex: 0, sentenceIndex: 0, offset: 23 },
    ...overrides,
  };
}

describe("selectionActionObjects", () => {
  it("offers Quote read and Quote written for unquoted text", () => {
    const objects = selectionActionObjects(sampleContext());

    expect(objects).toEqual([
      { text: 'What do you want to do with this unquoted text: "Rain fell on the plain."' },
      {
        button: {
          label: "Quote read",
          function: "quote",
          args: {
            quote_type: "reading",
            paragraph_ids: ["p1"],
            paragraph_indexes: [0],
            start: { paragraph_id: "p1", paragraph_index: 0, sentence_index: 0, offset: 0 },
            end: { paragraph_id: "p1", paragraph_index: 0, sentence_index: 0, offset: 23 },
            text: "Rain fell on the plain.",
          },
        },
      },
      {
        button: {
          label: "Quote written",
          function: "quote",
          args: {
            quote_type: "writing",
            paragraph_ids: ["p1"],
            paragraph_indexes: [0],
            start: { paragraph_id: "p1", paragraph_index: 0, sentence_index: 0, offset: 0 },
            end: { paragraph_id: "p1", paragraph_index: 0, sentence_index: 0, offset: 23 },
            text: "Rain fell on the plain.",
          },
        },
      },
    ]);
  });

  it("offers Remove quote and Quote written when the text is quoted as read", () => {
    const objects = selectionActionObjects(sampleContext({ quoteType: "reading" }));

    expect(objects[0]).toEqual({
      text: 'What do you want to do with this quoted as read text: "Rain fell on the plain."',
    });
    expect(objects.slice(1).map((item) => item.button?.label)).toEqual([
      "Remove quote",
      "Quote written",
    ]);
    expect(objects.slice(1).map((item) => (item.button?.args as { quote_type: string }).quote_type)).toEqual([
      "",
      "writing",
    ]);
  });

  it("offers Remove quote and Quote read when the text is quoted as written", () => {
    const objects = selectionActionObjects(sampleContext({ quoteType: "writing" }));

    expect(objects[0]).toEqual({
      text: 'What do you want to do with this quoted as written text: "Rain fell on the plain."',
    });
    expect(objects.slice(1).map((item) => item.button?.label)).toEqual([
      "Remove quote",
      "Quote read",
    ]);
    expect(objects.slice(1).map((item) => (item.button?.args as { quote_type: string }).quote_type)).toEqual([
      "",
      "reading",
    ]);
  });

  it("truncates the prompt snippet after 40 characters with an ellipsis while keeping full text in args", () => {
    const forty = "1234567890123456789012345678901234567890";
    expect(selectionActionObjects(sampleContext({ text: forty }))[0]).toEqual({
      text: `What do you want to do with this unquoted text: "${forty}"`,
    });

    const longer = `${forty} extra words after the limit`;
    const objects = selectionActionObjects(sampleContext({ text: longer }));
    expect(objects[0]).toEqual({
      text: `What do you want to do with this unquoted text: "${forty}…"`,
    });
    expect((objects[1].button?.args as { text: string }).text).toBe(longer);
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
