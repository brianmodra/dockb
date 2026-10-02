export interface OverlayButtonSpec {
  label: string;
  testId: string;
  primary?: boolean;
  disabled?: boolean;
}

export interface Overlay {
  /** The overlay element, so a caller can query or attach to it. */
  element: HTMLElement;
  /** The dialog box. */
  dialog: HTMLElement;
  /** Where content goes: between the title and the button row. */
  body: HTMLElement;
  /** Each button, by the test id it was given. */
  buttons: Readonly<Record<string, HTMLButtonElement>>;
  /** Take the overlay off the page. Safe to call more than once. */
  close(): void;
}

/**
 * Mount a modal overlay: a title, whatever content the caller adds to the body,
 * and a row of buttons.
 *
 * This is the shape every dialog in the editor shares, so the overlay, its
 * classes, and its test ids live here rather than being rebuilt per dialog. The
 * caller decides what closes a dialog and what closing it resolves to; buttons do
 * not close anything by themselves.
 */
export function openOverlay(options: { title: string; buttons: OverlayButtonSpec[] }): Overlay {
  const element = document.createElement("div");
  element.className = "modal-overlay";
  element.dataset.testid = "modal";

  const dialog = document.createElement("div");
  dialog.className = "modal-dialog";

  const title = document.createElement("h2");
  title.className = "modal-title";
  title.dataset.testid = "modal-title";
  title.textContent = options.title;

  const body = document.createElement("div");

  const buttons = document.createElement("div");
  buttons.className = "modal-buttons";

  const byId: Record<string, HTMLButtonElement> = {};
  for (const spec of options.buttons) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "modal-button";
    if (spec.primary === true) {
      button.classList.add("is-primary");
    }
    button.dataset.testid = spec.testId;
    button.textContent = spec.label;
    button.disabled = spec.disabled === true;
    byId[spec.testId] = button;
    buttons.append(button);
  }

  dialog.append(title, body, buttons);
  element.append(dialog);
  document.body.append(element);

  return {
    element,
    dialog,
    body,
    buttons: byId,
    close: () => element.remove(),
  };
}
