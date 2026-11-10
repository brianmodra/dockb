import { EditorView } from "@codemirror/view";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { DocumentContentResponse } from "../src/renderer/api/types";
import { EditPanel, type EditPanelApi } from "../src/renderer/layout/editPanel";

const CANONICAL = [
  "---",
  "title: Test",
  "---",
  "",
  '<span data-par-id="p-1">',
  "teh cat",
  "</span>",
  "",
].join("\n");

const ENTITY_CANONICAL = CANONICAL.replace("teh cat", "teh &amp; cat");

function fakeApi(): EditPanelApi {
  return {
    getChapterDocument: vi.fn(async (): Promise<DocumentContentResponse> => ({ content: "", summary: null })),
    saveChapterDocument: vi.fn(
      async (_id: string, content: string): Promise<DocumentContentResponse> => ({
        content,
        summary: null,
      }),
    ),
  };
}

function viewOf(panel: EditPanel): EditorView {
  return (panel as unknown as { view: EditorView }).view;
}

afterEach(() => {
  document.body.replaceChildren();
  vi.restoreAllMocks();
});

describe("EditPanel raw proofreading", () => {
  it("checks the raw paragraph under the cursor and marks its diagnostics", () => {
    const panel = new EditPanel({ api: fakeApi() });
    document.body.append(panel.element);
    panel.setMode("raw");
    panel.setContent(CANONICAL);
    const view = viewOf(panel);
    view.dispatch({ selection: { anchor: CANONICAL.indexOf("teh cat") } });

    const context = panel.proofreadingParagraph();
    expect(context?.text).toBe("teh cat");

    const mapped = panel.setProofreadingDiagnostics(context!, [
      {
        start: 0,
        end: 3,
        message: "Possible spelling mistake",
        rule_id: "MORFOLOGIK_RULE_EN_US",
        severity: "warning",
      },
    ]);

    expect(mapped).toHaveLength(1);
    expect(document.querySelector(".cm-lintRange-warning")).not.toBeNull();
  });

  it("clears raw lint markers when the checked paragraph has moved", () => {
    const panel = new EditPanel({ api: fakeApi() });
    document.body.append(panel.element);
    panel.setMode("raw");
    panel.setContent(CANONICAL);
    const view = viewOf(panel);
    view.dispatch({ selection: { anchor: CANONICAL.indexOf("teh cat") } });
    const context = panel.proofreadingParagraph();
    panel.setProofreadingDiagnostics(context!, [
      {
        start: 0,
        end: 3,
        message: "Possible spelling mistake",
        rule_id: "MORFOLOGIK_RULE_EN_US",
        severity: "warning",
      },
    ]);
    expect(document.querySelector(".cm-lintRange-warning")).not.toBeNull();

    const moved = panel.setProofreadingDiagnostics({ ...context!, text: "teh cat!" }, []);

    expect(moved).toEqual([]);
    expect(document.querySelector(".cm-lintRange-warning")).toBeNull();
  });

  it("opens the clicked spelling diagnostic's own replacements", () => {
    const onDiagnostic = vi.fn();
    const panel = new EditPanel({ api: fakeApi(), onDiagnostic });
    document.body.append(panel.element);
    panel.setMode("raw");
    panel.setContent(CANONICAL.replace("teh cat", "teh cat recieve"));
    const view = viewOf(panel);
    view.dispatch({ selection: { anchor: CANONICAL.indexOf("teh cat") } });
    const context = panel.proofreadingParagraph();
    const mapped = panel.setProofreadingDiagnostics(context!, [
      {
        start: 0,
        end: 3,
        message: "Possible spelling mistake",
        rule_id: "MORFOLOGIK_RULE_EN_US",
        severity: "warning",
        replacements: ["the"],
      },
      {
        start: 8,
        end: 15,
        message: "Possible spelling mistake",
        rule_id: "MORFOLOGIK_RULE_EN_US",
        severity: "warning",
        replacements: ["receive"],
      },
    ]);
    vi.spyOn(view, "posAtCoords").mockReturnValue(mapped[1].from + 1);

    panel.element
      .querySelector<HTMLElement>('[data-testid="edit-raw"]')!
      .dispatchEvent(new MouseEvent("contextmenu", { bubbles: true, cancelable: true }));

    expect(onDiagnostic).toHaveBeenCalledWith(
      expect.objectContaining({ word: "recieve", replacements: ["receive"] }),
      expect.any(Object),
    );
  });

  it("reports and replaces an entity-encoded word through its decoded form", () => {
    const onDiagnostic = vi.fn();
    const panel = new EditPanel({ api: fakeApi(), onDiagnostic });
    document.body.append(panel.element);
    panel.setMode("raw");
    panel.setContent(ENTITY_CANONICAL);
    const view = viewOf(panel);
    view.dispatch({ selection: { anchor: ENTITY_CANONICAL.indexOf("teh &amp; cat") } });
    const context = panel.proofreadingParagraph();
    expect(context?.text).toBe("teh & cat");
    const [diagnostic] = panel.setProofreadingDiagnostics(context!, [
      {
        start: 4,
        end: 5,
        message: "Use a word",
        rule_id: "AMPERSAND",
        severity: "info",
      },
    ]);

    vi.spyOn(view, "posAtCoords").mockReturnValue(diagnostic.from + 1);
    panel.element
      .querySelector<HTMLElement>('[data-testid="edit-raw"]')!
      .dispatchEvent(new MouseEvent("contextmenu", { bubbles: true, cancelable: true }));
    expect(onDiagnostic).toHaveBeenCalledWith(
      expect.objectContaining({ word: "&", from: diagnostic.from, to: diagnostic.to }),
      expect.any(Object),
    );

    expect(panel.applyProofreadingReplacement(diagnostic, "and")).toBe(true);
    expect(panel.content()).toContain("teh and cat");
    expect(panel.content()).not.toContain("&amp;");
  });

  it("refuses a raw replacement whose range no longer holds the diagnostic's word", () => {
    const panel = new EditPanel({ api: fakeApi() });
    document.body.append(panel.element);
    panel.setMode("raw");
    panel.setContent(CANONICAL);
    const view = viewOf(panel);
    view.dispatch({ selection: { anchor: CANONICAL.indexOf("teh cat") } });
    const context = panel.proofreadingParagraph();
    const [diagnostic] = panel.setProofreadingDiagnostics(context!, [
      {
        start: 0,
        end: 3,
        message: "Possible spelling mistake",
        rule_id: "MORFOLOGIK_RULE_EN_US",
        severity: "warning",
      },
    ]);

    view.dispatch({ changes: { from: diagnostic.from, insert: "x" } });

    expect(panel.applyProofreadingReplacement(diagnostic, "the")).toBe(false);
    expect(panel.content()).toContain("xteh cat");
  });

  it("replaces a raw diagnostic in one edit", () => {
    const panel = new EditPanel({ api: fakeApi() });
    document.body.append(panel.element);
    panel.setMode("raw");
    panel.setContent(CANONICAL);
    viewOf(panel).dispatch({ selection: { anchor: CANONICAL.indexOf("teh cat") } });
    const context = panel.proofreadingParagraph();
    const [diagnostic] = panel.setProofreadingDiagnostics(context!, [
      {
        start: 0,
        end: 3,
        message: "Possible spelling mistake",
        rule_id: "MORFOLOGIK_RULE_EN_US",
        severity: "warning",
      },
    ]);

    expect(panel.applyProofreadingReplacement(diagnostic, "the")).toBe(true);
    expect(panel.content()).toContain("the cat");
    expect(panel.content()).not.toContain("teh cat");
  });
});
