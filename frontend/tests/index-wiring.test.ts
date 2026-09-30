import { afterEach, describe, expect, it, vi } from "vitest";
import { apiBase, bootRenderer } from "../src/renderer/index";

afterEach(() => {
  document.body.replaceChildren();
  vi.unstubAllEnvs();
  vi.restoreAllMocks();
});

describe("renderer entry wiring", () => {
  it("uses a relative /api base, since the shell is served by the backend", () => {
    expect(apiBase()).toBe("/api");
  });

  it("honours an explicit VITE_API_BASE override", () => {
    vi.stubEnv("VITE_API_BASE", "http://backend.test/api");
    expect(apiBase()).toBe("http://backend.test/api");
  });

  it("mounts the full editor (left and edit panels) when given an element", () => {
    const root = document.createElement("div");
    bootRenderer(root);
    const shell = root.querySelector("[data-testid='app-shell']");
    expect(shell).not.toBeNull();
    expect(root.querySelector("[data-testid='panel-left']")).not.toBeNull();
    expect(root.querySelector("[data-testid='panel-edit']")).not.toBeNull();
  });
});