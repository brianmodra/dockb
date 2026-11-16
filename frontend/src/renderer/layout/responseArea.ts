import { createSpinner } from "./spinner";
import {
  type FormatPatch,
  type ParagraphLayout,
  type SelectionContext,
  type WysiwygDiagnostic,
} from "./wysiwyg";

export const PROOFREADING_REPLACE_FUNCTION = "proofreading-replace";
export const PROOFREADING_ADD_WORD_FUNCTION = "proofreading-add-word";
export const PROOFREADING_FIX_PAIR_FUNCTION = "proofreading-fix-pair";

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

const QUOTE_CHOICES: ReadonlyArray<{ layout: ParagraphLayout; label: string }> = [
  { layout: { kind: "quoted", variant: "reading" }, label: 'Quote para "reading"' },
  { layout: { kind: "quoted", variant: "writing" }, label: 'Quote para "writing"' },
];

const FORMAT_CHOICES: ReadonlyArray<{ patch: FormatPatch; label: string }> = [
  { patch: { style: "italic" }, label: "Italic" },
  { patch: { weight: "bold" }, label: "Bold" },
  { patch: { style: "underline" }, label: "Underline" },
  { patch: { family: "monospace" }, label: "Monospace" },
  { patch: { style: "", weight: "", family: "" }, label: "Normal font" },
  { patch: { size: "1.5em" }, label: "Large" },
  { patch: { size: "0.75em" }, label: "Small" },
  { patch: { size: "1em" }, label: "Normal size" },
  { patch: { style: "", weight: "", family: "", size: "1em" }, label: "Clear formatting" },
];

function sameLayout(left: ParagraphLayout, right: ParagraphLayout): boolean {
  return left.kind === right.kind && left.variant === right.variant;
}

/**
 * Build the response-area objects for a right-clicked text selection: a line
 * naming a 40-character snippet of the text, the inline-formatting buttons, and
 * — when the selection is a whole paragraph — the two quote actions that would
 * change its layout.
 */
export function selectionActionObjects(context: SelectionContext): ResponseObject[] {
  const collapsed = context.text.replace(/\s+/g, " ");
  const snippet =
    collapsed.length > SELECTION_SNIPPET_LIMIT
      ? `${collapsed.slice(0, SELECTION_SNIPPET_LIMIT)}…`
      : collapsed;
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
  const formatButtons: ResponseObject[] = FORMAT_CHOICES.map((choice) => ({
    button: {
      label: choice.label,
      function: "format",
      args: { changes: choice.patch },
    },
  }));
  const quoteButtons: ResponseObject[] = context.wholeParagraph
    ? QUOTE_CHOICES.filter((choice) => !sameLayout(choice.layout, context.layout)).map((choice) => ({
        button: {
          label: choice.label,
          function: "quote",
          args: {
            layout: choice.layout,
            paragraph_ids: context.paragraphIds,
            paragraph_indexes: context.paragraphIndexes,
            start,
            end,
            text: context.text,
          },
        },
      }))
    : [];
  return [
    { text: `What do you want to do with this text: "${snippet}"` },
    ...formatButtons,
    ...quoteButtons,
  ];
}

/**
 * Build the response-area objects for a right-clicked diagnostic: a line naming
 * the word and its message, then the replacement buttons, a quote-pair fix when
 * the diagnostic carries one, and Add to dictionary.
 */
export function proofreadingActionObjects(diagnostic: WysiwygDiagnostic): ResponseObject[] {
  const replacements = diagnostic.replacements.slice(0, 5).map((replacement) => ({
    button: {
      label: replacement,
      function: PROOFREADING_REPLACE_FUNCTION,
      args: { replacement },
    },
  }));
  const pair = diagnostic.pair
    ? [{ button: { label: "Fix \u201c \u2026 \u201d", function: PROOFREADING_FIX_PAIR_FUNCTION } }]
    : [];
  return [
    { text: `"${diagnostic.word}" — ${diagnostic.message}` },
    ...replacements,
    ...pair,
    {
      button: {
        label: "Add to dictionary",
        function: PROOFREADING_ADD_WORD_FUNCTION,
        args: { word: diagnostic.word },
      },
    },
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
  private menuActive = false;
  private onDismiss: (() => void) | null = null;

  constructor(options: ResponseAreaOptions = {}) {
    this.functions = options.functions ?? {};
    this.element = document.createElement("div");
    this.element.dataset.testid = "panel-response";
    this.element.className = "response-area";
    this.element.hidden = true;
    this.element.addEventListener("keydown", (event) => this.onKeydown(event));
  }

  showSpinner(): void {
    this.menuActive = false;
    this.onDismiss = null;
    this.showSpinnerIn(this.element);
  }

  show(objects: ResponseObject[]): void {
    this.menuActive = false;
    this.onDismiss = null;
    this.render(objects);
  }

  /**
   * Show *objects* as a keyboard-navigable menu: the first button takes focus,
   * arrow keys move the highlight between buttons, Enter activates the focused
   * one, and Escape (or an activation) runs *onDismiss*.
   */
  showMenu(objects: ResponseObject[], onDismiss?: () => void): void {
    this.render(objects);
    this.menuActive = true;
    this.onDismiss = onDismiss ?? null;
    this.element.querySelector<HTMLButtonElement>("button")?.focus();
  }

  clear(): void {
    this.menuActive = false;
    this.onDismiss = null;
    this.element.replaceChildren();
    this.element.hidden = true;
  }

  private render(objects: ResponseObject[]): void {
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

  private button(spec: ResponseButton): HTMLButtonElement {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "btn btn--secondary";
    button.textContent = spec.label;
    const handler = this.functions[spec.function];
    if (handler) {
      button.setAttribute("data-testid", "response-button");
      button.addEventListener("click", () => {
        const onDismiss = this.menuActive ? this.onDismiss : null;
        if (this.menuActive) {
          this.menuActive = false;
          this.onDismiss = null;
        }
        handler(spec.args);
        if (onDismiss) {
          this.clear();
          onDismiss();
        }
      });
    } else {
      button.disabled = true;
    }
    return button;
  }

  private onKeydown(event: KeyboardEvent): void {
    if (!this.menuActive) {
      return;
    }
    if (event.key === "ArrowLeft") {
      event.preventDefault();
      this.moveFocus(-1);
    } else if (event.key === "ArrowRight") {
      event.preventDefault();
      this.moveFocus(1);
    } else if (event.key === "Enter") {
      const active = document.activeElement;
      if (active instanceof HTMLButtonElement && this.element.contains(active)) {
        event.preventDefault();
        active.click();
      }
    } else if (event.key === "Escape") {
      event.preventDefault();
      this.dismiss();
    }
  }

  private moveFocus(direction: 1 | -1): void {
    const buttons = Array.from(this.element.querySelectorAll<HTMLButtonElement>("button"));
    if (buttons.length === 0) {
      return;
    }
    const current = document.activeElement;
    const index = current instanceof HTMLButtonElement ? buttons.indexOf(current) : -1;
    const next = index === -1 ? 0 : Math.max(0, Math.min(buttons.length - 1, index + direction));
    buttons[next].focus();
  }

  private dismiss(): void {
    if (!this.menuActive) {
      return;
    }
    this.menuActive = false;
    const onDismiss = this.onDismiss;
    this.onDismiss = null;
    this.clear();
    onDismiss?.();
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
