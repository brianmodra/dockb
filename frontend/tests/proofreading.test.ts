import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ProofreadingDiagnostic } from "../src/renderer/api/types";
import {
  ProofreadingController,
  type ProofreadingTarget,
} from "../src/renderer/layout/proofreading";
import type { ProofreadingParagraph, WysiwygDiagnostic } from "../src/renderer/layout/wysiwyg";

const paragraph: ProofreadingParagraph = {
  paragraphId: "p-1",
  paragraphIndex: 0,
  text: "teh cat",
  focus: { start: 0, end: 7 },
  contentStart: 1,
  contentEnd: 8,
};

const wireDiagnostic: ProofreadingDiagnostic = {
  rule_id: "MORFOLOGIK_RULE_EN_US",
  category: "TYPOS",
  severity: "warning",
  message: "Possible spelling mistake",
  start: 0,
  end: 3,
  replacements: ["the", "tea", "ten", "tech", "tee", "teak"],
  in_focus: true,
};

const mappedDiagnostic: WysiwygDiagnostic = {
  ...wireDiagnostic,
  from: 1,
  to: 4,
  word: "teh",
};

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

async function flush(): Promise<void> {
  for (let i = 0; i < 6; i += 1) {
    await Promise.resolve();
  }
}

function setup(
  options: {
    paragraph?: ProofreadingParagraph | null;
    documentId?: string | null;
    documentIdRef?: { current: string | null };
  } = {},
) {
  const api = {
    checkText: vi.fn(),
    getGlossary: vi.fn(),
    putGlossary: vi.fn(),
  };
  const target: ProofreadingTarget = {
    currentProofreadingParagraph: vi.fn(() => (options.paragraph === undefined ? paragraph : options.paragraph)),
    setProofreadingDiagnostics: vi.fn(() => [mappedDiagnostic]),
    clearProofreadingDiagnostics: vi.fn(),
    applyProofreadingReplacement: vi.fn(() => true),
  };
  const onMessage = vi.fn();
  const controller = new ProofreadingController({
    api,
    target,
    documentId: () =>
      options.documentIdRef
        ? options.documentIdRef.current
        : options.documentId === undefined
          ? "d-1"
          : options.documentId,
    language: () => "en-US",
    onMessage,
    debounceMs: 500,
  });
  return { api, target, controller, onMessage };
}

beforeEach(() => {
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
  document.body.replaceChildren();
});

