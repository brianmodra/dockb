import { createSpinner } from "./spinner";
import type { SelectionContext } from "./wysiwyg";

export interface ResponseButton {
  label: string;
  function: string;
  args?: unknown;
}

export interface ResponseObject {
  text?: string;
  button?: ResponseButton;
}

export type ResponseFunctions = Record<string, (args: unknown) => void>;

export interface ResponseAreaOptions {
  functions?: ResponseFunctions;
}

function isResponseButton(value: unknown): value is ResponseButton {
  if (typeof value !== "object" || value === null) {
    return false;
  }
  const button = value as Record<string, unknown>;
  return typeof button.label === "string" && typeof button.function === "string";
}

function isResponseObject(value: unknown): value is ResponseObject {
  if (typeof value !== "object" || value === null) {
    return false;
  }
  const object = value as Record<string, unknown>;
  if (typeof object.text === "string") {
    return true;
  }
  return "button" in object && isResponseButton(object.button);
}

/**
 * Parse the model's reply as the response syntax — an array of objects whose
 * fields name only `text` strings or `button` controls. A reply that is not
 * response syntax (JSON, the response array, or any item) parses as null, and
 * the caller falls back to showing it as plain text.
 */
export function parseResponseReply(reply: string): ResponseObject[] | null {
  let parsed: unknown;
  try {
    parsed = JSON.parse(reply);
  } catch {
    return null;
  }
  const objects = typeof parsed === "object" && parsed !== null && "response" in parsed
    ? (parsed as { response: unknown }).response
    : parsed;
  if (!Array.isArray(objects)) {
    return null;
  }
  return objects.every(isResponseObject) ? objects : null;
}

const SELECTION_SNIPPET_LIMIT = 40;

const QUOTE_CHOICES: ReadonlyArray<{ quoteType: string; label: string }> = [
  { quoteType: "", label: "Remove quote" },
  { quoteType: "reading", label: "Quote read" },
  { quoteType: "writing", label: "Quote written" },
];

function quoteStateLabel(quoteType: string): string {
  if (quoteType === "reading") {
    return "quoted as read";
  }
  if (quoteType === "writing") {
    return "quoted as written";
  }
  return "unquoted";
}

/**
 * Build the response-area objects for a right-clicked text selection: a line
 * naming its current quote state and a 40-character snippet of the text,
 * followed by the two quote actions that would change it.
 */
export function selectionActionObjects(context: SelectionContext): ResponseObject[] {
  const collapsed = context.text.replace(/\s+/g, " ");
  const snippet =
    collapsed.length > SELECTION_SNIPPET_LIMIT
      ? `${collapsed.slice(0, SELECTION_SNIPPET_LIMIT)}…`
      : collapsed;
  const state = quoteStateLabel(context.quoteType);
  const start = {
    paragraph_id: context.start.paragraphId,
    paragraph_index: context.start.paragraphIndex,
    sentence_index: context.start.sentenceIndex,
    offset: context.start.offset,
  };
  const end = {
    paragraph_id: context.end.paragraphId,
    paragraph_index: context.end.paragraphIndex,
    sentence_index: context.end.sentenceIndex,
    offset: context.end.offset,
  };
  const buttons: ResponseObject[] = QUOTE_CHOICES.filter(
    (choice) => choice.quoteType !== context.quoteType,
  ).map((choice) => ({
    button: {
      label: choice.label,
      function: "quote",
      args: {
        quote_type: choice.quoteType,
        paragraph_ids: context.paragraphIds,
        paragraph_indexes: context.paragraphIndexes,
        start,
        end,
        text: context.text,
      },
    },
  }));
  return [
    { text: `What do you want to do with this ${state} text: "${snippet}"` },
    ...buttons,
  ];
}

/**
 * The panel strip between the log and the chat box that answers a submitted
 * prompt: a spinner line while the model is working, then the parsed response.
 * Children are built with `createElement`/`textContent` only — the reply comes
 * from outside the editor and never enters the DOM as markup.
 */
export class ResponseArea {
  readonly element: HTMLElement;

  private readonly functions: ResponseFunctions;

  constructor(options: ResponseAreaOptions = {}) {
    this.functions = options.functions ?? {};
    this.element = document.createElement("div");
    this.element.dataset.testid = "panel-response";
    this.element.className = "response-area";
    this.element.hidden = true;
  }

  showSpinner(): void {
    this.showSpinnerIn(this.element);
  }

  show(objects: ResponseObject[]): void {
    this.element.replaceChildren();
    for (const object of objects) {
      if (object.text !== undefined) {
        const line = document.createElement("div");
        line.className = "response-line";
        line.textContent = object.text;
        this.element.append(line);
      }
      if (object.button !== undefined) {
        this.element.append(this.button(object.button));
      }
    }
    this.element.hidden = false;
  }

  clear(): void {
    this.element.replaceChildren();
    this.element.hidden = true;
  }

  private button(spec: ResponseButton): HTMLButtonElement {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "btn btn--secondary";
    button.textContent = spec.label;
    const handler = this.functions[spec.function];
    if (handler) {
      button.setAttribute("data-testid", "response-button");
      button.addEventListener("click", () => handler(spec.args));
    } else {
      button.disabled = true;
    }
    return button;
  }

  private showSpinnerIn(area: HTMLElement): void {
    area.replaceChildren();
    const spinner = document.createElement("div");
    spinner.className = "response-spinner";
    spinner.dataset.testid = "response-spinner";
    spinner.setAttribute("aria-busy", "true");
    spinner.append(createSpinner(), "waiting for the model");
    area.append(spinner);
    area.hidden = false;
  }
}
