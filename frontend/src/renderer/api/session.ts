import { ApiClient } from "./client";
import { ApiError } from "./http";
import type { DockbBridge } from "./bridge";
import type { UserProfile } from "./types";

export async function checkSession(client: ApiClient): Promise<UserProfile | null> {
  try {
    return await client.getMe();
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) {
      return null;
    }
    throw error;
  }
}

export async function login(
  client: ApiClient,
  bridge: DockbBridge,
  provider: string,
): Promise<void> {
  const authorizationUrl = await client.getLoginUrl(provider);
  await bridge.openExternal(authorizationUrl);
}