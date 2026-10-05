import type { ApiClient } from "../api/client";
import { signInWithPassword } from "../api/session";
import { ApiError } from "../api/http";
import { makeBody, makeOverlay, makeTitle } from "./modals";
import { makeErrorLine, makeField, setError } from "./authForm";

/**
 * How a refusal reads to somebody who only needs to know what to do next.
 *
 * The server answers a wrong password, an unknown username and a blocked account with
 * the same `invalid_username_or_password`, and that sameness is deliberate — it keeps
 * the form from telling an attacker which usernames exist. So the message is not
 * re-derived here; it is passed through as the server phrased it, except for a
 * throttle, where "wait" is the only useful advice and repeating "invalid password"
 * would send the user off retrying into a longer wait.
 */
function refusalText(error: unknown): string {
  if (error instanceof ApiError && error.status === 429) {
    return "Too many attempts. Wait before trying again.";
  }
  return error instanceof Error ? error.message : String(error);
}

/**
 * Ask for a username and password, and resolve true once the server has a session.
 *
 * Password-only, by decision: there are no provider buttons here, so an account that
 * exists only through OAuth — whose `password_hash` is NULL — needs
 * `dockb users set-password` before it can open the editor. The backend's OAuth routes
 * are untouched and still work; only this screen stopped offering them.
 */
export function openSignInGate(api: ApiClient): Promise<boolean> {
  return new Promise((resolve) => {
    const overlay = makeOverlay();
    const dialog = document.createElement("div");
    dialog.className = "modal-dialog";

    const error = makeErrorLine("sign-in-error");

    const username = makeField("sign-in-username", "Username", {
      type: "text",
      autocomplete: "username",
    });
    const password = makeField("sign-in-password", "Password", {
      type: "password",
      autocomplete: "current-password",
    });
    const fields = username.querySelector("input") as HTMLInputElement;
    const secret = password.querySelector("input") as HTMLInputElement;

    const form = document.createElement("form");
    form.dataset.testid = "sign-in-form";
    form.append(username, password, error);
    // Enter submits a form for free; a keydown handler would only re-implement it.
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      void attempt();
    });

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

    const submit = document.createElement("button");
    submit.type = "submit";
    submit.className = "modal-button is-primary";
    submit.dataset.testid = "sign-in-submit";
    submit.textContent = "Sign in";

    buttons.append(cancel, submit);
    form.append(buttons);

    dialog.append(
      makeTitle("Sign in"),
      makeBody("Sign in to open your documents."),
      form,
    );
    overlay.append(dialog);
    document.body.append(overlay);
    fields.focus();

    async function attempt(): Promise<void> {
      setError(error, "");
      submit.disabled = true;
      const typed = secret.value;
      try {
        await signInWithPassword(api, fields.value, typed);
        // Drop the typed secret from the DOM before handing the session over, so it
        // does not outlive the dialog in a node the page is about to discard anyway.
        secret.value = "";
        overlay.remove();
        resolve(true);
      } catch (failure) {
        // The username stays so a mistyped password does not mean retyping the name;
        // the secret goes, because a refused value has no business lingering.
        secret.value = "";
        setError(error, refusalText(failure));
        submit.disabled = false;
        secret.focus();
      }
    }
  });
}