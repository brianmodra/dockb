import { afterEach, describe, expect, it, vi } from "vitest";

import type { DockbBridge } from "../src/renderer/api/bridge";
import type { ImportSummaryWire } from "../src/renderer/api/types";
import {
  confirmImport,
  deriveDirectoryName,
  openImportDialog,
  showImportSummaries,
} from "../src/renderer/layout/importDialog";

function picked(relativePath: string, contents = "text"): File {
  const file = new File([contents], relativePath.split("/").pop() ?? "file.md", {
    type: "text/markdown",
  });
  Object.defineProperty(file, "webkitRelativePath", { value: relativePath });
  return file;
}

function bridgeFor(paths: Map<File, string>): DockbBridge {
  return {
    platform: "linux",
    openExternal: vi.fn(async () => undefined),
    quit: vi.fn(),
    getPathForFile: (file: File) => paths.get(file) ?? "",
  };
}

function modal(): HTMLElement | null {
  return document.querySelector("[data-testid='modal']");
}

function byId<T extends HTMLElement>(id: string): T {
  const el = document.querySelector<T>(`[data-testid='${id}']`);
  if (el === null) {
    throw new Error(`no element with test id ${id}`);
  }
  return el;
}

/** Drive the hidden directory input the dialog puts on the page. */
function handPick(input: HTMLInputElement, files: File[] | null): void {
  Object.defineProperty(input, "files", {
    configurable: true,
    value: files === null ? null : { length: files.length, item: (i: number) => files[i], [Symbol.iterator]: () => files[Symbol.iterator]() },
  });
  input.dispatchEvent(new Event(files === null ? "cancel" : "change"));
}

async function waitFor(testid: string): Promise<HTMLElement> {
  for (let i = 0; i < 20 && document.querySelector(`[data-testid='${testid}']`) === null; i += 1) {
    await new Promise((resolve) => setTimeout(resolve, 0));
  }
  return byId(testid);
}

function waitForInput(): Promise<HTMLInputElement> {
  return waitFor("import-directory-input") as Promise<HTMLInputElement>;
}

function waitForDialog(): Promise<HTMLElement> {
  return waitFor("import-dialog-cancel");
}

afterEach(() => {
  document.body.replaceChildren();
  vi.restoreAllMocks();
});

describe("deriveDirectoryName", () => {
  it("recovers the picked directory's name from a nested file", () => {
    const file = picked("Act I/Opening 1.md");
    const name = deriveDirectoryName([file], () => "/home/x/Linchpin/Act I/Opening 1.md");
    expect(name).toBe("Linchpin");
  });

  it("recovers the name for a file at the picked directory's root", () => {
    const file = picked("document_metadata.yaml");
    const name = deriveDirectoryName([file], () => "/home/x/Linchpin/document_metadata.yaml");
    expect(name).toBe("Linchpin");
  });

  it("recovers the name for a deeply nested file", () => {
    const file = picked("Act I/Scene 2/Opening 1.md");
    const name = deriveDirectoryName([file], () => "/home/x/Linchpin/Act I/Scene 2/Opening 1.md");
    expect(name).toBe("Linchpin");
  });

  it("handles a Windows path, whose separators differ from the relative path's", () => {
    const file = picked("Act I/Opening 1.md");
    const name = deriveDirectoryName([file], () => "C:\\docs\\Linchpin\\Act I\\Opening 1.md");
    expect(name).toBe("Linchpin");
  });

  it("refuses when the bridge is absent", () => {
    const file = picked("Act I/Opening 1.md");
    expect(() => deriveDirectoryName([file], undefined)).toThrow(/Electron/);
  });

  it("refuses when the bridge returns an empty path", () => {
    const file = picked("Act I/Opening 1.md");
    expect(() => deriveDirectoryName([file], () => "")).toThrow(/path/);
  });

  it("refuses when there are no files", () => {
    expect(() => deriveDirectoryName([], () => "/home/x/Linchpin/a.md")).toThrow(/at least one file/i);
  });

  it("refuses a file with no relative path", () => {
    const file = new File(["x"], "stray.md");
    expect(() => deriveDirectoryName([file], () => "/home/x/Linchpin/stray.md")).toThrow(/relative path/);
  });

  it("refuses when the path does not end with the relative path", () => {
    const file = picked("Act I/Opening 1.md");
    expect(() => deriveDirectoryName([file], () => "/home/x/Other/Opening 1.md")).toThrow(/does not match/);
  });
});

