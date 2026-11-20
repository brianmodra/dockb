import { afterEach, describe, expect, it, vi } from "vitest";
import { buildMenubar } from "../src/renderer/layout/menubar";

afterEach(() => {
  document.body.replaceChildren();
});

function openMenu(bar: { element: HTMLElement }, key: string): void {
  bar.element.querySelector<HTMLElement>(`[data-testid="menu-${key}"]`)?.click();
}

function dropdown(bar: { element: HTMLElement }, key: string): HTMLElement {
  return bar.element.querySelector<HTMLElement>(`[data-testid="menu-${key}-dropdown"]`)!;
}

describe("menubar", () => {
  it("renders the in-window File menu, mode toggle and Settings (cog) menu", () => {
    const bar = buildMenubar({});
    document.body.append(bar.element);
    expect(bar.element.getAttribute("data-testid")).toBe("menubar");
    expect(bar.element.querySelector('[data-testid="menu-File"]')?.textContent).toBe("File");
    expect(bar.element.querySelector('[data-testid="mode-toggle"]')).not.toBeNull();
    expect(bar.element.querySelector('[data-testid="menu-Mode"]')).toBeNull();
    expect(bar.element.querySelector('[data-testid="menu-Settings"]')?.textContent).toBe("⚙");
  });

  it("groups the Settings cog on the right, away from File and the mode toggle", () => {
    const bar = buildMenubar({});
    document.body.append(bar.element);
    const right = bar.element.querySelector<HTMLElement>(".menubar-right")!;
    expect(right).not.toBeNull();
    expect(right.querySelector('[data-testid="menu-Settings"]')).not.toBeNull();
    expect(bar.element.querySelector('[data-testid="menu-File"]')).not.toBeNull();
    expect(bar.element.querySelector('[data-testid="mode-toggle"]')).not.toBeNull();
    expect(right.querySelector('[data-testid="menu-File"]')).toBeNull();
    expect(right.querySelector('[data-testid="mode-toggle"]')).toBeNull();
  });

  it("opens File with Open, Import, Info and Delete", () => {
    const bar = buildMenubar({});
    document.body.append(bar.element);
    openMenu(bar, "File");
    const itemLabels = Array.from(dropdown(bar, "File").querySelectorAll(".menu-item")).map(
      (n) => n.textContent,
    );
    expect(itemLabels).toEqual(["Open", "Import…", "Info", "Delete"]);
  });

  it("has no Save, Edit, Sign out or Quit item in the File menu", () => {
    const bar = buildMenubar({});
    document.body.append(bar.element);
    openMenu(bar, "File");
    for (const key of ["save", "edit", "sign-out", "quit"]) {
      expect(dropdown(bar, "File").querySelector(`[data-testid="menu-item-${key}"]`)).toBeNull();
    }
  });

  it("safely handles File clicks (Open wires later)", () => {
    const bar = buildMenubar({});
    document.body.append(bar.element);
    openMenu(bar, "File");
    for (const key of ["open"]) {
      expect(() =>
        bar.element
          .querySelector(`[data-testid="menu-item-${key}"]`)
          ?.dispatchEvent(new MouseEvent("click", { bubbles: true })),
      ).not.toThrow();
    }
  });

  it("reports File → Open to onOpen", () => {
    const onOpen = vi.fn();
    const bar = buildMenubar({ onOpen });
    document.body.append(bar.element);
    openMenu(bar, "File");
    bar.element.querySelector('[data-testid="menu-item-open"]')?.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    expect(onOpen).toHaveBeenCalledTimes(1);
  });

  it("shows the markdown icon and its tooltip in WYSIWYG mode, switching to raw on click", () => {
    const onMode = vi.fn();
    const bar = buildMenubar({ rawMarkdownEnabled: true, onMode });
    document.body.append(bar.element);
    const toggle = bar.element.querySelector<HTMLButtonElement>('[data-testid="mode-toggle"]')!;
    expect(toggle.dataset.mode).toBe("wysiwyg");
    expect(toggle.disabled).toBe(false);
    expect(toggle.querySelector("svg")).not.toBeNull();
    expect(toggle.title).toBe("Switch editor to raw markdown mode");
    expect(toggle.getAttribute("aria-label")).toBe("Switch editor to raw markdown mode");
    toggle.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    expect(onMode).toHaveBeenCalledWith("raw");
  });

  it("shows the Aa icon and its tooltip in raw mode, switching back to WYSIWYG on click", () => {
    const onMode = vi.fn();
    const bar = buildMenubar({ mode: "raw", rawMarkdownEnabled: true, onMode });
    document.body.append(bar.element);
    const toggle = bar.element.querySelector<HTMLButtonElement>('[data-testid="mode-toggle"]')!;
    expect(toggle.dataset.mode).toBe("raw");
    expect(toggle.disabled).toBe(false);
    expect(toggle.querySelector("svg")).not.toBeNull();
    expect(toggle.title).toBe("Switch editor to WYSIWYG");
    expect(toggle.getAttribute("aria-label")).toBe("Switch editor to WYSIWYG");
    toggle.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    expect(onMode).toHaveBeenCalledWith("wysiwyg");
  });

  it("starts with the mode toggle disabled and pointed at user settings", () => {
    const onMode = vi.fn();
    const bar = buildMenubar({ onMode });
    document.body.append(bar.element);
    const toggle = bar.element.querySelector<HTMLButtonElement>('[data-testid="mode-toggle"]')!;
    expect(toggle.disabled).toBe(true);
    expect(toggle.title).toBe("Change user settings to enable raw markdown mode.");
    expect(toggle.getAttribute("aria-label")).toBe("Change user settings to enable raw markdown mode.");
    toggle.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    expect(onMode).not.toHaveBeenCalled();
  });

  it("enables the toggle and restores its tooltip when raw markdown is allowed", () => {
    const bar = buildMenubar({});
    document.body.append(bar.element);
    const toggle = bar.element.querySelector<HTMLButtonElement>('[data-testid="mode-toggle"]')!;
    expect(toggle.disabled).toBe(true);

    bar.setRawMarkdownEnabled(true);
    expect(toggle.disabled).toBe(false);
    expect(toggle.title).toBe("Switch editor to raw markdown mode");

    bar.setRawMarkdownEnabled(false);
    expect(toggle.disabled).toBe(true);
    expect(toggle.title).toBe("Change user settings to enable raw markdown mode.");
  });

  it("updates the icon and tooltip when setMode is called", () => {
    const bar = buildMenubar({ rawMarkdownEnabled: true });
    document.body.append(bar.element);
    const toggle = bar.element.querySelector<HTMLButtonElement>('[data-testid="mode-toggle"]')!;
    expect(toggle.dataset.mode).toBe("wysiwyg");
    expect(toggle.title).toBe("Switch editor to raw markdown mode");

    bar.setMode("raw");
    expect(toggle.dataset.mode).toBe("raw");
    expect(toggle.title).toBe("Switch editor to WYSIWYG");

    bar.setMode("wysiwyg");
    expect(toggle.dataset.mode).toBe("wysiwyg");
    expect(toggle.title).toBe("Switch editor to raw markdown mode");
  });

  it("sits on the left, immediately after the File menu", () => {
    const bar = buildMenubar({});
    document.body.append(bar.element);
    const [file, toggle] = Array.from(bar.element.children) as HTMLElement[];
    expect(file.querySelector('[data-testid="menu-File"]')).not.toBeNull();
    expect(toggle.dataset.testid).toBe("mode-toggle");
  });

  it("closes the dropdown when clicking outside the menu", () => {
    const bar = buildMenubar({});
    document.body.append(bar.element);
    openMenu(bar, "File");
    expect(dropdown(bar, "File").classList.contains("menu-dropdown--open")).toBe(true);

    document.body.dispatchEvent(new MouseEvent("mousedown", { bubbles: true, clientX: 500, clientY: 500 }));
    expect(dropdown(bar, "File").classList.contains("menu-dropdown--open")).toBe(false);
  });

  it("keeps the dropdown open when clicking inside the menu", () => {
    const bar = buildMenubar({});
    document.body.append(bar.element);
    openMenu(bar, "File");

    dropdown(bar, "File").dispatchEvent(new MouseEvent("mousedown", { bubbles: true }));
    expect(dropdown(bar, "File").classList.contains("menu-dropdown--open")).toBe(true);
  });

  it("closes the dropdown on Escape", () => {
    const bar = buildMenubar({});
    document.body.append(bar.element);
    openMenu(bar, "File");

    window.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" }));
    expect(dropdown(bar, "File").classList.contains("menu-dropdown--open")).toBe(false);
  });

  it("reopens a closed dropdown and can close it again", () => {
    const bar = buildMenubar({});
    document.body.append(bar.element);
    openMenu(bar, "File");
    openMenu(bar, "File");
    expect(dropdown(bar, "File").classList.contains("menu-dropdown--open")).toBe(false);
    openMenu(bar, "File");
    expect(dropdown(bar, "File").classList.contains("menu-dropdown--open")).toBe(true);
  });

  it("renders Settings with a Language item that reports to onOpenLanguageSettings", () => {
    const onOpenLanguageSettings = vi.fn();
    const bar = buildMenubar({ onOpenLanguageSettings });
    document.body.append(bar.element);
    openMenu(bar, "Settings");
    const item = dropdown(bar, "Settings").querySelector<HTMLElement>(
      '[data-testid="menu-item-language"]',
    );
    expect(item?.textContent).toBe("Language…");
    item?.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    expect(onOpenLanguageSettings).toHaveBeenCalledTimes(1);
  });

  it("reports Settings → Document… to onOpenDocumentSettings", () => {
    const onOpenDocumentSettings = vi.fn();
    const bar = buildMenubar({ onOpenDocumentSettings });
    document.body.append(bar.element);
    openMenu(bar, "Settings");
    const item = dropdown(bar, "Settings").querySelector<HTMLElement>(
      '[data-testid="menu-item-document"]',
    );
    expect(item?.textContent).toBe("Document…");
    item?.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    expect(onOpenDocumentSettings).toHaveBeenCalledTimes(1);
  });

  it("reports Settings → Dictionary… to onOpenDictionary", () => {
    const onOpenDictionary = vi.fn();
    const bar = buildMenubar({ onOpenDictionary });
    document.body.append(bar.element);
    openMenu(bar, "Settings");
    bar.element
      .querySelector<HTMLElement>('[data-testid="menu-item-dictionary"]')
      ?.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    expect(onOpenDictionary).toHaveBeenCalledTimes(1);
  });

  it("offers Document, Language and Dictionary in the Settings menu", () => {
    const bar = buildMenubar({});
    document.body.append(bar.element);
    openMenu(bar, "Settings");
    const labels = Array.from(dropdown(bar, "Settings").querySelectorAll(".menu-item")).map(
      (n) => n.textContent,
    );
    expect(labels).toEqual(["Document…", "Language…", "Dictionary…"]);
  });
});

