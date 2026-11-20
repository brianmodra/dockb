import type { ApiClient } from "../api/client";
import { openOverlay } from "./overlay";

export interface DictionaryDialogOptions {
  api: Pick<ApiClient, "getGlossary" | "postGlossary" | "deleteGlossary">;
  documentId: string | null;
  onMessage: (text: string) => void;
  onWordsChanged?: () => void;
  offline?: () => boolean;
  onOfflineChange?: (listener: (online: boolean) => void) => () => void;
}

/**
 * The document's proofreading dictionary: a text box and Add button above the
 * current words, each with an × to remove it. Adds post one word, removals
 * delete one, and the list always reflects the returned words, so it stays in
 * step with the store. A failed load, add, or removal is reported to the message
 * log and the dialog stays open for another try.
 */
export function openDictionaryDialog(options: DictionaryDialogOptions): void {
  const documentId = options.documentId;
  if (documentId === null) {
    options.onMessage("No document is open.");
    return;
  }

  const overlay = openOverlay({
    title: "Dictionary",
    buttons: [{ label: "Close", testId: "dictionary-close" }],
  });
  overlay.buttons["dictionary-close"].addEventListener("click", () => overlay.close());

  const isOffline = (): boolean => options.offline?.() === true;

  const input = document.createElement("input");
  input.className = "modal-input";
  input.dataset.testid = "dictionary-word-input";
  input.type = "text";
  input.placeholder = "Word";

  const add = document.createElement("button");
  add.type = "button";
  add.className = "modal-button is-primary";
  add.dataset.testid = "dictionary-add";
  add.textContent = "Add";
  add.disabled = true;
  const refreshAdd = (offline = isOffline()): void => {
    add.disabled = offline || input.value.trim() === "";
  };
  input.addEventListener("input", () => refreshAdd());

  const field = document.createElement("div");
  field.className = "dictionary-field";
  field.append(input, add);

  const list = document.createElement("div");
  list.className = "dictionary-words";
  list.dataset.testid = "dictionary-words";

  overlay.body.append(field, list);

  let currentWords: string[] = [];
  const render = (words: string[]): void => {
    currentWords = words;
    list.replaceChildren();
    for (const word of words) {
      const row = document.createElement("div");
      row.className = "dictionary-word";
      const text = document.createElement("span");
      text.textContent = word;
      const remove = document.createElement("button");
      remove.type = "button";
      remove.className = "dictionary-remove";
      remove.dataset.testid = "dictionary-remove";
      remove.textContent = "×";
      remove.disabled = isOffline();
      remove.addEventListener("click", () => {
        void removeWord(word);
      });
      row.append(text, remove);
      list.append(row);
    }
  };

  const addWord = async (): Promise<void> => {
    const word = input.value.trim();
    if (word === "") {
      return;
    }
    if (isOffline()) {
      options.onMessage("Unavailable offline.");
      return;
    }
    try {
      const result = await options.api.postGlossary(documentId, word);
      render(result.words);
      input.value = "";
      add.disabled = true;
      options.onWordsChanged?.();
    } catch (error) {
      options.onMessage(`Could not add the word: ${errorMessage(error)}`);
    }
  };

  const removeWord = async (word: string): Promise<void> => {
    if (isOffline()) {
      options.onMessage("Unavailable offline.");
      return;
    }
    try {
      const result = await options.api.deleteGlossary(documentId, word);
      render(result.words);
      options.onWordsChanged?.();
    } catch (error) {
      options.onMessage(`Could not remove the word: ${errorMessage(error)}`);
    }
  };

  add.addEventListener("click", () => {
    void addWord();
  });

  const unsubscribe = options.onOfflineChange?.((online) => {
    refreshAdd(!online);
    render(currentWords);
  });
  const close = overlay.close;
  overlay.close = () => {
    unsubscribe?.();
    close();
  };

  void options.api
    .getGlossary(documentId)
    .then((result) => render(result.words))
    .catch((error) => options.onMessage(`Could not load the dictionary: ${errorMessage(error)}`));
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}
