import type { ApiClient } from "../api/client";
import { changePassword, signOut } from "../api/session";
import { makeBody, makeOverlay, makeTitle } from "./modals";
import { makeErrorLine, makeField, setError } from "./authForm";

export type ChangePasswordOutcome = "changed" | "signed-out";

/**
 * Force a password change, and resolve once the user is through it.
 *
 * Shown before the editor loads anything: while `must_change_password` is set the
 * server refuses every manuscript route, so issuing one first would only produce a
 * 403 the user cannot act on.
 *
 * There is no Cancel. The only ways out are changing the password or signing out,
 * which is why the sign-out button is here rather than left to the sign-in gate:
 * somebody who has signed in on a colleague's temporary password needs to get back
 * to the gate, and a dialog with no way out of it is a trap. Logout is one of the
 * three routes the server keeps open for exactly this reason.
 */
export function openChangePasswordDialog(api: ApiClient): Promise<ChangePasswordOutcome> {
  return new Promise((resolve) => {
    const overlay = makeOverlay();
    const dialog = document.createElement("div");
    dialog.className = "modal-dialog";

    const error = makeErrorLine("change-password-error");

    const current = makeField("change-password-current", "Current password", {
      type: "password",
      autocomplete: "current-password",
    });
    const replacement = makeField("change-password-new", "New password", {
      type: "password",
      autocomplete: "new-password",
    });
    const currentInput = current.querySelector("input") as HTMLInputElement;
    const newInput = replacement.querySelector("input") as HTMLInputElement;

    const form = document.createElement("form");
    form.dataset.testid = "change-password-form";
    form.append(current, replacement, error);
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      void attempt();
    });

    const buttons = document.createElement("div");
    buttons.className = "modal-buttons";

    const signOutButton = document.createElement("button");
    signOutButton.type = "button";
    signOutButton.className = "modal-button";
    signOutButton.dataset.testid = "change-password-sign-out";
    signOutButton.textContent = "Sign out";
    signOutButton.addEventListener("click", () => {
      void leave();
    });

    const submit = document.createElement("button");
    submit.type = "submit";
    submit.className = "modal-button is-primary";
    submit.dataset.testid = "change-password-submit";
    submit.textContent = "Change password";

    buttons.append(signOutButton, submit);
    form.append(buttons);

    dialog.append(
      makeTitle("Change your password"),
      makeBody("Choose a password of your own before opening your documents."),
      form,
    );
    overlay.append(dialog);
    document.body.append(overlay);
    currentInput.focus();

    async function attempt(): Promise<void> {
      setError(error, "");
      submit.disabled = true;
      const old = currentInput.value;
      const chosen = newInput.value;
      try {
        await changePassword(api, old, chosen);
        currentInput.value = "";
        newInput.value = "";
        overlay.remove();
        resolve("changed");
      } catch (failure) {
        // Both fields go: the old one has been refused, and the new one is being held
        // by somebody who has not yet shown they may set it.
        currentInput.value = "";
        setError(error, failure instanceof Error ? failure.message : String(failure));
        submit.disabled = false;
        currentInput.focus();
      }
    }

    async function leave(): Promise<void> {
      setError(error, "");
      submit.disabled = true;
      try {
        await signOut(api);
        overlay.remove();
        resolve("signed-out");
      } catch (failure) {
        // Signing out that failed has not signed anybody out, so claiming it did would
        // leave the user believing they are safe when their session is still live.
        setError(error, failure instanceof Error ? failure.message : String(failure));
        submit.disabled = false;
      }
    }
  });
}