describe("ProofreadingController checks", () => {
  it("waits for the debounce before asking the backend", async () => {
    const { api, controller } = setup();
    api.checkText.mockResolvedValue({ language: "en-US", diagnostics: [] });

    controller.schedule();
    await vi.advanceTimersByTimeAsync(499);
    expect(api.checkText).not.toHaveBeenCalled();

    await vi.advanceTimersByTimeAsync(1);
    expect(api.checkText).toHaveBeenCalledTimes(1);
    expect(api.checkText).toHaveBeenCalledWith(
      {
        text: "teh cat",
        language: "en-US",
        document_id: "d-1",
        paragraph_id: "p-1",
        focus: { start: 0, end: 7 },
      },
      expect.any(AbortSignal),
    );
  });

  it("replaces a pending debounce with the newer call", async () => {
    const { api, controller } = setup();
    api.checkText.mockResolvedValue({ language: "en-US", diagnostics: [] });

    controller.schedule();
    await vi.advanceTimersByTimeAsync(300);
    controller.schedule();
    await vi.advanceTimersByTimeAsync(499);
    expect(api.checkText).not.toHaveBeenCalled();

    await vi.advanceTimersByTimeAsync(1);
    expect(api.checkText).toHaveBeenCalledTimes(1);
  });

  it("decorates the paragraph with the returned diagnostics", async () => {
    const { api, target, controller } = setup();
    api.checkText.mockResolvedValue({ language: "en-US", diagnostics: [wireDiagnostic] });

    await controller.checkNow();

    expect(target.setProofreadingDiagnostics).toHaveBeenCalledWith(paragraph, [wireDiagnostic]);
  });

  it("aborts the earlier request and ignores its late reply", async () => {
    const first = deferred<{ language: string; diagnostics: ProofreadingDiagnostic[] }>();
    const second = deferred<{ language: string; diagnostics: ProofreadingDiagnostic[] }>();
    const { api, target, controller } = setup();
    api.checkText
      .mockReturnValueOnce(first.promise)
      .mockReturnValueOnce(second.promise);

    const firstRun = controller.checkNow();
    const firstSignal = api.checkText.mock.calls[0][1] as AbortSignal;
    const secondRun = controller.checkNow();
    expect(firstSignal.aborted).toBe(true);

    second.resolve({ language: "en-US", diagnostics: [wireDiagnostic] });
    await secondRun;
    expect(target.setProofreadingDiagnostics).toHaveBeenCalledTimes(1);

    const later = { ...wireDiagnostic, message: "stale" };
    first.resolve({ language: "en-US", diagnostics: [later] });
    await firstRun;
    expect(target.setProofreadingDiagnostics).toHaveBeenCalledTimes(1);
    expect(target.setProofreadingDiagnostics).not.toHaveBeenCalledWith(paragraph, [later]);
  });

  it("drops a reply when the paragraph text has moved", async () => {
    const pending = deferred<{ language: string; diagnostics: ProofreadingDiagnostic[] }>();
    const { api, target, controller } = setup();
    api.checkText.mockReturnValue(pending.promise);

    const run = controller.checkNow();
    target.currentProofreadingParagraph = vi.fn(() => ({ ...paragraph, text: "teh cat!" }));
    pending.resolve({ language: "en-US", diagnostics: [wireDiagnostic] });
    await run;

    expect(target.setProofreadingDiagnostics).not.toHaveBeenCalled();
  });

  it("drops a reply when the open document has changed", async () => {
    const pending = deferred<{ language: string; diagnostics: ProofreadingDiagnostic[] }>();
    const documentIdRef = { current: "d-1" };
    const { api, target, controller } = setup({ documentIdRef });
    api.checkText.mockReturnValue(pending.promise);

    const run = controller.checkNow();
    documentIdRef.current = "d-2";
    pending.resolve({ language: "en-US", diagnostics: [wireDiagnostic] });
    await run;

    expect(target.setProofreadingDiagnostics).not.toHaveBeenCalled();
  });

  it("clears diagnostics and skips the request for an empty paragraph", async () => {
    const { api, target, controller } = setup({ paragraph: { ...paragraph, text: "" } });

    await controller.checkNow();

    expect(api.checkText).not.toHaveBeenCalled();
    expect(target.clearProofreadingDiagnostics).toHaveBeenCalled();
  });

  it("clears diagnostics when there is no paragraph", async () => {
    const { api, target, controller } = setup({ paragraph: null });

    controller.schedule();
    await vi.advanceTimersByTimeAsync(500);

    expect(api.checkText).not.toHaveBeenCalled();
    expect(target.clearProofreadingDiagnostics).toHaveBeenCalled();
  });

  it("reports a failed check without throwing", async () => {
    const { api, controller, onMessage } = setup();
    api.checkText.mockRejectedValue(new Error("backend down"));

    await controller.checkNow();

    expect(onMessage).toHaveBeenCalledWith(expect.stringContaining("backend down"));
  });

  it("does not report an aborted check", async () => {
    const { api, controller, onMessage } = setup();
    api.checkText.mockRejectedValue(new DOMException("aborted", "AbortError"));

    await controller.checkNow();

    expect(onMessage).not.toHaveBeenCalled();
  });
});

