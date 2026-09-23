import { openDocumentPicker, type DocumentPickerApi } from "../src/renderer/layout/documentPicker";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { DocumentWire } from "../src/renderer/api/types";

function doc(id: string, title: string): DocumentWire {
  return { attrs: { id, title, author: "A" }, chapter_summaries: [] };
}

function fakeApi(overrides: Partial<DocumentPickerApi> = {}): DocumentPickerApi {
  return {
    listDocuments: vi.fn(async (): Promise<DocumentWire[]> => []),
    ...overrides,
  };
}

afterEach(() => {
  document.body.replaceChildren();
  vi.restoreAllMocks();
});

function modal(): HTMLElement | null {
  return document.querySelector("[data-testid='modal']");
}

async function flush(): Promise<void> {
  await new Promise((r) => setTimeout(r, 0));
}

describe("openDocumentPicker", () => {
  it("lists the documents and resolves with the picked id", async () => {
    const api = fakeApi({ listDocuments: vi.fn(async () => [doc("d1", "Faith"), doc("d2", "Sight")]) });
    const promise = openDocumentPicker(api);
    await flush();
    const items = modal()!.querySelectorAll("[data-testid='document-picker-item']");
    expect(items).toHaveLength(2);
    expect(items[0].textContent).toContain("Faith");
    expect(items[1].textContent).toContain("Sight");

    items[1].dispatchEvent(new MouseEvent("click", { bubbles: true }));
    expect(await promise).toBe("d2");
    expect(modal()).toBeNull();
  });

  it("resolves null when the user cancels", async () => {
    const api = fakeApi({ listDocuments: vi.fn(async () => [doc("d1", "Faith")]) });
    const promise = openDocumentPicker(api);
    await flush();
    const cancel = modal()!.querySelector<HTMLElement>("[data-testid='document-picker-cancel']")!;
    cancel.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    expect(await promise).toBeNull();
  });

  it("reports a load failure into the message panel and resolves null", async () => {
    const onMessage = vi.fn();
    const api = fakeApi({
      listDocuments: vi.fn(async () => {
        throw new Error("backend down");
      }),
    });
    const result = await openDocumentPicker(api, { onMessage });
    expect(result).toBeNull();
    expect(onMessage).toHaveBeenCalledWith(expect.stringContaining("backend down"));
    expect(modal()).toBeNull();
  });

  it("shows an empty-state row and resolves null when there are no documents", async () => {
    const promise = openDocumentPicker(fakeApi());
    await flush();
    const empty = modal()!.querySelector("[data-testid='document-picker-empty']");
    expect(empty).not.toBeNull();
    const cancel = modal()!.querySelector<HTMLElement>("[data-testid='document-picker-cancel']")!;
    cancel.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    expect(await promise).toBeNull();
  });
});