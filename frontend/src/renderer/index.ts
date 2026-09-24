import "./styles.css";
import { ApiClient } from "./api/client";
import { mountShell } from "./main";

/** Resolve the API base the renderer talks to.
 *
 * A `VITE_API_BASE` build-time variable wins. Otherwise, when the app is
 * loaded from a local `file://` (the packaged Electron shell) the client
 * points straight at the loopback backend; when served over http the Vite dev
 * proxy answers on the same origin, so a relative `/api` base is used.
 */
export function apiBase(location: { protocol: string } = window.location): string {
  const override = import.meta.env.VITE_API_BASE;
  if (override) {
    return override;
  }
  return location.protocol === "file:" ? "http://localhost:8000/api" : "/api";
}

export function bootRenderer(root: HTMLElement | null): void {
  if (!root) {
    return;
  }
  mountShell(root, { api: new ApiClient(apiBase()) });
}

bootRenderer(document.getElementById("app"));