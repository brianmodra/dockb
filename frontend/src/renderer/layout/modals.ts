export interface ModalButton {
  label: string;
  value: string;
  primary?: boolean;
}

export interface PromptResult {
  value: string | null;
  input: string;
}

export interface ModalOptions {
  title: string;
  body: Node | string;
  buttons: ModalButton[];
}

function makeOverlay(): HTMLElement {
  const overlay = document.createElement("div");
  overlay.className = "modal-overlay";
  overlay.dataset.testid = "modal";
  return overlay;
}

function makeTitle(title: string): HTMLElement {
  const el = document.createElement("h2");
  el.className = "modal-title";
  el.dataset.testid = "modal-title";
  el.textContent = title;
  return el;
}

function makeBody(body: Node | string): HTMLElement {
  const el = document.createElement("div");
  el.className = "modal-body";
  el.dataset.testid = "modal-body";
  if (typeof body === "string") {
    el.textContent = body;
  } else {
    el.append(body);
  }
  return el;
}

export function openModal(options: ModalOptions): Promise<string> {
  return new Promise((resolve) => {
    const overlay = makeOverlay();
    const dialog = document.createElement("div");
    dialog.className = "modal-dialog";
    dialog.append(makeTitle(options.title), makeBody(options.body));

    const buttons = document.createElement("div");
    buttons.className = "modal-buttons";
    for (const buttonSpec of options.buttons) {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "modal-button";
      if (buttonSpec.primary) {
        button.classList.add("is-primary");
      }
      button.dataset.testid = "modal-button";
      button.textContent = buttonSpec.label;
      button.addEventListener("click", () => {
        overlay.remove();
        resolve(buttonSpec.value);
      });
      buttons.append(button);
    }
    dialog.append(buttons);
    overlay.append(dialog);
    document.body.append(overlay);
  });
}

export function confirmModal(options: {
  title: string;
  message: string;
  confirmLabel: string;
  cancelLabel?: string;
}): Promise<boolean> {
  return openModal({
    title: options.title,
    body: options.message,
    buttons: [
      { label: options.cancelLabel ?? "Cancel", value: "cancel" },
      { label: options.confirmLabel, value: "confirm", primary: true },
    ],
  }).then((value) => value === "confirm");
}

export function promptModal(options: {
  title: string;
  label: string;
  initial?: string;
  confirmLabel: string;
  cancelLabel?: string;
}): Promise<PromptResult> {
  return new Promise((resolve) => {
    const input = document.createElement("input");
    input.className = "modal-input";
    input.dataset.testid = "modal-input";
    input.type = "text";
    input.value = options.initial ?? "";

    const fieldLabel = document.createElement("label");
    fieldLabel.className = "modal-field-label";
    fieldLabel.textContent = options.label;
    fieldLabel.append(input);

    openModal({
      title: options.title,
      body: fieldLabel,
      buttons: [
        { label: options.cancelLabel ?? "Cancel", value: "cancel" },
        { label: options.confirmLabel, value: "confirm", primary: true },
      ],
    }).then((value) =>
      resolve(value === "confirm" ? { value, input: input.value } : { value: null, input: input.value }),
    );

    queueMicrotask(() => input.focus());
  });
}