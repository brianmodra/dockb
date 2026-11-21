import { ApiClient } from "./client";
import { ApiError } from "./http";
import type {
  Session,
  SignInResult,
  TwoFactorEnrollment,
  TwoFactorMethod,
} from "./types";

export type { SignInResult } from "./types";

/**
 * Who is signed in, or null when nobody is.
 *
 * Only a 401 means "nobody". Anything else is a real failure and propagates, so a
 * backend that is down is not mistaken for a signed-out editor.
 */
export async function checkSession(client: ApiClient): Promise<Session | null> {
  try {
    return await client.getMe();
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) {
      return null;
    }
    throw error;
  }
}

/**
 * Sign in with a username and password, and report what the session may now do.
 *
 * `passwordChangeRequired` comes back here rather than needing a second request,
 * because the answer is already in the sign-in response and the editor has to know it
 * before it loads anything.
 */
export async function signInWithPassword(
  client: ApiClient,
  username: string,
  password: string,
): Promise<SignInResult> {
  return client.loginWithPassword(username, password);
}

export async function verifyTwoFactor(
  client: ApiClient,
  challenge: string,
  code: string,
): Promise<Session> {
  return client.verifyTwoFactor(challenge, code);
}

export async function requestPasswordReset(client: ApiClient, email: string): Promise<void> {
  await client.requestPasswordReset(email);
}

export async function confirmPasswordReset(
  client: ApiClient,
  token: string,
  newPassword: string,
): Promise<void> {
  await client.confirmPasswordReset(token, newPassword);
}

export async function beginTwoFactorEnrollment(
  client: ApiClient,
  method: TwoFactorMethod,
): Promise<TwoFactorEnrollment> {
  return client.beginTwoFactorEnrollment(method);
}

export async function confirmTwoFactorEnrollment(
  client: ApiClient,
  method: TwoFactorMethod,
  code: string,
): Promise<void> {
  await client.confirmTwoFactorEnrollment(method, code);
}

export async function resendEmailOtp(client: ApiClient): Promise<void> {
  await client.resendEmailOtp();
}

/**
 * Replace the current password.
 *
 * This always signs the caller out: the server stamps the credentials, and every
 * session older than the stamp stops resolving. The editor therefore presents the
 * sign-in gate afterwards rather than continuing on a session that is already dead.
 */
export async function changePassword(
  client: ApiClient,
  currentPassword: string,
  newPassword: string,
): Promise<void> {
  await client.changePassword(currentPassword, newPassword);
}

export async function signOut(client: ApiClient): Promise<void> {
  await client.logout();
}