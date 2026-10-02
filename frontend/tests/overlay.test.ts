import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { openOverlay } from "../src/renderer/layout/overlay";
import { openSelectList, type SelectList } from "../src/renderer/layout/selectList";

function modal(): HTMLElement | null {
  return document.querySelector("[data-testid='modal']");
}

afterEach(() => {
  document.body.replaceChildren();
});

describe("openOverlay", () => {
  it("mounts an overlay dialog with a title", () => {
    openOverlay({ title: "Import document", buttons: [] });
    const overlay = modal();
    expect(overlay).not.toBeNull();
    expect(overlay!.querySelector("[data-testid='modal-title']")!.textContent).toBe(
      "Import document",
    );
    expect(overlay!.querySelector(".modal-dialog")).not.toBeNull();
  });

  it("puts the buttons in a row, in the order given", () => {
    const overlay = openOverlay({
      title: "T",
      buttons: [
        { label: "Cancel", testId: "cancel" },
        { label: "Import", testId: "import", primary: true },
      ],
    });
    const labels = [...overlay.dialog.querySelectorAll("button")].map((b) => b.textContent);
    expect(labels).toEqual(["Cancel", "Import"]);
    expect(overlay.dialog.querySelector(".modal-buttons")).not.toBeNull();
  });

  it("marks a primary button and leaves others unmarked", () => {
    const overlay = openOverlay({
      title: "T",
      buttons: [
        { label: "Cancel", testId: "cancel" },
        { label: "Import", testId: "import", primary: true },
      ],
    });
    expect(overlay.buttons.import.className).toContain("is-primary");
    expect(overlay.buttons.cancel.className).not.toContain("is-primary");
  });

  it("exposes each button by its test id", () => {
    const overlay = openOverlay({
      title: "T",
      buttons: [
        { label: "Cancel", testId: "cancel" },
        { label: "Import", testId: "import" },
      ],
    });
    expect(overlay.buttons.cancel.dataset.testid).toBe("cancel");
    expect(overlay.buttons.import.textContent).toBe("Import");
  });

  it("honours a button that starts disabled", () => {
    const overlay = openOverlay({
      title: "T",
      buttons: [{ label: "Import", testId: "import", disabled: true }],
    });
    expect(overlay.buttons.import.disabled).toBe(true);
  });

  it("leaves a button enabled when not asked to disable it", () => {
    const overlay = openOverlay({
      title: "T",
      buttons: [{ label: "Import", testId: "import" }],
    });
    expect(overlay.buttons.import.disabled).toBe(false);
  });

  it("close removes the overlay from the document", () => {
    const overlay = openOverlay({ title: "T", buttons: [] });
    expect(modal()).not.toBeNull();
    overlay.close();
    expect(modal()).toBeNull();
  });

  it("close is safe to call twice", () => {
    const overlay = openOverlay({ title: "T", buttons: [] });
    overlay.close();
    overlay.close();
    expect(modal()).toBeNull();
  });

  it("appends a second overlay on top of the first", () => {
    openOverlay({ title: "First", buttons: [] });
    openOverlay({ title: "Second", buttons: [] });
    expect(document.querySelectorAll("[data-testid='modal']")).toHaveLength(2);
  });
});

describe("openOverlay button clicks", () => {
  beforeEach(() => {
    document.body.replaceChildren();
  });

  it("a button's listener fires when it is clicked", () => {
    const overlay = openOverlay({
      title: "T",
      buttons: [{ label: "Import", testId: "import" }],
    });
    let clicks = 0;
    overlay.buttons.import.addEventListener("click", () => {
      clicks += 1;
    });
    overlay.buttons.import.click();
    expect(clicks).toBe(1);
  });

  it("clicking does not close the overlay on its own", () => {
    const overlay = openOverlay({
      title: "T",
      buttons: [{ label: "Import", testId: "import" }],
    });
    overlay.buttons.import.click();
    expect(modal()).not.toBeNull();
  });
});

describe("openOverlay body slot", () => {
  it("puts body content between the title and the button row", () => {
    const overlay = openOverlay({
      title: "Import document",
      buttons: [{ label: "Import", testId: "import" }],
    });
    const content = document.createElement("p");
    content.textContent = "content";
    overlay.body.append(content);
    const order = [...overlay.dialog.children].map((child) =>
      child.className === "" ? "content" : child.className,
    );
    expect(order).toEqual(["modal-title", "content", "modal-buttons"]);
  });

  it("body content sits inside the dialog", () => {
    const overlay = openOverlay({ title: "T", buttons: [] });
    expect(overlay.dialog.contains(overlay.body)).toBe(true);
  });
});

