import type { DocumentWire } from "../api/types";
import { reportError } from "../log";

export interface DocumentPickerApi {
  listDocuments(): Promise<DocumentWire[]>;
}

export interface DocumentPickerOptions {
  onMessage?: (text: string) => void;
}

export function openDocumentPicker(api: DocumentPickerApi, options: DocumentPickerOptions = {}): Promise<string | null> {
  return api
    .listDocuments()
    .then(
      (documents) => renderPicker(documents),
      (error) => {
        reportError("List documents", error, options.onMessage);
        return null;
      },
    );
}

export function openDocumentPickerConfirm(
  api: DocumentPickerApi,
  options: DocumentPickerOptions = {},
): Promise<string | null> {
  return api
    .listDocuments()
    .then(
      (documents) => renderConfirmPicker(documents),
      (error) => {
        reportError("List documents", error, options.onMessage);
        return null;
      },
    );
}

function renderPicker(documents: DocumentWire[]): Promise<string | null> {
  return new Promise((resolve) => {
    const overlay = document.createElement("div");
    overlay.className = "modal-overlay";
    overlay.dataset.testid = "modal";

    const dialog = document.createElement("div");
    dialog.className = "modal-dialog";

    const title = document.createElement("h2");
    title.className = "modal-title";
    title.dataset.testid = "modal-title";
    title.textContent = "Open document";
    dialog.append(title);

    if (documents.length === 0) {
      const empty = document.createElement("div");
      empty.className = "modal-body";
      empty.dataset.testid = "document-picker-empty";
      empty.textContent = "No documents yet.";
      dialog.append(empty);
    } else {
      const list = document.createElement("div");
      list.className = "document-picker-list";
      for (const entry of documents) {
        const item = document.createElement("button");
        item.type = "button";
        item.className = "document-picker-item";
        item.dataset.testid = "document-picker-item";
        item.textContent = entry.attrs.title;
        item.addEventListener("click", () => {
          overlay.remove();
          resolve(entry.attrs.id);
        });
        list.append(item);
      }
      dialog.append(list);
    }

    const buttons = document.createElement("div");
    buttons.className = "modal-buttons";
    const cancel = document.createElement("button");
    cancel.type = "button";
    cancel.className = "modal-button";
    cancel.dataset.testid = "document-picker-cancel";
    cancel.textContent = "Cancel";
    cancel.addEventListener("click", () => {
      overlay.remove();
      resolve(null);
    });
    buttons.append(cancel);
    dialog.append(buttons);

    overlay.append(dialog);
    document.body.append(overlay);
  });
}

function renderConfirmPicker(documents: DocumentWire[]): Promise<string | null> {
  return new Promise((resolve) => {
    const overlay = document.createElement("div");
    overlay.className = "modal-overlay";
    overlay.dataset.testid = "modal";

    const dialog = document.createElement("div");
    dialog.className = "modal-dialog";

    const title = document.createElement("h2");
    title.className = "modal-title";
    title.dataset.testid = "modal-title";
    title.textContent = "Open document";
    dialog.append(title);

    let selectedId: string | null = null;

    const openButton = document.createElement("button");
    openButton.type = "button";
    openButton.className = "modal-button is-primary";
    openButton.dataset.testid = "document-picker-open";
    openButton.textContent = "Open";
    openButton.disabled = true;

    if (documents.length === 0) {
      const empty = document.createElement("div");
      empty.className = "modal-body";
      empty.dataset.testid = "document-picker-empty";
      empty.textContent = "No documents yet.";
      dialog.append(empty);
    } else {
      const list = document.createElement("div");
      list.className = "document-picker-list";
      for (const entry of documents) {
        const item = document.createElement("button");
        item.type = "button";
        item.className = "document-picker-item";
        item.dataset.testid = "document-picker-item";
        item.textContent = entry.attrs.title;
        item.addEventListener("click", () => {
          selectedId = entry.attrs.id;
          for (const other of list.querySelectorAll(".document-picker-item--selected")) {
            other.classList.remove("document-picker-item--selected");
          }
          item.classList.add("document-picker-item--selected");
          openButton.disabled = false;
        });
        list.append(item);
      }
      dialog.append(list);
    }

    openButton.addEventListener("click", () => {
      if (selectedId === null) {
        return;
      }
      overlay.remove();
      resolve(selectedId);
    });

    const buttons = document.createElement("div");
    buttons.className = "modal-buttons";
    const cancel = document.createElement("button");
    cancel.type = "button";
    cancel.className = "modal-button";
    cancel.dataset.testid = "document-picker-cancel";
    cancel.textContent = "Cancel";
    cancel.addEventListener("click", () => {
      overlay.remove();
      resolve(null);
    });
    buttons.append(cancel, openButton);
    dialog.append(buttons);

    overlay.append(dialog);
    document.body.append(overlay);
  });
}