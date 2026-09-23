import type { AppState } from "../api/types";

export interface StartupOptions {
  savedState: AppState;
  loadDocument: (documentId: string) => Promise<void>;
  pickDocument: () => Promise<string | null>;
  restoreView: (panelWidths: Record<string, number> | null, editMode: string | null) => void;
}

export async function runStartup(options: StartupOptions): Promise<void> {
  options.restoreView(options.savedState.panel_widths, options.savedState.edit_mode);
  const documentId = options.savedState.last_document_id ?? (await options.pickDocument());
  if (documentId === null) {
    return;
  }
  await options.loadDocument(documentId);
}