describe("menubar user menu", () => {
  function userLabel(bar: { element: HTMLElement }): HTMLElement {
    return bar.element.querySelector<HTMLElement>('[data-testid="user-label"]')!;
  }

  function userDropdown(bar: { element: HTMLElement }): HTMLElement {
    return bar.element.querySelector<HTMLElement>('[data-testid="menu-user-dropdown"]')!;
  }

  it("hides the user menu until a username is set", () => {
    const bar = buildMenubar({});
    document.body.append(bar.element);
    expect(userLabel(bar).closest(".menu")?.hasAttribute("hidden")).toBe(true);
  });

  it("shows the username (with an icon) once setUser is called", () => {
    const bar = buildMenubar({});
    document.body.append(bar.element);
    bar.setUser("brian");
    expect(userLabel(bar).textContent).toBe("brian");
    expect(userLabel(bar).querySelector("svg.user-icon")).not.toBeNull();
    expect(userLabel(bar).closest(".menu")?.hasAttribute("hidden")).toBe(false);
  });

  it("opens a dropdown with Sign out and Settings", () => {
    const bar = buildMenubar({});
    document.body.append(bar.element);
    bar.setUser("brian");
    userLabel(bar).click();
    expect(userDropdown(bar).classList.contains("menu-dropdown--open")).toBe(true);
    const labels = Array.from(userDropdown(bar).querySelectorAll(".menu-item")).map(
      (n) => n.textContent,
    );
    expect(labels).toEqual(["Sign out", "Settings"]);
  });

  it("reports Sign out to onSignOut", () => {
    const onSignOut = vi.fn();
    const bar = buildMenubar({ onSignOut });
    document.body.append(bar.element);
    bar.element
      .querySelector('[data-testid="menu-item-sign-out"]')
      ?.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    expect(onSignOut).toHaveBeenCalledTimes(1);
  });

  it("reports Settings to onUserSettings", () => {
    const onUserSettings = vi.fn();
    const bar = buildMenubar({ onUserSettings });
    document.body.append(bar.element);
    bar.element
      .querySelector('[data-testid="menu-item-user-settings"]')
      ?.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    expect(onUserSettings).toHaveBeenCalledTimes(1);
  });

  it("groups the user menu on the right with the Settings cog", () => {
    const bar = buildMenubar({});
    document.body.append(bar.element);
    const right = bar.element.querySelector<HTMLElement>(".menubar-right")!;
    expect(right.querySelector('[data-testid="user-label"]')).not.toBeNull();
    expect(right.querySelector('[data-testid="menu-Settings"]')).not.toBeNull();
  });
});

