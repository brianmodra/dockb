import { describe, expect, it, vi } from "vitest";
import { defaultProofreadingLanguage } from "../src/renderer/state/language";

describe("defaultProofreadingLanguage", () => {
  it("returns the backend default language", async () => {
    const api = {
      getProofreadingLanguages: vi.fn(async () => ({
        languages: [{ code: "en-GB", label: "English (UK)" }],
        default: "en-GB",
      })),
    };

    await expect(defaultProofreadingLanguage(api)).resolves.toBe("en-GB");
  });

  it("returns null when the request fails", async () => {
    const api = {
      getProofreadingLanguages: vi.fn(async () => {
        throw new Error("down");
      }),
    };

    await expect(defaultProofreadingLanguage(api)).resolves.toBeNull();
  });
});
