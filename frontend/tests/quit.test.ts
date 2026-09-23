import { afterEach, describe, expect, it, vi } from "vitest";
import { quitApp } from "../src/renderer/state/quit";

function modalButtons(): HTMLElement[] {
  return Array.from(document.querySelectorAll("[data-testid='modal-button']"));
}

function clickButton(index: number): void {
  modalButtons()[index].dispatchEvent(new MouseEvent("click", { bubbles: true }));
}

afterEach(() => {
  document.body.replaceChildren();
  vi.restoreAllMocks();
});

describe("quitApp", () => {
  it("quits immediately when there are no unsaved changes", async () => {
    const onQuit = vi.fn();
    const result = await quitApp({
      isDirty: () => false,
      onQuit,
    });
    expect(result).toBe(true);
    expect(onQuit).toHaveBeenCalledTimes(1);
    expect(document.querySelector("[data-testid='modal']")).toBeNull();
  });

  it("shows the save-first modal when there are unsaved changes", async () => {
    quitApp({ isDirty: () => true, onQuit: vi.fn() });
    const title = document.querySelector("[data-testid='modal-title']");
    expect(title?.textContent).toBe("Save chapter first?");
    expect(modalButtons().map((b) => b.textContent)).toEqual(["Cancel", "Discard", "Save and Quit"]);
    expect(document.querySelector("[data-testid='modal']")).not.toBeNull();
  });

  it("discards changes and quits when Discard is chosen", async () => {
    const onQuit = vi.fn();
    const promise = quitApp({ isDirty: () => true, onQuit });
    clickButton(1);
    expect(await promise).toBe(true);
    expect(onQuit).toHaveBeenCalledTimes(1);
  });

  it("does not quit when Cancel is chosen", async () => {
    const onQuit = vi.fn();
    const promise = quitApp({ isDirty: () => true, onQuit });
    clickButton(0);
    expect(await promise).toBe(false);
    expect(onQuit).not.toHaveBeenCalled();
  });

  it("saves then quits when Save and Quit is chosen", async () => {
    const save = vi.fn(async () => ({ content: "x", summary: null }));
    const onQuit = vi.fn();
    const promise = quitApp({ isDirty: () => true, save, onQuit });
    clickButton(2);
    expect(await promise).toBe(true);
    expect(save).toHaveBeenCalledTimes(1);
    expect(onQuit).toHaveBeenCalledTimes(1);
  });

  it("does not quit if the save fails", async () => {
    const save = vi.fn(async () => null);
    const onQuit = vi.fn();
    const promise = quitApp({ isDirty: () => true, save, onQuit });
    clickButton(2);
    expect(await promise).toBe(false);
    expect(onQuit).not.toHaveBeenCalled();
  });
});