describe("ProofreadingController popover", () => {
  it("shows the message, at most five replacements, and Add to dictionary", () => {
    const { controller } = setup();

    controller.openPopover(mappedDiagnostic, { x: 12, y: 34 });

    const popover = document.querySelector<HTMLElement>('[data-testid="proofreading-popover"]');
    expect(popover).not.toBeNull();
    expect(popover!.textContent).toContain("Possible spelling mistake");
    expect(popover!.style.left).toBe("12px");
    expect(popover!.style.top).toBe("34px");
    expect(popover!.querySelectorAll('[data-testid="proofreading-replacement"]')).toHaveLength(5);
    expect(popover!.querySelector('[data-testid="proofreading-add-word"]')).not.toBeNull();
  });

  it("applies the chosen replacement and closes", async () => {
    const { api, target, controller } = setup();
    api.checkText.mockResolvedValue({ language: "en-US", diagnostics: [] });
    controller.openPopover(mappedDiagnostic, { x: 1, y: 2 });

    const first = document.querySelector<HTMLButtonElement>(
      '[data-testid="proofreading-replacement"]',
    );
    expect(first?.textContent).toBe("the");
    first!.click();
    await flush();

    expect(target.applyProofreadingReplacement).toHaveBeenCalledWith(mappedDiagnostic, "the");
    expect(document.querySelector('[data-testid="proofreading-popover"]')).toBeNull();
  });

  it("adds the word to this document's glossary and re-checks", async () => {
    const { api, controller } = setup();
    api.getGlossary.mockResolvedValue({ words: ["Karakas"] });
    api.putGlossary.mockResolvedValue({ words: ["Karakas", "teh"] });
    api.checkText.mockResolvedValue({ language: "en-US", diagnostics: [] });
    controller.openPopover(mappedDiagnostic, { x: 1, y: 2 });

    document.querySelector<HTMLButtonElement>('[data-testid="proofreading-add-word"]')!.click();
    await flush();

    expect(api.getGlossary).toHaveBeenCalledWith("d-1");
    expect(api.putGlossary).toHaveBeenCalledWith("d-1", ["Karakas", "teh"]);
    expect(api.checkText).toHaveBeenCalledTimes(1);
    expect(document.querySelector('[data-testid="proofreading-popover"]')).toBeNull();
  });

  it("reuses the cached glossary for a second word in the same document", async () => {
    const { api, controller } = setup();
    api.getGlossary.mockResolvedValue({ words: [] });
    api.putGlossary.mockResolvedValue({ words: [] });
    api.checkText.mockResolvedValue({ language: "en-US", diagnostics: [] });

    controller.openPopover(mappedDiagnostic, { x: 1, y: 2 });
    document.querySelector<HTMLButtonElement>('[data-testid="proofreading-add-word"]')!.click();
    await flush();
    controller.openPopover({ ...mappedDiagnostic, word: "cat" }, { x: 1, y: 2 });
    document.querySelector<HTMLButtonElement>('[data-testid="proofreading-add-word"]')!.click();
    await flush();

    expect(api.getGlossary).toHaveBeenCalledTimes(1);
    expect(api.putGlossary).toHaveBeenLastCalledWith("d-1", ["teh", "cat"]);
  });

  it("closes the popover on Escape and on dispose", () => {
    const { controller } = setup();
    controller.openPopover(mappedDiagnostic, { x: 1, y: 2 });
    window.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" }));
    expect(document.querySelector('[data-testid="proofreading-popover"]')).toBeNull();

    controller.openPopover(mappedDiagnostic, { x: 1, y: 2 });
    controller.dispose();
    expect(document.querySelector('[data-testid="proofreading-popover"]')).toBeNull();
  });

  it("closes the popover when the writer clicks outside it", () => {
    const { controller } = setup();
    controller.openPopover(mappedDiagnostic, { x: 1, y: 2 });

    document.body.dispatchEvent(new MouseEvent("pointerdown", { bubbles: true }));

    expect(document.querySelector('[data-testid="proofreading-popover"]')).toBeNull();
  });

  it("reports a glossary failure and keeps the popover open", async () => {
    const { api, controller, onMessage } = setup();
    api.getGlossary.mockRejectedValue(new Error("nope"));
    controller.openPopover(mappedDiagnostic, { x: 1, y: 2 });

    document.querySelector<HTMLButtonElement>('[data-testid="proofreading-add-word"]')!.click();
    await flush();

    expect(onMessage).toHaveBeenCalledWith(expect.stringContaining("nope"));
    expect(document.querySelector('[data-testid="proofreading-popover"]')).not.toBeNull();
  });

  it("does nothing when there is no open document", async () => {
    const { api, controller } = setup({ documentId: null });
    controller.openPopover(mappedDiagnostic, { x: 1, y: 2 });

    document.querySelector<HTMLButtonElement>('[data-testid="proofreading-add-word"]')!.click();
    await flush();

    expect(api.getGlossary).not.toHaveBeenCalled();
    expect(api.putGlossary).not.toHaveBeenCalled();
  });
});
