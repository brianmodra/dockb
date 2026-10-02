import { openOverlay, type Overlay } from "./overlay";

export interface SelectListItem {
  key: string;
  label: string;
}

export interface SelectListOptions<T> {
  title: string;
  items: SelectListItem[];
  itemTestId: string;
  cancelTestId?: string;
  confirmTestId: string;
  confirmLabel: string;
  emptyMessage: string;
  emptyTestId: string;
  /** What to resolve with when the chosen item is confirmed. */
  valueFor: (item: SelectListItem) => T;
}

export interface SelectList<T> {
  overlay: Overlay;
  /** Resolve with the chosen value, or null when cancelled or nothing chosen. */
  result: Promise<T | null>;
}

/**
 * A modal listing of items, one of which is chosen and then confirmed.
 *
 * This is the shape the document pickers share: pick an entry, then press the
 * action button. The button stays disabled until something is chosen, and only
 * one item reads as selected at a time.
 */
export function openSelectList<T>(options: SelectListOptions<T>): SelectList<T> {
  const cancelTestId = options.cancelTestId ?? "modal-cancel";
  const overlay = openOverlay({
    title: options.title,
    buttons: [
      { label: "Cancel", testId: cancelTestId },
      { label: options.confirmLabel, testId: options.confirmTestId, primary: true, disabled: true },
    ],
  });

  let chosen: SelectListItem | null = null;
  let resolveResult: (value: T | null) => void = () => {};
  const result = new Promise<T | null>((resolve) => {
    resolveResult = resolve;
  });

  const confirm = overlay.buttons[options.confirmTestId];
  const settle = (value: T | null): void => {
    overlay.close();
    resolveResult(value);
  };

  if (options.items.length === 0) {
    const empty = document.createElement("div");
    empty.className = "modal-body";
    empty.dataset.testid = options.emptyTestId;
    empty.textContent = options.emptyMessage;
    overlay.body.append(empty);
  } else {
    const list = document.createElement("div");
    list.className = "document-picker-list";
    for (const item of options.items) {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "document-picker-item";
      button.dataset.testid = options.itemTestId;
      button.textContent = item.label;
      button.addEventListener("click", () => {
        chosen = item;
        for (const other of list.querySelectorAll(".document-picker-item--selected")) {
          other.classList.remove("document-picker-item--selected");
        }
        button.classList.add("document-picker-item--selected");
        confirm.disabled = false;
      });
      list.append(button);
    }
    overlay.body.append(list);
  }

  overlay.buttons[cancelTestId].addEventListener("click", () => settle(null));
  confirm.addEventListener("click", () => {
    if (chosen === null) {
      return;
    }
    settle(options.valueFor(chosen));
  });

  return { overlay, result };
}