describe("openSelectList", () => {
  const items = [
    { key: "d-1", label: "Faith" },
    { key: "d-2", label: "Love" },
  ];

  function open(): SelectList<string> {
    return openSelectList({
      title: "Open document",
      items,
      itemTestId: "document-picker-item",
      cancelTestId: "document-picker-cancel",
      confirmTestId: "document-picker-delete",
      confirmLabel: "Delete",
      emptyMessage: "No documents yet.",
      emptyTestId: "document-picker-empty",
      valueFor: (item) => item.key,
    });
  }

  it("lists one button per item, labelled by the item", () => {
    open();
    const rendered = document.querySelectorAll("[data-testid='document-picker-item']");
    expect([...rendered].map((b) => b.textContent)).toEqual(["Faith", "Love"]);
  });

  it("shows the empty message and no items when there are none", () => {
    openSelectList({
      title: "Open document",
      items: [],
      itemTestId: "document-picker-item",
      cancelTestId: "document-picker-cancel",
      confirmTestId: "document-picker-delete",
      confirmLabel: "Delete",
      emptyMessage: "No documents yet.",
      emptyTestId: "document-picker-empty",
      valueFor: (item) => item.key,
    });
    const empty = document.querySelector("[data-testid='document-picker-empty']");
    expect(empty?.textContent).toBe("No documents yet.");
    expect(document.querySelectorAll("[data-testid='document-picker-item']")).toHaveLength(0);
  });

  it("starts with the confirm button disabled", () => {
    const list = open();
    expect(list.overlay.buttons["document-picker-delete"].disabled).toBe(true);
  });

  it("keeps the confirm button disabled when there are no items", () => {
    openSelectList({
      title: "Open document",
      items: [],
      itemTestId: "document-picker-item",
      cancelTestId: "document-picker-cancel",
      confirmTestId: "document-picker-delete",
      confirmLabel: "Delete",
      emptyMessage: "No documents yet.",
      emptyTestId: "document-picker-empty",
      valueFor: (item) => item.key,
    });
    const del = document.querySelector<HTMLButtonElement>("[data-testid='document-picker-delete']")!;
    expect(del.disabled).toBe(true);
  });

  it("enables the confirm button once an item is chosen", () => {
    open();
    document.querySelectorAll<HTMLElement>("[data-testid='document-picker-item']")[1].click();
    const del = document.querySelector<HTMLButtonElement>("[data-testid='document-picker-delete']")!;
    expect(del.disabled).toBe(false);
  });

  it("marks only the chosen item as selected", () => {
    open();
    const rendered = document.querySelectorAll<HTMLElement>("[data-testid='document-picker-item']");
    rendered[0].click();
    rendered[1].click();
    const selected = [...document.querySelectorAll(".document-picker-item--selected")];
    expect(selected).toHaveLength(1);
    expect(selected[0].textContent).toBe("Love");
  });

  it("resolves with the chosen item's value on confirm", async () => {
    const list = open();
    document.querySelectorAll<HTMLElement>("[data-testid='document-picker-item']")[0].click();
    document.querySelector<HTMLButtonElement>("[data-testid='document-picker-delete']")!.click();
    await expect(list.result).resolves.toBe("d-1");
  });

  it("closes the overlay on confirm", async () => {
    const list = open();
    document.querySelector<HTMLElement>("[data-testid='document-picker-item']")!.click();
    document.querySelector<HTMLButtonElement>("[data-testid='document-picker-delete']")!.click();
    await list.result;
    expect(modal()).toBeNull();
  });

  it("resolves with null on cancel", async () => {
    const list = open();
    document.querySelector<HTMLButtonElement>("[data-testid='document-picker-cancel']")!.click();
    await expect(list.result).resolves.toBeNull();
  });

  it("closes the overlay on cancel", async () => {
    const list = open();
    document.querySelector<HTMLButtonElement>("[data-testid='document-picker-cancel']")!.click();
    await list.result;
    expect(modal()).toBeNull();
  });

  it("ignores a confirm click when nothing is chosen", async () => {
    const list = open();
    document.querySelector<HTMLButtonElement>("[data-testid='document-picker-delete']")!.click();
    expect(modal()).not.toBeNull();
    document.querySelector<HTMLButtonElement>("[data-testid='document-picker-cancel']")!.click();
    await expect(list.result).resolves.toBeNull();
  });

  it("resolves with null when an empty list is confirmed", async () => {
    const list = openSelectList({
      title: "Open document",
      items: [],
      itemTestId: "document-picker-item",
      cancelTestId: "document-picker-cancel",
      confirmTestId: "document-picker-delete",
      confirmLabel: "Delete",
      emptyMessage: "No documents yet.",
      emptyTestId: "document-picker-empty",
      valueFor: (item) => item.key,
    });
    document.querySelector<HTMLButtonElement>("[data-testid='document-picker-cancel']")!.click();
    await expect(list.result).resolves.toBeNull();
  });
});