describe("confirmImport", () => {
  const files = [picked("Act I/Opening 1.md", "a"), picked("Act I/Opening 2.md", "bb")];

  it("names the document, and counts the files and their bytes", async () => {
    const pending = confirmImport("Linchpin", files);
    expect(byId("import-dialog-name").textContent).toContain("Linchpin");
    expect(byId("import-dialog-count").textContent).toContain("2 files");
    expect(byId("import-dialog-size").textContent).toContain("3 bytes");
    byId<HTMLButtonElement>("import-dialog-cancel").click();
    await expect(pending).resolves.toBeNull();
  });

  it("says 1 file, not 1 files", async () => {
    const pending = confirmImport("Linchpin", [files[0]]);
    expect(byId("import-dialog-count").textContent).toContain("1 file");
    expect(byId("import-dialog-count").textContent).not.toContain("1 files");
    byId<HTMLButtonElement>("import-dialog-cancel").click();
    await pending;
  });

  it("offers the paragraphs checkbox, off by default", async () => {
    const pending = confirmImport("Linchpin", files);
    expect(byId<HTMLInputElement>("import-dialog-paragraphs").checked).toBe(false);
    byId<HTMLButtonElement>("import-dialog-cancel").click();
    await pending;
  });

  it("resolves with the files and the unticked checkbox", async () => {
    const pending = confirmImport("Linchpin", files);
    byId<HTMLButtonElement>("import-dialog-confirm").click();
    const selection = await pending;
    expect(selection).not.toBeNull();
    expect(selection!.directoryName).toBe("Linchpin");
    expect(selection!.files).toHaveLength(2);
    expect(selection!.singleNewlineParagraphs).toBe(false);
  });

  it("resolves with the checkbox ticked", async () => {
    const pending = confirmImport("Linchpin", files);
    const box = byId<HTMLInputElement>("import-dialog-paragraphs");
    box.checked = true;
    byId<HTMLButtonElement>("import-dialog-confirm").click();
    const selection = await pending;
    expect(selection!.singleNewlineParagraphs).toBe(true);
  });

  it("closes the dialog on confirm", async () => {
    const pending = confirmImport("Linchpin", files);
    byId<HTMLButtonElement>("import-dialog-confirm").click();
    await pending;
    expect(modal()).toBeNull();
  });

  it("closes the dialog on cancel", async () => {
    const pending = confirmImport("Linchpin", files);
    byId<HTMLButtonElement>("import-dialog-cancel").click();
    await pending;
    expect(modal()).toBeNull();
  });
});

describe("showImportSummaries", () => {
  const summaries: ImportSummaryWire[] = [
    { chapter_id: "c-1", title: "Opening 1", category: "Chapter", created: true, changed: 3, added: 1, deleted: 0 },
    { chapter_id: "c-2", title: "Dramatis Personae", category: "Character", created: true, changed: 0, added: 5, deleted: 0 },
  ];

  it("renders one row per chapter, with its title and category", () => {
    showImportSummaries(summaries);
    const rows = document.querySelectorAll("[data-testid='import-summary-row']");
    expect(rows).toHaveLength(2);
    expect(rows[0].textContent).toContain("Opening 1");
    expect(rows[0].textContent).toContain("Chapter");
    expect(rows[1].textContent).toContain("Character");
  });

  it("says how many chapters were added", () => {
    showImportSummaries(summaries);
    const body = byId("import-summary-body").textContent ?? "";
    expect(body).toContain("2 chapters");
  });

  it("shows the counts for each chapter", () => {
    showImportSummaries(summaries);
    const row = byId("import-summary-row").textContent ?? "";
    expect(row).toContain("3");
    expect(row).toContain("1");
  });

  it("distinguishes a created chapter from an updated one", () => {
    showImportSummaries([
      { chapter_id: "c-1", title: "New", category: "Chapter", created: true, changed: 0, added: 1, deleted: 0 },
      { chapter_id: "c-2", title: "Old", category: "Chapter", created: false, changed: 2, added: 0, deleted: 0 },
    ]);
    const rows = [...document.querySelectorAll("[data-testid='import-summary-row']")];
    expect(rows[0].textContent).toContain("new");
    expect(rows[1].textContent).toContain("updated");
  });

  it("closes on the done button", () => {
    showImportSummaries(summaries);
    byId<HTMLButtonElement>("import-summary-close").click();
    expect(modal()).toBeNull();
  });

  it("says so when the document had no chapters", () => {
    showImportSummaries([]);
    expect(byId("import-summary-body").textContent).toContain("No chapters");
  });
});

