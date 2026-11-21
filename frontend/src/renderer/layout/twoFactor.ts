import QRCode from "qrcode";
import type { ApiClient } from "../api/client";
import { ApiError } from "../api/http";
import type { TwoFactorChallenge, TwoFactorMethod } from "../api/types";
import { makeErrorLine, makeField, setError } from "./authForm";
import { makeBody, makeOverlay, makeTitle } from "./modals";

export function twoFactorRefusal(error: unknown): string {
  if (error instanceof ApiError && error.status === 429) {
    return "Too many attempts. Wait before trying again.";
  }
  return error instanceof Error ? error.message : String(error);
}

function makeDialog(
  title: string,
  description: string,
): { overlay: HTMLElement; dialog: HTMLElement } {
  const overlay = makeOverlay();
  const dialog = document.createElement("div");
  dialog.className = "modal-dialog";
  dialog.append(makeTitle(title), makeBody(description));
  overlay.append(dialog);
  document.body.append(overlay);
  return { overlay, dialog };
}

function methodLabel(method: TwoFactorMethod): string {
  return method === "email" ? "email" : "authenticator app";
}

export function openTwoFactorChallenge(api: ApiClient, challenge: TwoFactorChallenge): Promise<boolean> {
  return new Promise((resolve) => {
    const { overlay, dialog } = makeDialog(
      "Two-factor verification",
      `Enter the code from your ${methodLabel(challenge.method)}.`,
    );
    const error = makeErrorLine("two-factor-error");
    const codeField = makeField("two-factor-code", "Code", {
      type: "text",
      autocomplete: "one-time-code",
    });
    const code = codeField.querySelector("input") as HTMLInputElement;

    const form = document.createElement("form");
    form.dataset.testid = "two-factor-challenge-form";
    form.append(codeField, error);

    const buttons = document.createElement("div");
    buttons.className = "modal-buttons";
    const cancel = document.createElement("button");
    cancel.type = "button";
    cancel.className = "modal-button";
    cancel.dataset.testid = "two-factor-cancel";
    cancel.textContent = "Cancel";
    const verify = document.createElement("button");
    verify.type = "submit";
    verify.className = "modal-button is-primary";
    verify.dataset.testid = "two-factor-verify";
    verify.textContent = "Verify";
    buttons.append(cancel, verify);
    form.append(buttons);
    dialog.append(form);

    const close = (verified: boolean): void => {
      overlay.remove();
      resolve(verified);
    };
    cancel.addEventListener("click", () => close(false));
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      void attempt();
    });

    async function attempt(): Promise<void> {
      setError(error, "");
      verify.disabled = true;
      try {
        await api.verifyTwoFactor(challenge.challenge, code.value);
        close(true);
      } catch (failure) {
        setError(error, twoFactorRefusal(failure));
        verify.disabled = false;
        code.value = "";
        code.focus();
      }
    }

    code.focus();
  });
}

export function offerTwoFactorEnrollment(api: ApiClient): Promise<boolean> {
  return new Promise((resolve) => {
    const { overlay, dialog } = makeDialog(
      "Set up two-factor authentication",
      "Add a second factor to protect your account, or skip this and set it up later.",
    );
    const details = document.createElement("div");
    details.dataset.testid = "two-factor-details";
    const error = makeErrorLine("two-factor-error");

    const choices = document.createElement("div");
    choices.className = "modal-buttons";
    const totp = document.createElement("button");
    totp.type = "button";
    totp.className = "modal-button";
    totp.dataset.testid = "two-factor-method-totp";
    totp.textContent = "Authenticator app";
    const email = document.createElement("button");
    email.type = "button";
    email.className = "modal-button";
    email.dataset.testid = "two-factor-method-email";
    email.textContent = "Email code";
    choices.append(totp, email);

    const buttons = document.createElement("div");
    buttons.className = "modal-buttons";
    const skip = document.createElement("button");
    skip.type = "button";
    skip.className = "modal-button";
    skip.dataset.testid = "two-factor-skip";
    skip.textContent = "Not now";
    buttons.append(skip);

    dialog.append(choices, details, error, buttons);
    totp.addEventListener("click", () => void choose("totp"));
    email.addEventListener("click", () => void choose("email"));

    const close = (confirmed: boolean): void => {
      overlay.remove();
      resolve(confirmed);
    };
    skip.addEventListener("click", () => close(false));

    let method: TwoFactorMethod | null = null;
    let code: HTMLInputElement | null = null;
    let confirm: HTMLButtonElement | null = null;

    async function choose(selected: TwoFactorMethod): Promise<void> {
      method = selected;
      setError(error, "");
      totp.disabled = true;
      email.disabled = true;
      try {
        const enrollment = await api.beginTwoFactorEnrollment(selected);
        details.replaceChildren();
        if (enrollment.secret) {
          const secret = document.createElement("p");
          secret.dataset.testid = "two-factor-secret";
          secret.textContent = `Secret: ${enrollment.secret}`;
          details.append(secret);
        }
        if (enrollment.provisioningUri) {
          const image = document.createElement("img");
          image.dataset.testid = "two-factor-qr";
          image.alt = "Authenticator setup QR code";
          details.append(image);
          void QRCode.toDataURL(enrollment.provisioningUri)
            .then((url) => {
              image.src = url;
            })
            .catch((failure) => setError(error, twoFactorRefusal(failure)));
          const uri = document.createElement("p");
          uri.dataset.testid = "two-factor-uri";
          uri.textContent = enrollment.provisioningUri;
          details.append(uri);
        }
        if (selected === "email") {
          const sent = document.createElement("p");
          sent.dataset.testid = "two-factor-email-sent";
          sent.textContent = "We sent a code to your email.";
          details.append(sent);
        }

        const codeField = makeField("two-factor-code", "Code", {
          type: "text",
          autocomplete: "one-time-code",
        });
        code = codeField.querySelector("input") as HTMLInputElement;
        confirm = document.createElement("button");
        confirm.type = "button";
        confirm.className = "modal-button is-primary";
        confirm.dataset.testid = "two-factor-confirm";
        confirm.textContent = "Confirm";
        confirm.addEventListener("click", () => void submit());
        details.append(codeField);

        if (selected === "email") {
          const resend = document.createElement("button");
          resend.type = "button";
          resend.className = "modal-button";
          resend.dataset.testid = "two-factor-resend";
          resend.textContent = "Resend code";
          resend.addEventListener("click", () => void resendCode());
          buttons.prepend(resend);
        }
        buttons.append(confirm);
        code.focus();
      } catch (failure) {
        setError(error, twoFactorRefusal(failure));
        totp.disabled = false;
        email.disabled = false;
      }
    }

    async function resendCode(): Promise<void> {
      setError(error, "");
      try {
        await api.resendEmailOtp();
        const sent = document.querySelector<HTMLElement>("[data-testid='two-factor-email-sent']");
        if (sent) {
          sent.textContent = "A new code is on its way.";
        }
      } catch (failure) {
        setError(error, twoFactorRefusal(failure));
      }
    }

    async function submit(): Promise<void> {
      if (!method || !code || !confirm) {
        return;
      }
      setError(error, "");
      confirm.disabled = true;
      try {
        await api.confirmTwoFactorEnrollment(method, code.value);
        close(true);
      } catch (failure) {
        setError(error, twoFactorRefusal(failure));
        confirm.disabled = false;
        code.value = "";
        code.focus();
      }
    }
  });
}
