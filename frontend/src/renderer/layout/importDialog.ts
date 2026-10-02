import type { DockbBridge } from "../api/bridge";
import type { ImportSummaryWire } from "../api/types";
import { reportError } from "../log";
import { openOverlay } from "./overlay";

export interface ImportSelection {
  directoryName: string;
  files: File[];
  singleNewlineParagraphs: boolean;
}

export interface ImportDialogOptions {
  onMessage?: (text: string) => void;
}

const UNITS = ["bytes", "KB", "MB", "GB"];

/**
 * The picked directory's own name, which webkitRelativePath does not carry.
 *
 * A picked file knows where it sits inside the chosen directory, and the preload
 * can say where it sits on disk, so stripping one from the other leaves the
 * directory. The server needs that name: it is the shared first segment every part
 * must sit under, and it becomes the document's title.
 */
export function deriveDirectoryName(
  files: File[],
  getPathForFile: DockbBridge["getPathForFile"] | undefined,
): string {
  const first = files[0];
  if (first === undefined) {
    throw new Error("Import needs at least one file, but the directory was empty");
  }
  const relative = first.webkitRelativePath ?? "";
  if (relative === "") {
    throw new Error(
      `Import needs a relative path for "${first.name}", so the file has to come from the directory picker`,
    );
  }
  if (getPathForFile === undefined) {
    throw new Error(
      "Import needs to read the chosen path, which needs the Electron preload bridge; open the editor in the desktop app",
    );
  }
  const absolute = getPathForFile(first);
  if (absolute === "") {
    throw new Error(`Import could not read the path of "${relative}"`);
  }
  const onDisk = absolute.replace(/\\/g, "/");
  const inside = relative.replace(/\\/g, "/");
  if (!onDisk.endsWith(inside)) {
    throw new Error(`Import path mismatch: "${absolute}" does not match "${relative}"`);
  }
  const segments = onDisk
    .slice(0, onDisk.length - inside.length)
    .split("/")
    .filter((segment) => segment !== "");
  const name = segments[segments.length - 1];
  if (name === undefined || name === "") {
    throw new Error(`Import could not work out which directory holds "${relative}"`);
  }
  return name;
}

function formatSize(bytes: number): string {
  let value = bytes;
  let unit = 0;
  while (value >= 1024 && unit < UNITS.length - 1) {
    value /= 1024;
    unit += 1;
  }
  const rounded = unit === 0 ? String(value) : value.toFixed(1);
  return `${rounded} ${UNITS[unit]}`;
}

function totalSize(files: File[]): number {
  return files.reduce((sum, file) => sum + file.size, 0);
}

/**
 * Confirm what is about to be imported: which directory, how much of it, and
 * whether single newlines start a paragraph.
 */
export function confirmImport(directoryName: string, files: File[]): Promise<ImportSelection | null> {
  return new Promise((resolve) => {
    const overlay = openOverlay({
      title: "Import document",
      buttons: [
        { label: "Cancel", testId: "import-dialog-cancel" },
        { label: "Import", testId: "import-dialog-confirm", primary: true },
      ],
    });

    const body = document.createElement("div");
    body.className = "modal-body";

    const name = document.createElement("div");
    name.dataset.testid = "import-dialog-name";
    name.textContent = `Document: ${directoryName}`;

    const count = document.createElement("div");
    count.dataset.testid = "import-dialog-count";
    count.textContent = `${files.length} ${files.length === 1 ? "file" : "files"}`;

    const size = document.createElement("div");
    size.dataset.testid = "import-dialog-size";
    size.textContent = `Total size: ${formatSize(totalSize(files))}`;

    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.dataset.testid = "import-dialog-paragraphs";

    const label = document.createElement("label");
    label.className = "modal-field-label";
    label.append(checkbox, document.createTextNode(" Treat single newlines as paragraph breaks"));

    body.append(name, count, size, label);
    overlay.body.append(body);

    const settle = (value: ImportSelection | null): void => {
      overlay.close();
      resolve(value);
    };

    overlay.buttons["import-dialog-cancel"].addEventListener("click", () => settle(null));
    overlay.buttons["import-dialog-confirm"].addEventListener("click", () =>
      settle({
        directoryName,
        files,
        singleNewlineParagraphs: checkbox.checked,
      }),
    );
  });
}

/** Report what the import did, one line per chapter. */
export function showImportSummaries(summaries: ImportSummaryWire[]): void {
  const overlay = openOverlay({
    title: "Import complete",
    buttons: [{ label: "Done", testId: "import-summary-close", primary: true }],
  });

  const body = document.createElement("div");
  body.className = "modal-body";
  body.dataset.testid = "import-summary-body";

  if (summaries.length === 0) {
    body.textContent = "No chapters were found in that directory.";
  } else {
    body.textContent = `${summaries.length} ${summaries.length === 1 ? "chapter" : "chapters"} imported.`;
    const list = document.createElement("div");
    list.className = "import-summary-list";
    for (const summary of summaries) {
      const row = document.createElement("div");
      row.className = "import-summary-row";
      row.dataset.testid = "import-summary-row";
      row.textContent = [
        summary.title,
        summary.category,
        summary.created ? "new" : "updated",
        `${summary.changed} changed`,
        `${summary.added} added`,
        `${summary.deleted} deleted`,
      ].join(" · ");
      list.append(row);
    }
    body.append(list);
  }

  overlay.body.append(body);
  overlay.buttons["import-summary-close"].addEventListener("click", () => overlay.close());
}

/**
 * Raise the native directory chooser and hand back what the user picked.
 *
 * A `<input webkitdirectory>` is how a renderer asks for a whole directory; the
 * browser puts up its own dialog. Cancelling that dialog fires `cancel` and picks
 * nothing, which is a cancel rather than an error.
 */
function pickDirectory(): Promise<File[] | null> {
  return new Promise((resolve) => {
    const input = document.createElement("input");
    input.type = "file";
    input.multiple = true;
    input.setAttribute("webkitdirectory", "");
    input.dataset.testid = "import-directory-input";
    input.style.display = "none";

    const finish = (files: File[] | null): void => {
      input.remove();
      resolve(files === null || files.length === 0 ? null : files);
    };

    input.addEventListener("change", () => finish(input.files === null ? null : [...input.files]));
    input.addEventListener("cancel", () => finish(null));

    document.body.append(input);
    input.click();
  });
}

/**
 * The whole import flow up to the point of sending: choose a directory, work out
 * its name, and confirm. Sending is the caller's business, so that a failure there
 * can be reported with the selection still in hand.
 */
export async function openImportDialog(
  bridge: DockbBridge | undefined,
  options: ImportDialogOptions = {},
): Promise<ImportSelection | null> {
  const files = await pickDirectory();
  if (files === null) {
    return null;
  }
  let directoryName: string;
  try {
    directoryName = deriveDirectoryName(files, bridge?.getPathForFile);
  } catch (error) {
    reportError("Import", error, options.onMessage);
    return null;
  }
  return confirmImport(directoryName, files);
}
