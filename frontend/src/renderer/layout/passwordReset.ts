import type { ApiClient } from "../api/client";
import { ApiError } from "../api/http";
import { makeBody, makeOverlay, makeTitle } from "./modals";
import { makeErrorLine, makeField, setError } from "./authForm";

function failureText(error: unknown): string {
  if (error instanceof ApiError && error.status === 429) {
    return "Too many attempts. Wait before trying again.";
  }
  return error instanceof Error ? error.message : String(error);
}

export function openPasswordResetRequest(api: ApiClient): Promise<void> {
  return new Promise((resolve) => {
    const overlay = makeOverlay();
    const dialog = document.createElement("div");
    dialog.className = "modal-dialog";
    const body = makeBody("Enter your account email and we will send a reset link.");
    const error = makeErrorLine("password-reset-error");
    const email = makeField("password-reset-email", "Email", {
      type: "text",
      autocomplete: "email",
    });
    const input = email.querySelector("input") as HTMLInputElement;

    const form = document.createElement("form");
    form.dataset.testid = "password-reset-request-form";
    form.append(email, error);

    const buttons = document.createElement("div");
    buttons.className = "modal-buttons";
    const cancel = document.createElement("button");
    cancel.type = "button";
    cancel.className = "modal-button";
    cancel.dataset.testid = "password-reset-cancel";
    cancel.textContent = "Cancel";
    const send = document.createElement("button");
    send.type = "submit";
    send.className = "modal-button is-primary";
    send.dataset.testid = "password-reset-send";
    send.textContent = "Send reset link";
    const done = document.createElement("button");
    done.type = "button";
    done.className = "modal-button is-primary";
    done.dataset.testid = "password-reset-done";
    done.textContent = "Done";
    buttons.append(cancel, send);
    form.append(buttons);

    const close = (): void => {
      overlay.remove();
      resolve();
    };
    cancel.addEventListener("click", close);
    done.addEventListener("click", close);
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      void submit();
    });

    async function submit(): Promise<void> {
      setError(error, "");
      send.disabled = true;
      try {
        await api.requestPasswordReset(input.value);
        const sent = document.createElement("p");
        sent.dataset.testid = "password-reset-sent";
        sent.textContent = "Check your email for the reset link. It is valid for 24 hours.";
        email.hidden = true;
        body.append(sent);
        buttons.replaceChildren(done);
      } catch (failure) {
        setError(error, failureText(failure));
        send.disabled = false;
        input.focus();
      }
    }

    dialog.append(makeTitle("Reset password"), body, form);
    overlay.append(dialog);
    document.body.append(overlay);
    input.focus();
  });
}

export function openPasswordResetDialog(
  api: ApiClient,
  token: string,
  onMessage?: (text: string) => void,
): Promise<boolean> {
  return new Promise((resolve) => {
    const overlay = makeOverlay();
    const dialog = document.createElement("div");
    dialog.className = "modal-dialog";

    const body = makeBody("Choose a new password for your account.");
    const error = makeErrorLine("password-reset-error");
    const password = makeField("password-reset-new", "New password", {
      type: "password",
      autocomplete: "new-password",
    });
    const confirm = makeField("password-reset-confirm", "Confirm password", {
      type: "password",
      autocomplete: "new-password",
    });
    const newInput = password.querySelector("input") as HTMLInputElement;
    const confirmInput = confirm.querySelector("input") as HTMLInputElement;

    const form = document.createElement("form");
    form.dataset.testid = "password-reset-form";
    form.append(password, confirm, error);

    const buttons = document.createElement("div");
    buttons.className = "modal-buttons";
    const cancel = document.createElement("button");
    cancel.type = "button";
    cancel.className = "modal-button";
    cancel.dataset.testid = "password-reset-cancel";
    cancel.textContent = "Cancel";
    const submit = document.createElement("button");
    submit.type = "submit";
    submit.className = "modal-button is-primary";
    submit.dataset.testid = "password-reset-submit";
    submit.textContent = "Change password";
    buttons.append(cancel, submit);
    form.append(buttons);

    const close = (confirmed: boolean): void => {
      overlay.remove();
      resolve(confirmed);
    };
    cancel.addEventListener("click", () => close(false));
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      void attempt();
    });

    async function attempt(): Promise<void> {
      setError(error, "");
      const newPassword = newInput.value;
      if (newPassword !== confirmInput.value) {
        setError(error, "Passwords do not match.");
        return;
      }
      submit.disabled = true;
      try {
        await api.confirmPasswordReset(token, newPassword);
        overlay.remove();
        onMessage?.("Password changed. Sign in with it.");
        resolve(true);
      } catch (failure) {
        setError(error, failureText(failure));
        submit.disabled = false;
        newInput.value = "";
        confirmInput.value = "";
        newInput.focus();
      }
    }

    dialog.append(makeTitle("Choose a new password"), body, form);
    overlay.append(dialog);
    document.body.append(overlay);
    newInput.focus();
  });
}
