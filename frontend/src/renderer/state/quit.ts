import { openModal } from "../layout/modals";

export interface UnsavedChangesOptions {
  isDirty: () => boolean;
  save?: () => Promise<unknown>;
  /** The confirm button's wording: "Save and Quit", or "Save" when quitting is not what happens next. */
  confirmLabel: string;
  proceed: () => void;
}

/**
 * Offer to save an unsaved buffer before running `proceed`.
 *
 * Returns false when the person cancelled or the save failed, meaning `proceed`
 * must not run; true once it has been called.
 */
export async function confirmUnsaved(options: UnsavedChangesOptions): Promise<boolean> {
  if (!options.isDirty()) {
    options.proceed();
    return true;
  }
  const choice = await openModal({
    title: "Save chapter first?",
    body: "You have unsaved changes.",
    buttons: [
      { label: "Cancel", value: "cancel" },
      { label: "Discard", value: "discard" },
      { label: options.confirmLabel, value: "save", primary: true },
    ],
  });
  if (choice === "cancel") {
    return false;
  }
  if (choice === "save") {
    const saved = options.save ? await options.save() : null;
    if (saved === null) {
      return false;
    }
  }
  options.proceed();
  return true;
}

export interface QuitAppOptions {
  isDirty: () => boolean;
  save?: () => Promise<unknown>;
  onQuit: () => void;
}

export async function quitApp(options: QuitAppOptions): Promise<boolean> {
  return confirmUnsaved({
    isDirty: options.isDirty,
    save: options.save,
    confirmLabel: "Save and Quit",
    proceed: options.onQuit,
  });
}
