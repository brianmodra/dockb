import "./styles.css";
import { ApiClient } from "./api/client";
import { mountShell } from "./main";

/** Resolve the API base the renderer talks to.
 *
 * A `VITE_API_BASE` build-time variable wins. Otherwise the relative `/api`:
 * the shell is served by the backend, so the renderer and the API share an
 * origin and a relative base stays correct wherever the backend is reached.
 */
export function apiBase(): string {
  const override = import.meta.env.VITE_API_BASE;
  if (override) {
    return override;
  }
  return "/api";
}

export function bootRenderer(root: HTMLElement | null): void {
  if (!root) {
    return;
  }
  mountShell(root, { api: new ApiClient(apiBase()) });
}

bootRenderer(document.getElementById("app"));