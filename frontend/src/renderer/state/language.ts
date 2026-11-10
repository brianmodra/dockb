import type { ApiClient } from "../api/client";

export async function defaultProofreadingLanguage(
  api: Pick<ApiClient, "getProofreadingLanguages">,
): Promise<string | null> {
  try {
    const response = await api.getProofreadingLanguages();
    return response.default || null;
  } catch {
    return null;
  }
}
