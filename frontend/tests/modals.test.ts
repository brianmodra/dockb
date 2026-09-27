import { afterEach, describe, expect, it } from "vitest";
import { confirmModal, editDocumentModal, openModal, promptModal } from "../src/renderer/layout/modals";

afterEach(() => {
  document.body.replaceChildren();
});

function modal(): HTMLElement | null {
  return document.querySelector("[data-testid='modal']");
}

describe("modals", () => {
  it("openModal resolves with the clicked button's value", async () => {
    const promise = openModal({
      title: "Go?",
      body: "Are you sure?",
      buttons: [
        { label: "Cancel", value: "cancel" },
        { label: "Delete", value: "delete", primary: true },
      ],
    });

    const el = modal()!;
    expect(el.querySelector<HTMLElement>("[data-testid='modal-title']")!.textContent).toBe("Go?");
    expect(el.querySelector<HTMLElement>("[data-testid='modal-body']")!.textContent).toBe("Are you sure?");
    const labels = Array.from(el.querySelectorAll("[data-testid='modal-button']")).map(
      (n) => (n as HTMLElement).textContent,
    );
    expect(labels).toEqual(["Cancel", "Delete"]);

    el.querySelectorAll("[data-testid='modal-button']")[1].dispatchEvent(new MouseEvent("click", { bubbles: true }));
    expect(await promise).toBe("delete");
    expect(modal()).toBeNull();
  });

  it("confirmModal resolves true on confirm and removes the modal", async () => {
    const promise = confirmModal({ title: "Delete?", message: "Really delete?", confirmLabel: "Delete" });
    const buttons = modal()!.querySelectorAll("[data-testid='modal-button']");
    buttons[1].dispatchEvent(new MouseEvent("click", { bubbles: true }));
    expect(await promise).toBe(true);
    expect(modal()).toBeNull();
  });

  it("confirmModal resolves false on cancel", async () => {
    const promise = confirmModal({ title: "Delete?", message: "Really delete?", confirmLabel: "Delete" });
    const buttons = modal()!.querySelectorAll("[data-testid='modal-button']");
    buttons[0].dispatchEvent(new MouseEvent("click", { bubbles: true }));
    expect(await promise).toBe(false);
  });

  it("promptModal pre-fills the input and returns typed text on confirm", async () => {
    const promise = promptModal({
      title: "Rename",
      label: "New name",
      initial: "Old Title",
      confirmLabel: "Rename",
    });
    const input = modal()!.querySelector<HTMLInputElement>("[data-testid='modal-input']")!;
    expect(input.value).toBe("Old Title");
    input.value = "New Title";
    const buttons = modal()!.querySelectorAll("[data-testid='modal-button']");
    buttons[1].dispatchEvent(new MouseEvent("click", { bubbles: true }));

    const result = await promise;
    expect(result.value).toBe("confirm");
    expect(result.input).toBe("New Title");
  });

  it("promptModal returns null on cancel with the untouched input", async () => {
    const promise = promptModal({ title: "Rename", label: "New name", initial: "Old", confirmLabel: "Rename" });
    const buttons = modal()!.querySelectorAll("[data-testid='modal-button']");
    buttons[0].dispatchEvent(new MouseEvent("click", { bubbles: true }));
    const result = await promise;
    expect(result.value).toBe(null);
    expect(result.input).toBe("Old");
  });

  it("editDocumentModal pre-fills title and author and saves the new values", async () => {
    const promise = editDocumentModal({ title: "Faith", author: "Paul" });
    const titleInput = modal()!.querySelector<HTMLInputElement>("[data-testid='modal-input-title']")!;
    const authorInput = modal()!.querySelector<HTMLInputElement>("[data-testid='modal-input-author']")!;
    expect(titleInput.value).toBe("Faith");
    expect(authorInput.value).toBe("Paul");
    titleInput.value = "Hope";
    authorInput.value = "Brian";
    const buttons = modal()!.querySelectorAll("[data-testid='modal-button']");
    buttons[1].dispatchEvent(new MouseEvent("click", { bubbles: true }));

    expect(await promise).toEqual({ title: "Hope", author: "Brian" });
    expect(modal()).toBeNull();
  });

  it("editDocumentModal keeps Save disabled while the title is blank", async () => {
    void editDocumentModal({ title: "Faith", author: "Paul" });
    const titleInput = modal()!.querySelector<HTMLInputElement>("[data-testid='modal-input-title']")!;
    const save = modal()!.querySelectorAll<HTMLButtonElement>("[data-testid='modal-button']")[1];
    expect(save.disabled).toBe(false);
    titleInput.value = "";
    titleInput.dispatchEvent(new Event("input", { bubbles: true }));
    expect(save.disabled).toBe(true);
  });

  it("editDocumentModal resolves null on cancel", async () => {
    const promise = editDocumentModal({ title: "Faith", author: "Paul" });
    const buttons = modal()!.querySelectorAll("[data-testid='modal-button']");
    buttons[0].dispatchEvent(new MouseEvent("click", { bubbles: true }));
    expect(await promise).toBeNull();
  });
});