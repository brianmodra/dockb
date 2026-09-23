import type { ApiClient } from "../api/client";
import type { DockbBridge } from "../api/bridge";
import { checkSession, login } from "../api/session";
import { reportError } from "../log";

export interface SignInGateOptions {
  provider?: string;
  onMessage?: (text: string) => void;
}

export function openSignInGate(
  api: ApiClient,
  bridge: DockbBridge,
  options: SignInGateOptions = {},
): Promise<boolean> {
  const provider = options.provider ?? "google";
  return new Promise((resolve) => {
    const overlay = document.createElement("div");
    overlay.className = "modal-overlay";
    overlay.dataset.testid = "modal";

    const dialog = document.createElement("div");
    dialog.className = "modal-dialog";

    const title = document.createElement("h2");
    title.className = "modal-title";
    title.dataset.testid = "modal-title";
    title.textContent = "Sign in";
    dialog.append(title);

    const body = document.createElement("div");
    body.className = "modal-body";
    body.textContent = "Sign in to open your documents.";
    dialog.append(body);

    const buttons = document.createElement("div");
    buttons.className = "modal-buttons";

    const cancel = document.createElement("button");
    cancel.type = "button";
    cancel.className = "modal-button";
    cancel.dataset.testid = "sign-in-cancel";
    cancel.textContent = "Cancel";
    cancel.addEventListener("click", () => {
      overlay.remove();
      resolve(false);
    });
    buttons.append(cancel);

    const signIn = document.createElement("button");
    signIn.type = "button";
    signIn.className = "modal-button";
    signIn.dataset.testid = "sign-in";
    signIn.textContent = "Sign in";
    signIn.addEventListener("click", () => {
      void attempt();
    });
    buttons.append(signIn);

    dialog.append(buttons);
    overlay.append(dialog);
    document.body.append(overlay);

    async function attempt(): Promise<void> {
      signIn.disabled = true;
      try {
        await login(api, bridge, provider);
        const user = await checkSession(api);
        if (user) {
          overlay.remove();
          resolve(true);
          return;
        }
        options.onMessage?.("Sign-in did not complete. Try again.");
        signIn.disabled = false;
      } catch (error) {
        signIn.disabled = false;
        reportError("Sign in", error, options.onMessage);
      }
    }
  });
}