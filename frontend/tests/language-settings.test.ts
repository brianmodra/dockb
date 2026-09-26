import { afterEach, describe, expect, it } from "vitest";
import { LANGUAGES, openLanguageSettings } from "../src/renderer/layout/languageSettings";

afterEach(() => {
  document.body.replaceChildren();
});

function itemButtons(): HTMLElement[] {
  return Array.from(document.querySelectorAll<HTMLElement>('[data-testid="language-settings-item"]'));
}

function clickItem(code: string): void {
  const target = itemButtons().find((n) => n.dataset.lang === code);
  expect(target).toBeDefined();
  target.dispatchEvent(new MouseEvent("click", { bubbles: true }));
}

describe("language settings dialog", () => {
  it("renders the scrollable language list and marks the current one", () => {
    void openLanguageSettings({ current: "de" });

    expect(itemButtons().map((n) => n.textContent)).toEqual(LANGUAGES.map((l) => l.label));
    const current = document.querySelector<HTMLElement>('[data-testid="language-settings-item"][aria-current="true"]');
    expect(current?.textContent).toBe("Deutsch");
  });

  it("starts with Apply disabled and enables it once a language is chosen", () => {
    void openLanguageSettings();

    const apply = document.querySelector<HTMLButtonElement>('[data-testid="language-settings-apply"]')!;
    expect(apply.disabled).toBe(true);

    clickItem("fr");
    expect(apply.disabled).toBe(false);
  });

  it("keeps Apply enabled when the dialog opens with a current language", () => {
    void openLanguageSettings({ current: "en-GB" });
    const apply = document.querySelector<HTMLButtonElement>('[data-testid="language-settings-apply"]')!;
    expect(apply.disabled).toBe(false);
  });

  it("resolves the chosen language on Apply and closes", async () => {
    const opened = openLanguageSettings({ current: "en-US" });
    clickItem("en-GB");
    document.querySelector<HTMLButtonElement>('[data-testid="language-settings-apply"]')!.click();

    await expect(opened).resolves.toBe("en-GB");
    expect(document.querySelector(".modal-overlay")).toBeNull();
  });

  it("resolves null on Cancel and closes", async () => {
    const opened = openLanguageSettings({ current: "en-US" });
    document.querySelector<HTMLButtonElement>('[data-testid="language-settings-cancel"]')!.click();

    await expect(opened).resolves.toBeNull();
    expect(document.querySelector(".modal-overlay")).toBeNull();
  });

  it("resolves null on Escape and closes", async () => {
    const opened = openLanguageSettings({ current: "en-US" });
    window.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" }));

    await expect(opened).resolves.toBeNull();
    expect(document.querySelector(".modal-overlay")).toBeNull();
  });

  it("resolves null when clicking the overlay and closes", async () => {
    const opened = openLanguageSettings({ current: "en-US" });
    const overlay = document.querySelector<HTMLElement>(".modal-overlay")!;
    overlay.dispatchEvent(new MouseEvent("mousedown", { bubbles: true }));

    await expect(opened).resolves.toBeNull();
    expect(document.querySelector(".modal-overlay")).toBeNull();
  });

  it("moves the current mark to the newly chosen language", () => {
    void openLanguageSettings({ current: "en-US" });
    clickItem("pl");

    const current = document.querySelector<HTMLElement>('[data-testid="language-settings-item"][aria-current="true"]');
    expect(current?.textContent).toBe("Polski");
  });
});