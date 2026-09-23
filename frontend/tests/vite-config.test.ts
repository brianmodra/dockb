// @vitest-environment node
import { describe, expect, it } from "vitest";
import config from "../vite.config.mts";

describe("vite dev server", () => {
  it("serves on port 3000", () => {
    expect(config.server?.port).toBe(3000);
  });

  it("proxies /api to the backend on :8000", () => {
    const proxy = config.server?.proxy?.["/api"];
    expect(proxy).toBeDefined();
    expect(proxy && "target" in proxy ? proxy.target : undefined).toBe(
      "http://localhost:8000",
    );
  });
});