import { openModal } from "../layout/modals";

export interface QuitAppOptions {
  isDirty: () => boolean;
  save?: () => Promise<unknown>;
  onQuit: () => void;
}

export async function quitApp(options: QuitAppOptions): Promise<boolean> {
  if (!options.isDirty()) {
    options.onQuit();
    return true;
  }
  const choice = await openModal({
    title: "Save chapter first?",
    body: "You have unsaved changes.",
    buttons: [
      { label: "Cancel", value: "cancel" },
      { label: "Discard", value: "discard" },
      { label: "Save and Quit", value: "save", primary: true },
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
  options.onQuit();
  return true;
}