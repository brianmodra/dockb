import type { ApiClient } from "../api/client";
import type { AppState, AppStatePatch } from "../api/types";
import { reportError } from "../log";

export interface AppStateControllerOptions {
  onMessage?: (text: string) => void;
}

export class AppStateController {
  constructor(
    private readonly api: Pick<ApiClient, "getAppState" | "putAppState">,
    private readonly options: AppStateControllerOptions = {},
  ) {}

  async load(): Promise<AppState> {
    try {
      return await this.api.getAppState();
    } catch (error) {
      reportError("Load app state", error, this.options.onMessage);
      return { last_document_id: null, panel_widths: null, edit_mode: null };
    }
  }

  async saveLastDocument(documentId: string): Promise<void> {
    await this.persist({ last_document_id: documentId });
  }

  async saveEditMode(editMode: string): Promise<void> {
    await this.persist({ edit_mode: editMode });
  }

  async savePanelWidths(panelWidths: Record<string, number>): Promise<void> {
    await this.persist({ panel_widths: panelWidths });
  }

  private async persist(patch: AppStatePatch): Promise<void> {
    try {
      await this.api.putAppState(patch);
    } catch (error) {
      reportError("Save app state", error, this.options.onMessage);
    }
  }
}