describe("menubar connectivity", () => {
  it("hides the connectivity icon in the browser", () => {
    const bar = buildMenubar({});
    document.body.append(bar.element);
    expect(bar.element.querySelector('[data-testid="connectivity-toggle"]')).toBeNull();
  });

  it("places a blue globe immediately left of the user menu while online", () => {
    const bar = buildMenubar({ showConnectivity: true, online: true });
    document.body.append(bar.element);
    const right = bar.element.querySelector<HTMLElement>(".menubar-right")!;
    const children = Array.from(right.children) as HTMLElement[];
    const iconIndex = children.findIndex((child) => child.dataset.testid === "connectivity-toggle");
    expect(iconIndex).toBeGreaterThanOrEqual(0);
    expect(children[iconIndex + 1].querySelector('[data-testid="user-label"]')).not.toBeNull();
    expect(children[iconIndex].querySelector('[data-testid="connectivity-online-icon"]')).not.toBeNull();
    expect(children[iconIndex].title).toBe("Go offline?");
  });

  it("reports a click on the connectivity icon", () => {
    const onConnectivityClick = vi.fn();
    const bar = buildMenubar({ showConnectivity: true, onConnectivityClick });
    document.body.append(bar.element);
    bar.element.querySelector<HTMLElement>('[data-testid="connectivity-toggle"]')!.click();
    expect(onConnectivityClick).toHaveBeenCalledTimes(1);
  });

  it("switches to a red unplug and disables backend-changing menus when set offline", () => {
    const bar = buildMenubar({ showConnectivity: true, online: true });
    document.body.append(bar.element);
    bar.setOnline(false);

    const toggle = bar.element.querySelector<HTMLElement>('[data-testid="connectivity-toggle"]')!;
    expect(toggle.querySelector('[data-testid="connectivity-offline-icon"]')).not.toBeNull();
    expect(toggle.title).toBe("Go back online?");
    expect(toggle.dataset.online).toBe("false");
    expect(bar.element.querySelector<HTMLButtonElement>('[data-testid="menu-item-import"]')!.disabled).toBe(true);
    expect(bar.element.querySelector<HTMLButtonElement>('[data-testid="menu-item-document"]')!.disabled).toBe(true);
    expect(bar.element.querySelector<HTMLButtonElement>('[data-testid="menu-item-delete-document"]')!.disabled).toBe(true);
    expect(bar.element.querySelector<HTMLButtonElement>('[data-testid="menu-item-open"]')!.disabled).toBe(false);
  });
});

