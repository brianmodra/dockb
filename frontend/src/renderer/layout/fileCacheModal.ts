import { reportError } from "../log";
import type { FileCache } from "../state/fileCache";
import { openOverlay, type OverlayButtonSpec } from "./overlay";

export const FILE_CACHE_MESSAGE =
  "The 'file cache' is the directory where documents will be stored on your PC. This is a cache, not the actual storage.\n" +
  "The documents are stored in a database and with versioning, on the remote server.";

export interface FileCacheModalOptions {
  allowCancel?: boolean;
  onMessage?: (text: string) => void;
}

export function openFileCacheModal(
  cache: FileCache,
  options: FileCacheModalOptions = {},
): Promise<string | null> {
  const buttons: OverlayButtonSpec[] = [
    {
      label: "Choose the file cache directory",
      testId: "file-cache-choose-button",
      primary: true,
    },
  ];
  if (options.allowCancel === true) {
    buttons.push({ label: "Cancel", testId: "file-cache-cancel-button" });
  }

  const overlay = openOverlay({ title: "File cache", buttons });
  for (const paragraph of FILE_CACHE_MESSAGE.split("\n")) {
    const message = document.createElement("p");
    message.dataset.testid = "file-cache-message";
    message.textContent = paragraph;
    overlay.body.append(message);
  }

  return new Promise((resolve) => {
    const settle = (directory: string | null): void => {
      overlay.close();
      resolve(directory);
    };

    overlay.buttons["file-cache-cancel-button"]?.addEventListener("click", () => settle(null));

    const choose = overlay.buttons["file-cache-choose-button"];
    choose.addEventListener("click", () => {
      choose.disabled = true;
      void cache.chooseDirectory().then(
        (directory) => {
          if (directory === null) {
            choose.disabled = false;
          } else {
            settle(directory);
          }
        },
        (error: unknown) => {
          choose.disabled = false;
          reportError("File cache", error, options.onMessage);
        },
      );
    });
  });
}
