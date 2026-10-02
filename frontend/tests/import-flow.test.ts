import { afterEach, describe, expect, it, vi } from "vitest";

import type { ApiClient } from "../src/renderer/api/client";
import type { DockbBridge } from "../src/renderer/api/bridge";
import { mountShell } from "../src/renderer/main";

function picked(relativePath: string): File {
  const file = new File(["text"], relativePath.split("/").pop() ?? "file.md", {
    type: "text/markdown",
  });
  Object.defineProperty(file, "webkitRelativePath", { value: relativePath });
  return file;
}

function bridgeFor(file: File, absolute: string): DockbBridge {
  return {
    platform: "linux",
    openExternal: vi.fn(async () => undefined),
    quit: vi.fn(),
    getPathForFile: (candidate: File) => (candidate === file ? absolute : ""),
  };
}

function apiWith(importDocument: ApiClient["importDocument"]): ApiClient {
  return {
    listDocuments: vi.fn(async () => []),
    importDocument,
  } as unknown as ApiClient;
}

const summary = {
  chapter_id: "c-1",
  title: "Opening 1",
  category: "Chapter",
  created: true,
  changed: 2,
  added: 1,
  deleted: 0,
};

async function waitFor<T extends HTMLElement>(testid: string): Promise<T> {
  for (let i = 0; i < 20 && document.querySelector(`[data-testid='${testid}']`) === null; i += 1) {
    await new Promise((resolve) => setTimeout(resolve, 0));
  }
  const el = document.querySelector<T>(`[data-testid='${testid}']`);
  if (el === null) {
    throw new Error(`no element with test id ${testid}`);
  }
  return el;
}

async function waitForText(root: HTMLElement, text: string): Promise<void> {
  for (let i = 0; i < 40 && !(root.textContent ?? "").includes(text); i += 1) {
    await new Promise((resolve) => setTimeout(resolve, 0));
  }
}

function byId<T extends HTMLElement>(testid: string): T {
  const el = document.querySelector<T>(`[data-testid='${testid}']`);
  if (el === null) {
    throw new Error(`no element with test id ${testid}`);
  }
  return el;
}

function handPick(input: HTMLInputElement, files: File[] | null): void {
  Object.defineProperty(input, "files", {
    configurable: true,
    value:
      files === null
        ? null
        : {
            length: files.length,
            item: (i: number) => files[i],
            [Symbol.iterator]: () => files[Symbol.iterator](),
          },
  });
  input.dispatchEvent(new Event(files === null ? "cancel" : "change"));
}

async function clickImportMenuItem(): Promise<void> {
  byId<HTMLElement>("menu-File").dispatchEvent(new MouseEvent("click", { bubbles: true }));
  byId<HTMLElement>("menu-item-import").dispatchEvent(new MouseEvent("click", { bubbles: true }));
  await waitFor("import-directory-input");
}

afterEach(() => {
  document.body.replaceChildren();
  vi.restoreAllMocks();
});

describe("the shell import flow", () => {
  it("sends the picked directory and then shows the summaries", async () => {
    const file = picked("Act I/Opening 1.md");
    const importDocument = vi.fn(async () => ({ imports: [summary] }));
    const root = document.createElement("div");
    document.body.append(root);
    mountShell(root, { api: apiWith(importDocument), bridge: bridgeFor(file, "/home/x/Linchpin/Act I/Opening 1.md") });

    await clickImportMenuItem();
    handPick(byId<HTMLInputElement>("import-directory-input"), [file]);
    await waitFor("import-dialog-confirm");
    byId<HTMLButtonElement>("import-dialog-confirm").click();

    await waitFor("import-summary-row");
    expect(importDocument).toHaveBeenCalledTimes(1);
    expect(importDocument.mock.calls[0][0]).toBe("Linchpin");
    expect(importDocument.mock.calls[0][1]).toHaveLength(1);
    expect(byId("import-summary-row").textContent).toContain("Opening 1");
  });

  it("passes the ticked paragraphs option through", async () => {
    const file = picked("Act I/Opening 1.md");
    const importDocument = vi.fn(async () => ({ imports: [summary] }));
    const root = document.createElement("div");
    document.body.append(root);
    mountShell(root, { api: apiWith(importDocument), bridge: bridgeFor(file, "/home/x/Linchpin/Act I/Opening 1.md") });

    await clickImportMenuItem();
    handPick(byId<HTMLInputElement>("import-directory-input"), [file]);
    await waitFor("import-dialog-confirm");
    byId<HTMLInputElement>("import-dialog-paragraphs").checked = true;
    byId<HTMLButtonElement>("import-dialog-confirm").click();

    await waitFor("import-summary-row");
    expect(importDocument.mock.calls[0][2]).toEqual({ singleNewlineParagraphs: true });
  });

  it("sends nothing when the import is cancelled", async () => {
    const file = picked("Act I/Opening 1.md");
    const importDocument = vi.fn(async () => ({ imports: [] }));
    const root = document.createElement("div");
    document.body.append(root);
    mountShell(root, { api: apiWith(importDocument), bridge: bridgeFor(file, "/home/x/Linchpin/Act I/Opening 1.md") });

    await clickImportMenuItem();
    handPick(byId<HTMLInputElement>("import-directory-input"), [file]);
    await waitFor("import-dialog-confirm");
    byId<HTMLButtonElement>("import-dialog-cancel").click();
    await new Promise((resolve) => setTimeout(resolve, 5));

    expect(importDocument).not.toHaveBeenCalled();
  });

  it("sends nothing when the native dialog is cancelled", async () => {
    const importDocument = vi.fn(async () => ({ imports: [] }));
    const root = document.createElement("div");
    document.body.append(root);
    const file = picked("Act I/Opening 1.md");
    mountShell(root, { api: apiWith(importDocument), bridge: bridgeFor(file, "/home/x/Linchpin/Act I/Opening 1.md") });

    await clickImportMenuItem();
    handPick(byId<HTMLInputElement>("import-directory-input"), null);
    await new Promise((resolve) => setTimeout(resolve, 5));

    expect(importDocument).not.toHaveBeenCalled();
  });

  it("reports a failed upload instead of showing summaries", async () => {
    const file = picked("Act I/Opening 1.md");
    const importDocument = vi.fn(async () => {
      throw new Error("upload exceeds 64.0 MiB");
    });
    const root = document.createElement("div");
    document.body.append(root);
    mountShell(root, { api: apiWith(importDocument), bridge: bridgeFor(file, "/home/x/Linchpin/Act I/Opening 1.md") });

    await clickImportMenuItem();
    handPick(byId<HTMLInputElement>("import-directory-input"), [file]);
    await waitFor("import-dialog-confirm");
    byId<HTMLButtonElement>("import-dialog-confirm").click();

    await waitForText(root, "upload exceeds 64.0 MiB");
    expect(document.querySelector("[data-testid='import-summary-row']")).toBeNull();
  });

  it("reports a missing bridge rather than uploading", async () => {
    const importDocument = vi.fn(async () => ({ imports: [] }));
    const root = document.createElement("div");
    document.body.append(root);
    mountShell(root, { api: apiWith(importDocument) });

    await clickImportMenuItem();
    handPick(byId<HTMLInputElement>("import-directory-input"), [picked("Act I/Opening 1.md")]);
    await new Promise((resolve) => setTimeout(resolve, 5));

    expect(importDocument).not.toHaveBeenCalled();
    await waitForText(root, "Electron");
  });
});
