/** The form pieces the two auth dialogs share. */

/**
 * A labelled input, wired the way a password manager expects.
 *
 * `autocomplete` is the part that matters and the part that is easy to omit: without
 * `username` and `current-password` a browser offers to save the wrong thing or
 * refuses to fill it in at all. Nothing here sets `maxlength` or blocks paste — a
 * refused paste is hostile, and the server's policy is the only authority on length.
 */
export function makeField(
  testid: string,
  label: string,
  options: { type: "text" | "password"; autocomplete: HTMLInputElement["autocomplete"] },
): HTMLLabelElement {
  const input = document.createElement("input");
  input.className = "modal-input";
  input.dataset.testid = testid;
  input.type = options.type;
  input.autocomplete = options.autocomplete;

  const caption = document.createElement("span");
  caption.textContent = label;

  const wrapper = document.createElement("label");
  wrapper.className = "modal-field-label";
  wrapper.append(caption, input);
  return wrapper;
}

/**
 * The one line where a refusal is shown, above the buttons rather than behind the
 * dialog — a message panel under a modal overlay is not readable.
 *
 * Kept empty and hidden until something goes wrong, so a successful screen has no
 * stale error left on it.
 */
export function makeErrorLine(testid: string): HTMLParagraphElement {
  const error = document.createElement("p");
  error.className = "modal-error";
  error.dataset.testid = testid;
  error.hidden = true;
  return error;
}

/** Show *message* in an error line, or clear it when *message* is empty. */
export function setError(error: HTMLElement, message: string): void {
  error.textContent = message;
  error.hidden = message === "";
}