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

/** The backdrop every modal sits on. Shared so the auth dialogs match the rest. */
export function makeOverlay(): HTMLElement {
  const overlay = document.createElement("div");
  overlay.className = "modal-overlay";
  overlay.dataset.testid = "modal";
  return overlay;
}

export function makeTitle(title: string): HTMLElement {
  const el = document.createElement("h2");
  el.className = "modal-title";
  el.dataset.testid = "modal-title";
  el.textContent = title;
  return el;
}

export function makeBody(body: Node | string): HTMLElement {
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

export interface EditDocumentResult {
  title: string;
  author: string;
}

export function editDocumentModal(
  options: { title: string; author: string },
): Promise<EditDocumentResult | null> {
  return new Promise((resolve) => {
    const overlay = makeOverlay();
    const dialog = document.createElement("div");
    dialog.className = "modal-dialog";

    const titleInput = document.createElement("input");
    titleInput.className = "modal-input";
    titleInput.dataset.testid = "modal-input-title";
    titleInput.type = "text";
    titleInput.value = options.title;

    const authorInput = document.createElement("input");
    authorInput.className = "modal-input";
    authorInput.dataset.testid = "modal-input-author";
    authorInput.type = "text";
    authorInput.value = options.author;

    const titleLabel = document.createElement("label");
    titleLabel.className = "modal-field-label";
    titleLabel.textContent = "Title";
    titleLabel.append(titleInput);

    const authorLabel = document.createElement("label");
    authorLabel.className = "modal-field-label";
    authorLabel.textContent = "Author";
    authorLabel.append(authorInput);

    const body = document.createElement("div");
    body.className = "modal-fields";
    body.append(titleLabel, authorLabel);

    const save = document.createElement("button");
    save.type = "button";
    save.className = "modal-button is-primary";
    save.dataset.testid = "modal-button";
    save.textContent = "Save";
    save.disabled = titleInput.value.trim() === "";
    titleInput.addEventListener("input", () => {
      save.disabled = titleInput.value.trim() === "";
    });

    const cancel = document.createElement("button");
    cancel.type = "button";
    cancel.className = "modal-button";
    cancel.dataset.testid = "modal-button";
    cancel.textContent = "Cancel";

    dialog.append(makeTitle("Edit document"), makeBody(body));
    const buttons = document.createElement("div");
    buttons.className = "modal-buttons";
    buttons.append(cancel, save);
    dialog.append(buttons);

    cancel.addEventListener("click", () => {
      overlay.remove();
      resolve(null);
    });
    save.addEventListener("click", () => {
      if (save.disabled) {
        return;
      }
      overlay.remove();
      resolve({ title: titleInput.value, author: authorInput.value });
    });

    overlay.append(dialog);
    document.body.append(overlay);

    queueMicrotask(() => titleInput.select());
  });
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