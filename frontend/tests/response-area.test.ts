import { afterEach, describe, expect, it, vi } from "vitest";
import { ResponseArea, parseResponseReply } from "../src/renderer/layout/responseArea";

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
    expect(area.element.querySelector('[data-testid="response-spinner"]')).not.toBeNull();
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