describe("openImportDialog", () => {
  const file = picked("Act I/Opening 1.md");

  it("shows a directory input marked as a directory picker", async () => {
    const bridge = bridgeFor(new Map([[file, "/home/x/Linchpin/Act I/Opening 1.md"]]));
    const pending = openImportDialog(bridge);
    const input = await waitForInput();
    expect(input.type).toBe("file");
    expect(input.getAttribute("webkitdirectory")).toBe("");
    handPick(input, [file]);
    await waitForDialog();
    byId<HTMLButtonElement>("import-dialog-cancel").click();
    await pending;
  });

  it("resolves with the picked files and the derived directory name", async () => {
    const bridge = bridgeFor(new Map([[file, "/home/x/Linchpin/Act I/Opening 1.md"]]));
    const pending = openImportDialog(bridge);
    handPick(await waitForInput(), [file]);
    await waitForDialog();
    byId<HTMLButtonElement>("import-dialog-confirm").click();
    const selection = await pending;
    expect(selection!.directoryName).toBe("Linchpin");
    expect(selection!.files).toHaveLength(1);
  });

  it("resolves with null when the native dialog is cancelled", async () => {
    const pending = openImportDialog(bridgeFor(new Map()));
    handPick(await waitForInput(), null);
    await expect(pending).resolves.toBeNull();
  });

  it("resolves with null when the picker reports an empty selection", async () => {
    const pending = openImportDialog(bridgeFor(new Map()));
    handPick(await waitForInput(), []);
    await expect(pending).resolves.toBeNull();
  });

  it("leaves no modal open after the native dialog is cancelled", async () => {
    const pending = openImportDialog(bridgeFor(new Map()));
    handPick(await waitForInput(), null);
    await pending;
    expect(modal()).toBeNull();
  });

  it("reports an error rather than uploading when the bridge is absent", async () => {
    const onMessage = vi.fn();
    const pending = openImportDialog(undefined, { onMessage });
    handPick(await waitForInput(), [file]);
    await pending;
    expect(onMessage).toHaveBeenCalled();
    expect(String(onMessage.mock.calls[0][0])).toMatch(/Electron/);
    expect(modal()).toBeNull();
  });

  it("reports an error when the picked path cannot be read", async () => {
    const onMessage = vi.fn();
    const pending = openImportDialog(bridgeFor(new Map()), { onMessage });
    handPick(await waitForInput(), [file]);
    await pending;
    expect(onMessage).toHaveBeenCalled();
    expect(modal()).toBeNull();
  });

  it("removes the directory input once the native dialog is done", async () => {
    const bridge = bridgeFor(new Map([[file, "/home/x/Linchpin/Act I/Opening 1.md"]]));
    const pending = openImportDialog(bridge);
    handPick(await waitForInput(), [file]);
    await waitForDialog();
    expect(document.querySelector("[data-testid='import-directory-input']")).toBeNull();
    byId<HTMLButtonElement>("import-dialog-cancel").click();
    await pending;
  });
});

describe("summary rows are not buttons", () => {
  it("renders each row as a div, so it does not look clickable", () => {
    showImportSummaries([
      { chapter_id: "c-1", title: "Opening 1", category: "Chapter", created: true, changed: 1, added: 0, deleted: 0 },
    ]);
    const row = byId("import-summary-row");
    expect(row.tagName).toBe("DIV");
    expect(row.className).toBe("import-summary-row");
    expect(row.className).not.toContain("document-picker-item");
  });
});

describe("import text is never treated as markup", () => {
  it("shows a directory name containing markup as literal text", async () => {
    const file = picked("Act I/Opening 1.md");
    const hostile = "<img src=x onerror=alert(1)>";
    const pending = confirmImport(hostile, [file]);
    const name = byId("import-dialog-name");
    expect(name.textContent).toBe(`Document: ${hostile}`);
    expect(name.querySelector("img")).toBeNull();
    byId<HTMLButtonElement>("import-dialog-cancel").click();
    await pending;
  });

  it("shows a chapter title containing markup as literal text", () => {
    showImportSummaries([
      {
        chapter_id: "c-1",
        title: "<script>alert(1)</script>",
        category: "Chapter",
        created: true,
        changed: 0,
        added: 1,
        deleted: 0,
      },
    ]);
    const row = byId("import-summary-row");
    expect(row.textContent).toContain("<script>alert(1)</script>");
    expect(row.querySelector("script")).toBeNull();
  });
});
