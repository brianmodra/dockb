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
    spinner.textContent = "⌛ waiting for the model";
    area.append(spinner);
    area.hidden = false;
  }
}
