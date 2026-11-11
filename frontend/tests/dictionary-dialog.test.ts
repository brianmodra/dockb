import { afterEach, describe, expect, it, vi } from "vitest";
import { openDictionaryDialog } from "../src/renderer/layout/dictionaryDialog";

afterEach(() => {
  document.body.replaceChildren();
});

function make() {
  const api = {
    getGlossary: vi.fn(),
    postGlossary: vi.fn(),
    deleteGlossary: vi.fn(),
  };
  const onMessage = vi.fn();
  const onWordsChanged = vi.fn();
  const open = (documentId: string | null = "d-1"): void => {
    openDictionaryDialog({ api, documentId, onMessage, onWordsChanged });
  };
  return { api, onMessage, onWordsChanged, open };
}

function renderedWords(): string[] {
  return Array.from(
    document.querySelectorAll('[data-testid="dictionary-words"] .dictionary-word span'),
  ).map((node) => node.textContent ?? "");
}

function addWord(word: string): void {
  const input = document.querySelector<HTMLInputElement>('[data-testid="dictionary-word-input"]')!;
  input.value = word;
  input.dispatchEvent(new Event("input", { bubbles: true }));
  document.querySelector<HTMLButtonElement>('[data-testid="dictionary-add"]')!.click();
}

describe("dictionary dialog", () => {
  it("reports and stays closed when no document is open", () => {
    const { onMessage, open } = make();
    open(null);

    expect(document.querySelector('[data-testid="modal"]')).toBeNull();
    expect(onMessage).toHaveBeenCalledWith("No document is open.");
  });

  it("loads and renders the stored words", async () => {
    const { api, open } = make();
    api.getGlossary.mockResolvedValue({ words: ["Karakas", "teh"] });
    open();

    await vi.waitFor(() => {
      expect(renderedWords()).toEqual(["Karakas", "teh"]);
    });
    expect(api.getGlossary).toHaveBeenCalledWith("d-1");
  });

  it("adds a word through POST and reflects the returned list", async () => {
    const { api, onWordsChanged, open } = make();
    api.getGlossary.mockResolvedValue({ words: ["Karakas"] });
    api.postGlossary.mockResolvedValue({ words: ["Karakas", "teh"] });
    open();
    await vi.waitFor(() => expect(renderedWords()).toEqual(["Karakas"]));

    addWord("teh");

    await vi.waitFor(() => {
      expect(api.postGlossary).toHaveBeenCalledWith("d-1", "teh");
      expect(renderedWords()).toEqual(["Karakas", "teh"]);
    });
    expect(onWordsChanged).toHaveBeenCalledTimes(1);
  });

  it("keeps Add disabled for a blank word", () => {
    const { api, open } = make();
    api.getGlossary.mockResolvedValue({ words: [] });
    open();
    const add = document.querySelector<HTMLButtonElement>('[data-testid="dictionary-add"]')!;

    expect(add.disabled).toBe(true);
    addWord("   ");
    expect(api.postGlossary).not.toHaveBeenCalled();
  });

  it("removes a word through DELETE and reflects the returned list", async () => {
    const { api, onWordsChanged, open } = make();
    api.getGlossary.mockResolvedValue({ words: ["Karakas", "teh"] });
    api.deleteGlossary.mockResolvedValue({ words: ["Karakas"] });
    open();
    await vi.waitFor(() => expect(renderedWords()).toEqual(["Karakas", "teh"]));

    document.querySelector<HTMLButtonElement>('[data-testid="dictionary-remove"]')!.click();

    await vi.waitFor(() => {
      expect(api.deleteGlossary).toHaveBeenCalledWith("d-1", "Karakas");
      expect(renderedWords()).toEqual(["Karakas"]);
    });
    expect(onWordsChanged).toHaveBeenCalledTimes(1);
  });

  it("reports a failed load and keeps the dialog open", async () => {
    const { api, onMessage, open } = make();
    api.getGlossary.mockRejectedValue(new Error("down"));
    open();

    await vi.waitFor(() => {
      expect(onMessage).toHaveBeenCalledWith(expect.stringContaining("down"));
    });
    expect(document.querySelector('[data-testid="modal"]')).not.toBeNull();
  });

  it("reports a failed add and keeps the dialog open", async () => {
    const { api, onMessage, onWordsChanged, open } = make();
    api.getGlossary.mockResolvedValue({ words: [] });
    api.postGlossary.mockRejectedValue(new Error("nope"));
    open();
    await vi.waitFor(() => expect(renderedWords()).toEqual([]));

    addWord("teh");

    await vi.waitFor(() => {
      expect(onMessage).toHaveBeenCalledWith(expect.stringContaining("nope"));
    });
    expect(document.querySelector('[data-testid="modal"]')).not.toBeNull();
    expect(onWordsChanged).not.toHaveBeenCalled();
  });
});
