import { afterEach, describe, expect, it, vi } from "vitest";
import type { DocumentContentResponse } from "../src/renderer/api/types";
import { RightPanel, type RightPanelApi } from "../src/renderer/layout/rightPanel";

function fakeApi(overrides: Partial<RightPanelApi> = {}): RightPanelApi {
  return {
    getChapterDocument: vi.fn(async (): Promise<DocumentContentResponse> => ({
      content: "# Title\n\nBody",
      summary: null,
    })),
    ...overrides,
  };
}

function panel(options: { api?: RightPanelApi; onMessage?: (text: string) => void } = {}): {
  panel: RightPanel;
  api: RightPanelApi;
  onMessage: ReturnType<typeof vi.fn>;
} {
  const api = options.api ?? fakeApi();
  const onMessage = vi.fn();
  const instance = new RightPanel({ api, onMessage: options.onMessage ?? onMessage });
  document.body.append(instance.element);
  return { panel: instance, api, onMessage };
}

function tabLabels(instance: RightPanel): string[] {
  return Array.from(instance.element.querySelectorAll('[data-testid="right-tab"]')).map(
    (node) => node.textContent?.replace("×", "").trim() ?? "",
  );
}

afterEach(() => {
  document.body.replaceChildren();
  vi.restoreAllMocks();
});

describe("RightPanel tabs", () => {
  it("truncates a long writer title to nine characters plus ellipsis", () => {
    const { panel: instance } = panel();
    instance.addWriterChapter("c1", "A very long chapter title");
    expect(tabLabels(instance)).toEqual(["A very lo…"]);
  });

  it("shows a short title whole", () => {
    const { panel: instance } = panel();
    instance.addWriterChapter("c1", "Intro");
    expect(tabLabels(instance)).toEqual(["Intro"]);
  });

  it("gives writer tabs a close button but not character tabs", () => {
    const { panel: instance } = panel();
    instance.addWriterChapter("c1", "Intro");
    instance.setCharacterChapters([{ chapterId: "k1", title: "Karakas" }]);

    const tabs = Array.from(instance.element.querySelectorAll('[data-testid="right-tab"]'));
    expect(tabs).toHaveLength(2);
    expect(tabs[0].querySelector('[data-testid="right-tab-close"]')).not.toBeNull();
    expect(tabs[1].querySelector('[data-testid="right-tab-close"]')).toBeNull();
  });

  it("orders writer tabs before character tabs", () => {
    const { panel: instance } = panel();
    instance.setCharacterChapters([{ chapterId: "k1", title: "Karakas" }]);
    instance.addWriterChapter("c1", "Intro");
    expect(tabLabels(instance)).toEqual(["Intro", "Karakas"]);
  });

  it("replaces the automatic character tabs", () => {
    const { panel: instance } = panel();
    instance.setCharacterChapters([{ chapterId: "k1", title: "Karakas" }]);
    instance.setCharacterChapters([{ chapterId: "k2", title: "Jael" }]);
    expect(tabLabels(instance)).toEqual(["Jael"]);
  });

  it("closes a writer tab and clears its content if open", async () => {
    const { panel: instance } = panel();
    instance.addWriterChapter("c1", "Intro");
    await vi.waitFor(() => {
      expect(instance.element.querySelector('[data-testid="right-content"]')?.innerHTML).toContain("<h1>");
    });

    instance.element.querySelector<HTMLButtonElement>('[data-testid="right-tab-close"]')!.click();

    expect(tabLabels(instance)).toEqual([]);
    expect(instance.element.querySelector('[data-testid="right-content"]')?.innerHTML).toBe("");
  });

  it("closes the open tab when its character tab is replaced", async () => {
    const { panel: instance } = panel();
    instance.setCharacterChapters([{ chapterId: "k1", title: "Karakas" }]);
    instance.element.querySelector<HTMLButtonElement>('[data-testid="right-tab"]')!.click();
    await vi.waitFor(() => {
      expect(instance.element.querySelector('[data-testid="right-content"]')?.innerHTML).toContain("<h1>");
    });

    instance.setCharacterChapters([{ chapterId: "k2", title: "Jael" }]);

    expect(instance.element.querySelector('[data-testid="right-content"]')?.innerHTML).toBe("");
    expect(tabLabels(instance)).toEqual(["Jael"]);
  });
});

describe("RightPanel content", () => {
  it("renders the opened chapter's markdown", async () => {
    const { panel: instance } = panel();
    instance.addWriterChapter("c1", "Intro");
    await vi.waitFor(() => {
      expect(instance.element.querySelector('[data-testid="right-content"]')?.innerHTML).toContain("<h1>Title</h1>");
    });
  });

  it("fetches the chapter read-only", async () => {
    const api = fakeApi();
    const { panel: instance } = panel({ api });
    instance.addWriterChapter("c1", "Intro");
    await vi.waitFor(() => {
      expect(api.getChapterDocument).toHaveBeenCalledWith("c1", { readonly: true });
    });
  });

  it("reports a failed load without throwing", async () => {
    const api = fakeApi({ getChapterDocument: vi.fn(async () => Promise.reject(new Error("down"))) });
    const { panel: instance, onMessage } = panel({ api });
    instance.addWriterChapter("c1", "Intro");
    await vi.waitFor(() => {
      expect(onMessage).toHaveBeenCalledWith(expect.stringContaining("down"));
    });
  });
});
