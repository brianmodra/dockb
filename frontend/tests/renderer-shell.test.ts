import { afterEach, describe, expect, it } from "vitest";
import { mountShell } from "../src/renderer/main";

afterEach(() => {
  document.body.replaceChildren();
});

describe("renderer shell", () => {
  it("mounts an empty shell window with a menubar placeholder", () => {
    mountShell(document.body);
    const shell = document.querySelector("[data-testid='app-shell']");
    expect(shell).not.toBeNull();
    expect(shell?.querySelector("[data-testid='menubar']")).not.toBeNull();
  });

  it("is idempotent — mounting again replaces, not duplicates", () => {
    mountShell(document.body);
    mountShell(document.body);
    expect(document.querySelectorAll("[data-testid='app-shell']")).toHaveLength(1);
  });
});