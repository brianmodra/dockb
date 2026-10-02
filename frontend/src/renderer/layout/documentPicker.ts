import type { DocumentAttrs, DocumentWire } from "../api/types";
import { reportError } from "../log";
import { openOverlay } from "./overlay";
import { openSelectList } from "./selectList";

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

export interface DeleteDocumentSelection {
  documentId: string;
  title: string;
}

export function openDeleteDocumentPicker(
  api: DocumentPickerApi,
  options: DocumentPickerOptions = {},
): Promise<DeleteDocumentSelection | null> {
  return api
    .listDocuments()
    .then(
      (documents) => renderDeletePicker(documents),
      (error) => {
        reportError("List documents", error, options.onMessage);
        return null;
      },
    );
}

export function openDocumentAttrsPicker(
  api: DocumentPickerApi,
  options: DocumentPickerOptions = {},
): Promise<DocumentAttrs | null> {
  return api
    .listDocuments()
    .then(
      (documents) => renderEditPicker(documents),
      (error) => {
        reportError("List documents", error, options.onMessage);
        return null;
      },
    );
}

function pickerItems(documents: DocumentWire[]): { key: string; label: string }[] {
  return documents.map((entry) => ({ key: entry.attrs.id, label: entry.attrs.title }));
}

function renderPicker(documents: DocumentWire[]): Promise<string | null> {
  return new Promise((resolve) => {
    const overlay = openOverlay({
      title: "Open document",
      buttons: [{ label: "Cancel", testId: "document-picker-cancel" }],
    });

    if (documents.length === 0) {
      const empty = document.createElement("div");
      empty.className = "modal-body";
      empty.dataset.testid = "document-picker-empty";
      empty.textContent = "No documents yet.";
      overlay.body.append(empty);
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
          overlay.close();
          resolve(entry.attrs.id);
        });
        list.append(item);
      }
      overlay.body.append(list);
    }

    overlay.buttons["document-picker-cancel"].addEventListener("click", () => {
      overlay.close();
      resolve(null);
    });
  });
}

function renderDeletePicker(documents: DocumentWire[]): Promise<DeleteDocumentSelection | null> {
  const selected = openSelectList({
    title: "Delete document",
    items: pickerItems(documents),
    itemTestId: "document-picker-item",
    cancelTestId: "document-picker-cancel",
    confirmTestId: "document-picker-delete",
    confirmLabel: "Delete",
    emptyMessage: "No documents yet.",
    emptyTestId: "document-picker-empty",
    valueFor: (item) => {
      const entry = documents.find((doc) => doc.attrs.id === item.key);
      return { documentId: item.key, title: entry?.attrs.title ?? item.label };
    },
  });
  return selected.result;
}

function renderEditPicker(documents: DocumentWire[]): Promise<DocumentAttrs | null> {
  const selected = openSelectList({
    title: "Edit document",
    items: pickerItems(documents),
    itemTestId: "document-picker-item",
    cancelTestId: "document-picker-cancel",
    confirmTestId: "document-picker-edit",
    confirmLabel: "Edit",
    emptyMessage: "No documents yet.",
    emptyTestId: "document-picker-empty",
    valueFor: (item) => {
      const entry = documents.find((doc) => doc.attrs.id === item.key);
      return entry?.attrs ?? { id: item.key, title: item.label, author: "" };
    },
  });
  return selected.result;
}

function renderConfirmPicker(documents: DocumentWire[]): Promise<string | null> {
  const selected = openSelectList({
    title: "Open document",
    items: pickerItems(documents),
    itemTestId: "document-picker-item",
    cancelTestId: "document-picker-cancel",
    confirmTestId: "document-picker-open",
    confirmLabel: "Open",
    emptyMessage: "No documents yet.",
    emptyTestId: "document-picker-empty",
    valueFor: (item) => item.key,
  });
  return selected.result;
}
