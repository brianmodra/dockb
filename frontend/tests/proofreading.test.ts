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

function setup(
  options: {
    paragraph?: ProofreadingParagraph | null;
    documentId?: string | null;
    documentIdRef?: { current: string | null };
  } = {},
) {
  const api = {
    checkText: vi.fn(),
    postGlossary: vi.fn(),
  };
  const target: ProofreadingTarget = {
    currentProofreadingParagraph: vi.fn(() => (options.paragraph === undefined ? paragraph : options.paragraph)),
    setProofreadingDiagnostics: vi.fn(() => [mappedDiagnostic]),
    clearProofreadingDiagnostics: vi.fn(),
    applyProofreadingReplacement: vi.fn(() => true),
  };
  const onMessage = vi.fn();
  const onShowActions = vi.fn();
  const onCloseActions = vi.fn();
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
    onShowActions,
    onCloseActions,
    debounceMs: 500,
  });
  return { api, target, controller, onMessage, onShowActions, onCloseActions };
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

describe("ProofreadingController actions", () => {
  it("shows the diagnostic's actions through onShowActions", () => {
    const { controller, onShowActions } = setup();

    controller.showActions(mappedDiagnostic);

    expect(onShowActions).toHaveBeenCalledTimes(1);
    expect(onShowActions).toHaveBeenCalledWith([
      { text: '"teh" — Possible spelling mistake' },
      { button: { label: "the", function: "proofreading-replace", args: { replacement: "the" } } },
      { button: { label: "tea", function: "proofreading-replace", args: { replacement: "tea" } } },
      { button: { label: "ten", function: "proofreading-replace", args: { replacement: "ten" } } },
      { button: { label: "tech", function: "proofreading-replace", args: { replacement: "tech" } } },
      { button: { label: "tee", function: "proofreading-replace", args: { replacement: "tee" } } },
      { button: { label: "Add to dictionary", function: "proofreading-add-word", args: { word: "teh" } } },
    ]);
  });

  it("applies the chosen replacement, closes the actions, and re-checks", async () => {
    const { api, target, controller, onCloseActions } = setup();
    api.checkText.mockResolvedValue({ language: "en-US", diagnostics: [] });
    controller.showActions(mappedDiagnostic);

    controller.applyActiveReplacement("the");
    await vi.advanceTimersByTimeAsync(500);

    expect(target.applyProofreadingReplacement).toHaveBeenCalledWith(mappedDiagnostic, "the");
    expect(onCloseActions).toHaveBeenCalledTimes(1);
    expect(api.checkText).toHaveBeenCalledTimes(1);
  });

  it("closes the actions without re-checking when the replacement no longer applies", async () => {
    const { api, target, controller, onCloseActions } = setup();
    target.applyProofreadingReplacement = vi.fn(() => false);
    controller.showActions(mappedDiagnostic);

    controller.applyActiveReplacement("the");
    await vi.advanceTimersByTimeAsync(500);

    expect(onCloseActions).toHaveBeenCalledTimes(1);
    expect(api.checkText).not.toHaveBeenCalled();
  });

  it("does nothing when no diagnostic is active", async () => {
    const { api, target, controller, onCloseActions } = setup();

    controller.applyActiveReplacement("the");
    await vi.advanceTimersByTimeAsync(500);

    expect(target.applyProofreadingReplacement).not.toHaveBeenCalled();
    expect(onCloseActions).not.toHaveBeenCalled();
    expect(api.checkText).not.toHaveBeenCalled();
  });

  it("adds the word to this document's glossary, closes the actions, and re-checks", async () => {
    const { api, controller, onCloseActions } = setup();
    api.postGlossary.mockResolvedValue({ words: ["Karakas", "teh"] });
    api.checkText.mockResolvedValue({ language: "en-US", diagnostics: [] });
    controller.showActions(mappedDiagnostic);

    await controller.addActiveWord();

    expect(api.postGlossary).toHaveBeenCalledWith("d-1", "teh");
    expect(api.checkText).toHaveBeenCalledTimes(1);
    expect(onCloseActions).toHaveBeenCalledTimes(1);
  });

  it("reports a glossary failure and keeps the actions open", async () => {
    const { api, controller, onMessage, onCloseActions } = setup();
    api.postGlossary.mockRejectedValue(new Error("nope"));
    controller.showActions(mappedDiagnostic);

    await controller.addActiveWord();

    expect(onMessage).toHaveBeenCalledWith(expect.stringContaining("nope"));
    expect(onCloseActions).not.toHaveBeenCalled();
  });

  it("does nothing when there is no open document", async () => {
    const { api, controller, onCloseActions } = setup({ documentId: null });
    controller.showActions(mappedDiagnostic);

    await controller.addActiveWord();

    expect(api.postGlossary).not.toHaveBeenCalled();
    expect(onCloseActions).not.toHaveBeenCalled();
  });

  it("closes the actions on dispose", () => {
    const { controller, onCloseActions } = setup();
    controller.showActions(mappedDiagnostic);

    controller.dispose();

    expect(onCloseActions).toHaveBeenCalledTimes(1);
  });
});
