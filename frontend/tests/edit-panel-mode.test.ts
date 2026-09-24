import { afterEach, describe, expect, it, vi } from "vitest";
import type { DocumentContentResponse } from "../src/renderer/api/types";
import { EditPanel, type EditPanelApi } from "../src/renderer/layout/editPanel";

function doc(content: string): DocumentContentResponse {
  return { content, summary: null };
}

function fakeApi(): EditPanelApi {
  return {
    getChapterDocument: vi.fn(async (): Promise<DocumentContentResponse> => doc("")),
    saveChapterDocument: vi.fn(
      async (_id: string, content: string): Promise<DocumentContentResponse> => doc(content),
    ),
  };
}

function rawHostOf(panel: EditPanel): HTMLElement {
  return panel.element.querySelector<HTMLElement>("[data-testid='edit-raw']")!;
}

function wysiwygHostOf(panel: EditPanel): HTMLElement {
  return panel.element.querySelector<HTMLElement>("[data-testid='edit-wysiwyg']")!;
}

afterEach(() => {
  document.body.replaceChildren();
  vi.restoreAllMocks();
});

describe("EditPanel mode switching", () => {
  it("starts in wysiwyg mode with the raw view hidden", () => {
    const panel = new EditPanel({ api: fakeApi() });
    document.body.append(panel.element);

    expect(wysiwygHostOf(panel).hidden).toBe(false);
    expect(rawHostOf(panel).hidden).toBe(true);
  });

  it("shows the raw view and hides the wysiwyg view in raw mode", () => {
    const panel = new EditPanel({ api: fakeApi() });
    document.body.append(panel.element);

    panel.setMode("raw");

    expect(rawHostOf(panel).hidden).toBe(false);
    expect(wysiwygHostOf(panel).hidden).toBe(true);
  });

  it("toggling to raw then back preserves the loaded text", async () => {
    const api = fakeApi();
    api.getChapterDocument = vi.fn(async () => doc("extra body"));
    const panel = new EditPanel({ api });
    document.body.append(panel.element);
    await panel.load("c1");

    panel.setMode("raw");
    panel.setMode("wysiwyg");

    expect(panel.content()).toBe("extra body");
  });

  it("keeps a wysiwyg edit when switching to raw and back", async () => {
    const api = fakeApi();
    const panel = new EditPanel({ api });
    document.body.append(panel.element);
    await panel.load("c1");

    panel.setMode("wysiwyg");
    panel.setContent("edited in wysiwyg");
    panel.setMode("raw");
    panel.setMode("wysiwyg");

    expect(panel.content()).toBe("edited in wysiwyg");
  });

  it("shows wysiwyg text in the raw view after switching", async () => {
    const api = fakeApi();
    const panel = new EditPanel({ api });
    document.body.append(panel.element);
    await panel.load("c1");

    panel.setMode("wysiwyg");
    panel.setContent("seen in both");
    panel.setMode("raw");

    const rawEditor = panel.element.querySelector<HTMLElement>(".cm-editor")!;
    expect(rawEditor.textContent).toContain("seen in both");
  });

  it("isDirty tracks edits regardless of the active mode", async () => {
    const api = fakeApi();
    const panel = new EditPanel({ api });
    document.body.append(panel.element);
    await panel.load("c1");

    panel.setMode("wysiwyg");
    panel.setContent("dirty text");
    expect(panel.isDirty()).toBe(true);

    panel.setMode("raw");
    expect(panel.isDirty()).toBe(true);

    await panel.save();
    expect(panel.isDirty()).toBe(false);
  });

  it("shows the full canonical markup in the raw view when nothing was edited", async () => {
    const canonicalFile = [
      "---",
      "id: c1",
      "title: Opening 1",
      "---",
      "",
      '<span data-par-id="p-1">',
      "Chapter text.",
      "</span>",
    ].join("\n");
    const api = fakeApi();
    api.getChapterDocument = vi.fn(async () => doc(canonicalFile));
    const panel = new EditPanel({ api });
    document.body.append(panel.element);
    await panel.load("c1");

    panel.setMode("raw");

    const rawEditor = panel.element.querySelector<HTMLElement>(".cm-editor")!;
    expect(rawEditor.textContent).toContain("title: Opening 1");
    expect(rawEditor.textContent).toContain('<span data-par-id="p-1">');
  });
});