import { afterEach, describe, expect, it, vi } from "vitest";
import { FILE_CACHE_MESSAGE, openFileCacheModal } from "../src/renderer/layout/fileCacheModal";
import type { FileCache } from "../src/renderer/state/fileCache";

function cacheFor(directory: string | null = "/cache"): FileCache {
  return { chooseDirectory: vi.fn(async () => directory) } as unknown as FileCache;
}

function button(testId: string): HTMLButtonElement {
  return document.querySelector<HTMLButtonElement>(`[data-testid="${testId}"]`)!;
}

function click(testId: string): void {
  button(testId).dispatchEvent(new MouseEvent("click", { bubbles: true }));
}

afterEach(() => {
  document.body.replaceChildren();
});

describe("file cache modal", () => {
  it("shows the exact cache explanation and native chooser button at startup", () => {
    void openFileCacheModal(cacheFor());
    const messages = Array.from(document.querySelectorAll('[data-testid="file-cache-message"]')).map(
      (node) => node.textContent,
    );
    expect(messages).toEqual(FILE_CACHE_MESSAGE.split("\n"));
    expect(button("file-cache-choose-button").textContent).toBe("Choose the file cache directory");
    expect(document.querySelector('[data-testid="file-cache-cancel-button"]')).toBeNull();
  });

  it("offers Cancel when opened from the cog", async () => {
    const pending = openFileCacheModal(cacheFor(), { allowCancel: true });
    expect(button("file-cache-cancel-button")).not.toBeNull();
    click("file-cache-cancel-button");
    await expect(pending).resolves.toBeNull();
    expect(document.querySelector('[data-testid="modal"]')).toBeNull();
  });

  it("chooses a directory, resolves it and closes the modal", async () => {
    const cache = cacheFor("/picked/cache");
    const pending = openFileCacheModal(cache);
    click("file-cache-choose-button");
    await expect(pending).resolves.toBe("/picked/cache");
    expect(cache.chooseDirectory).toHaveBeenCalledTimes(1);
    expect(document.querySelector('[data-testid="modal"]')).toBeNull();
  });

  it("keeps the modal open when the native chooser is cancelled", async () => {
    const cache = cacheFor(null);
    const pending = openFileCacheModal(cache, { allowCancel: true });
    click("file-cache-choose-button");
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(document.querySelector('[data-testid="modal"]')).not.toBeNull();
    expect(button("file-cache-choose-button").disabled).toBe(false);
    click("file-cache-cancel-button");
    await expect(pending).resolves.toBeNull();
  });
});