describe("menubar file cache", () => {
  it("hides File Cache in the browser", () => {
    const bar = buildMenubar({});
    document.body.append(bar.element);
    openMenu(bar, "Settings");
    expect(dropdown(bar, "Settings").querySelector('[data-testid="menu-item-file-cache"]')).toBeNull();
  });

  it("shows File Cache last in the cog menu when enabled", () => {
    const bar = buildMenubar({ showFileCache: true });
    document.body.append(bar.element);
    openMenu(bar, "Settings");
    const labels = Array.from(dropdown(bar, "Settings").querySelectorAll(".menu-item")).map(
      (n) => n.textContent,
    );
    expect(labels).toEqual(["Document…", "Language…", "Dictionary…", "File Cache"]);
  });

  it("reports Settings → File Cache to onFileCache", () => {
    const onFileCache = vi.fn();
    const bar = buildMenubar({ showFileCache: true, onFileCache });
    document.body.append(bar.element);
    openMenu(bar, "Settings");
    dropdown(bar, "Settings")
      .querySelector<HTMLElement>('[data-testid="menu-item-file-cache"]')!
      .dispatchEvent(new MouseEvent("click", { bubbles: true }));
    expect(onFileCache).toHaveBeenCalledTimes(1);
  });
});

describe("menubar document actions", () => {
  it("opens the Delete submenu with its document item", () => {
    const bar = buildMenubar({});
    document.body.append(bar.element);
    openMenu(bar, "File");

    const deleteSub = bar.element.querySelector<HTMLElement>("[data-testid='menu-submenu-delete']")!;
    expect(deleteSub.classList.contains("menu-submenu--open")).toBe(false);
    bar.element.querySelector<HTMLElement>("[data-testid='menu-item-delete']")!.click();
    expect(deleteSub.classList.contains("menu-submenu--open")).toBe(true);
    expect(
      Array.from(deleteSub.querySelectorAll(".menu-submenu-item")).map((n) => n.textContent),
    ).toEqual(["Document"]);
  });

  it("reports File → Delete → Document to onDeleteDocument", () => {
    const onDeleteDocument = vi.fn();
    const bar = buildMenubar({ onDeleteDocument });
    document.body.append(bar.element);
    openMenu(bar, "File");
    bar.element.querySelector<HTMLElement>("[data-testid='menu-item-delete']")!.click();
    bar.element
      .querySelector<HTMLElement>("[data-testid='menu-item-delete-document']")!
      .dispatchEvent(new MouseEvent("click", { bubbles: true }));
    expect(onDeleteDocument).toHaveBeenCalledTimes(1);
  });
});
describe("File → Import", () => {
  it("offers Import… in the File menu", () => {
    const bar = buildMenubar({});
    const item = bar.element.querySelector('[data-testid="menu-item-import"]');
    expect(item?.textContent).toBe("Import…");
  });

  it("sits directly after Open", () => {
    const bar = buildMenubar({});
    const labels = [...bar.element.querySelectorAll(".menu-dropdown .menu-item")].map(
      (el) => el.textContent,
    );
    expect(labels.indexOf("Import…")).toBe(labels.indexOf("Open") + 1);
  });

  it("reports File → Import to onImport", () => {
    const onImport = vi.fn();
    const bar = buildMenubar({ onImport });
    bar.element
      .querySelector('[data-testid="menu-item-import"]')
      ?.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    expect(onImport).toHaveBeenCalledTimes(1);
  });

  it("does not call onOpen when Import is chosen", () => {
    const onOpen = vi.fn();
    const onImport = vi.fn();
    const bar = buildMenubar({ onOpen, onImport });
    bar.element
      .querySelector('[data-testid="menu-item-import"]')
      ?.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    expect(onOpen).not.toHaveBeenCalled();
  });

  it("is a no-op when no handler was given", () => {
    const bar = buildMenubar({});
    expect(() =>
      bar.element
        .querySelector('[data-testid="menu-item-import"]')
        ?.dispatchEvent(new MouseEvent("click", { bubbles: true })),
    ).not.toThrow();
  });
});

describe("File → Info", () => {
  it("offers Info in the File menu", () => {
    const bar = buildMenubar({});
    const item = bar.element.querySelector('[data-testid="menu-item-info"]');
    expect(item?.textContent).toBe("Info");
  });

  it("reports File → Info to onInfo", () => {
    const onInfo = vi.fn();
    const bar = buildMenubar({ onInfo });
    bar.element
      .querySelector('[data-testid="menu-item-info"]')
      ?.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    expect(onInfo).toHaveBeenCalledTimes(1);
  });

  it("is a no-op when no handler was given", () => {
    const bar = buildMenubar({});
    expect(() =>
      bar.element
        .querySelector('[data-testid="menu-item-info"]')
        ?.dispatchEvent(new MouseEvent("click", { bubbles: true })),
    ).not.toThrow();
  });
});
