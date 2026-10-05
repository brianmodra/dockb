import type { ApiClient } from "../api/client";
import { checkSession } from "../api/session";
import type { Session } from "../api/types";
import { openSignInGate } from "./signInGate";
import { openChangePasswordDialog } from "./changePasswordDialog";

export interface EnsureSignedInOptions {
  onMessage?: (text: string) => void;
}

/**
 * Get the editor to a session it may actually use, or to nothing.
 *
 * Resolves the session, or null when the user cancelled out of the gate or signed out
 * of the change dialog — both mean "stop here", and the caller should not load state.
 *
 * A first-time user signs in twice, and that is the server's rule rather than this
 * one's: changing a password stamps the credentials, which refuses every session older
 * than the stamp, including the one the change arrived on. So the change dialog is
 * followed by the sign-in gate again. The new password is not held in memory to post a
 * second time — the user types it.
 */
export async function ensureSignedIn(
  api: ApiClient,
  options: EnsureSignedInOptions = {},
): Promise<Session | null> {
  let session = await settled(checkSession(api));

  if (!session) {
    const signedIn = await openSignInGate(api);
    if (!signedIn) {
      return null;
    }
    session = await checkSession(api);
  }

  if (session?.passwordChangeRequired) {
    const outcome = await openChangePasswordDialog(api);
    if (outcome === "signed-out") {
      return null;
    }
    options.onMessage?.("Your password has changed. Sign in with it.");
    const signedInAgain = await openSignInGate(api);
    if (!signedInAgain) {
      return null;
    }
    session = await checkSession(api);
  }

  return session;
}

/**
 * A session check that cannot throw.
 *
 * Only the editor's first question — "is anybody signed in?" — treats an error as
 * "no". Past that point a failure is a real failure and is left to propagate, so a
 * backend that is down does not look like a signed-out user.
 */
async function settled(check: Promise<Session | null>): Promise<Session | null> {
  try {
    return await check;
  } catch {
    return null;
  }
}