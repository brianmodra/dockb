import { afterEach, describe, expect, it, vi } from "vitest";
import type { DocumentContentResponse } from "../src/renderer/api/types";
import { EditPanel, type EditPanelApi } from "../src/renderer/layout/editPanel";

function doc(content: string, summary = null): DocumentContentResponse {
  return { content, summary };
}

function fakeApi(overrides: Partial<EditPanelApi> = {}): EditPanelApi {
  return {
    getChapterDocument: vi.fn(async (): Promise<DocumentContentResponse> => doc("")),
    saveChapterDocument: vi.fn(
      async (_id: string, content: string): Promise<DocumentContentResponse> => doc(content),
    ),
    ...overrides,
  };
}

afterEach(() => {
  document.body.replaceChildren();
  vi.restoreAllMocks();
});

describe("EditPanel", () => {
  it("loads the chapter's canonical text into the editor", async () => {
    const api = fakeApi({ getChapterDocument: vi.fn(async () => doc("# Title\n\nBody")) });
    const panel = new EditPanel({ api });
    document.body.append(panel.element);

    await panel.load("c1");

    expect(api.getChapterDocument).toHaveBeenCalledWith("c1");
    expect(panel.content()).toBe("# Title\n\nBody");
    expect(panel.lastCanonical()).toBe("# Title\n\nBody");
    expect(panel.isDirty()).toBe(false);
  });

  it("reports a new chapter load even after edits", async () => {
    const getChapterDocument = vi
      .fn(async () => doc("second"))
      .mockResolvedValueOnce(doc("first"));
    const api = fakeApi({ getChapterDocument });
    const panel = new EditPanel({ api });
    document.body.append(panel.element);

    await panel.load("c1");
    await panel.load("c1");

    expect(panel.content()).toBe("second");
    expect(panel.isDirty()).toBe(false);
  });

  it("becomes dirty after an edit and clean again once saved", async () => {
    const api = fakeApi();
    const panel = new EditPanel({ api });
    document.body.append(panel.element);
    await panel.load("c1");

    await panel.setContent(" extra");
    expect(panel.isDirty()).toBe(true);

    await panel.save();
    expect(panel.isDirty()).toBe(false);
    expect(api.saveChapterDocument).toHaveBeenCalledWith("c1", expect.stringContaining("extra"));
  });

  it("sends exactly the editor text to the backend on save", async () => {
    const saveChapterDocument = vi.fn(async (_id: string, c: string) => doc(c));
    const api = fakeApi({ saveChapterDocument });
    const panel = new EditPanel({ api });
    document.body.append(panel.element);
    await panel.load("c1");
    await panel.setContent("more words");

    await panel.save();
    expect(saveChapterDocument).toHaveBeenCalledWith("c1", "more words");
  });

  it("adopts the returned canonical text as the clean baseline (reformats the buffer)", async () => {
    const api = fakeApi({
      saveChapterDocument: vi.fn(async () => doc("canonicalized body")),
    });
    const panel = new EditPanel({ api });
    document.body.append(panel.element);
    await panel.load("c1");
    await panel.setContent("# untidy");

    await panel.save();
    expect(panel.content()).toBe("canonicalized body");
    expect(panel.lastCanonical()).toBe("canonicalized body");
    expect(panel.isDirty()).toBe(false);
  });

  it("writes a save-result message to the console on success", async () => {
    const onMessage = vi.fn();
    const summary = { created: false, changed: 2, added: 1, deleted: 0 };
    const api = fakeApi({ saveChapterDocument: vi.fn(async () => doc("c", summary)) });
    const panel = new EditPanel({ api, onMessage });
    document.body.append(panel.element);
    await panel.load("c1");
    await panel.setContent("x y z");

    await panel.save();
    expect(onMessage).toHaveBeenCalledWith(
      expect.stringMatching(/saved/i),
    );
    expect(onMessage).toHaveBeenCalledWith(expect.stringContaining("2"));
  });

  it("writes an error message to the console and stays dirty when saving fails", async () => {
    const onMessage = vi.fn();
    const api = fakeApi({
      saveChapterDocument: vi.fn(async () => {
        throw new Error("boom");
      }),
    });
    const panel = new EditPanel({ api, onMessage });
    document.body.append(panel.element);
    await panel.load("c1");
    await panel.setContent("some text here");

    const result = await panel.save();
    expect(result).toBeNull();
    expect(onMessage).toHaveBeenCalledWith(expect.stringContaining("boom"));
    expect(panel.isDirty()).toBe(true);
  });

  it("routes load failures into the message panel", async () => {
    const onMessage = vi.fn();
    const api = fakeApi({
      getChapterDocument: vi.fn(async () => {
        throw new Error("chapter missing");
      }),
    });
    const panel = new EditPanel({ api, onMessage });
    document.body.append(panel.element);

    await panel.load("c1");
    expect(onMessage).toHaveBeenCalledWith(expect.stringContaining("chapter missing"));
    expect(panel.isDirty()).toBe(false);
  });

  it("still allows a save when the buffer is unchanged", async () => {
    const saveChapterDocument = vi.fn(async (_id: string, c: string) => doc(c));
    const api = fakeApi({ saveChapterDocument });
    const panel = new EditPanel({ api });
    document.body.append(panel.element);
    await panel.load("c1");

    await panel.save();
    expect(saveChapterDocument).toHaveBeenCalledTimes(1);
  });
});