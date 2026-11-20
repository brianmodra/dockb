import { createALargeSmallIcon, createMarkdownIcon } from "./modeIcons";
import { createConnectivityIcon } from "./connectivityIcon";
import { createUserRoundIcon } from "./userIcon";

export type Mode = "wysiwyg" | "raw";

export interface MenubarOptions {
  mode?: Mode;
  /** Whether the raw-markdown mode is available; off, the mode toggle is disabled. */
  rawMarkdownEnabled?: boolean;
  onMode?: (mode: Mode) => void;
  onOpen?: () => void;
  onImport?: () => void;
  onInfo?: () => void;
  onOpenDocumentSettings?: () => void;
  onOpenLanguageSettings?: () => void;
  onOpenDictionary?: () => void;
  showFileCache?: boolean;
  onFileCache?: () => void;
  showConnectivity?: boolean;
  online?: boolean;
  onConnectivityClick?: () => void;
  onDeleteDocument?: () => void;
  onSignOut?: () => void;
  onUserSettings?: () => void;
}

interface MenuSpec {
  key: string;
  label: string;
  items: MenuItemSpec[];
}

interface MenuItemSpec {
  key: string;
  label: string;
  children?: MenuItemSpec[];
  disabledWhenOffline?: boolean;
}

const MENUS: MenuSpec[] = [
  {
    key: "File",
    label: "File",
    items: [
      { key: "open", label: "Open" },
      { key: "import", label: "Import…", disabledWhenOffline: true },
      { key: "info", label: "Info" },
      {
        key: "delete",
        label: "Delete",
        children: [{ key: "delete-document", label: "Document", disabledWhenOffline: true }],
      },
    ],
  },
  {
    key: "Settings",
    label: "⚙",
    items: [
      { key: "document", label: "Document…", disabledWhenOffline: true },
      { key: "language", label: "Language…" },
      { key: "dictionary", label: "Dictionary…" },
    ],
  },
  {
    key: "user",
    label: "",
    items: [
      { key: "sign-out", label: "Sign out" },
      { key: "user-settings", label: "Settings" },
    ],
  },
];

export interface Menubar {
  element: HTMLElement;
  /** The right-aligned group holding Settings, the user menu, and the editor's status labels. */
  right: HTMLElement;
  /** Redraw the mode toggle for *mode* (icon and tooltip). */
  setMode: (mode: Mode) => void;
  /** Enable or disable the mode toggle (and re-word its tooltip) for raw markdown. */
  setRawMarkdownEnabled: (enabled: boolean) => void;
  /** Show the signed-in username (hiding the menu when empty). */
  setUser: (username: string) => void;
  /** Redraw the connectivity icon and offline-disabled menu items. */
  setOnline: (online: boolean) => void;
}

const WYSIWYG_TOOLTIP = "Switch editor to raw markdown mode";
const RAW_TOOLTIP = "Switch editor to WYSIWYG";
const RAW_MARKDOWN_DISABLED_TOOLTIP = "Change user settings to enable raw markdown mode.";

export function buildMenubar(options: MenubarOptions): Menubar {
  const element = document.createElement("div");
  element.dataset.testid = "menubar";
  element.className = "menubar";

  const right = document.createElement("div");
  right.className = "menubar-right";
  right.dataset.testid = "menubar-right";

  let rawMarkdownEnabled = options.rawMarkdownEnabled ?? false;
  let online = options.online ?? true;
  const toggle = buildModeToggle(options.mode ?? "wysiwyg", options.onMode);
  applyMode(toggle, options.mode ?? "wysiwyg", rawMarkdownEnabled);

  let userContainer: HTMLElement | null = null;
  let userName: HTMLSpanElement | null = null;
  let connectivityButton: HTMLButtonElement | null = null;
  const offlineButtons: Array<{ button: HTMLButtonElement; disabledWhenOffline: boolean }> = [];

  const menus = options.showFileCache === true
    ? MENUS.map((menu) =>
        menu.key === "Settings"
          ? { ...menu, items: [...menu.items, { key: "file-cache", label: "File Cache" }] }
          : menu,
      )
    : MENUS;

  for (const menu of menus) {
    if (menu.key === "Settings") {
      right.append(buildMenu(menu, options, offlineButtons).container);
    } else if (menu.key === "user") {
      if (options.showConnectivity === true) {
        connectivityButton = buildConnectivityButton(online, options.onConnectivityClick);
        right.append(connectivityButton);
      }
      const built = buildMenu(menu, options, offlineButtons);
      right.append(built.container);
      userContainer = built.container;
      userName = built.name;
    } else {
      element.append(buildMenu(menu, options, offlineButtons).container);
      if (menu.key === "File") {
        element.append(toggle);
      }
    }
  }
  element.append(right);

  const setOnline = (next: boolean): void => {
    online = next;
    if (connectivityButton !== null) {
      applyConnectivity(connectivityButton, online, options.onConnectivityClick);
    }
    for (const entry of offlineButtons) {
      entry.button.disabled = !online && entry.disabledWhenOffline;
    }
  };
  setOnline(online);

  return {
    element,
    right,
    setMode: (mode) => applyMode(toggle, mode, rawMarkdownEnabled),
    setOnline,
    setRawMarkdownEnabled: (enabled) => {
      rawMarkdownEnabled = enabled;
      applyMode(toggle, toggle.dataset.mode as Mode, enabled);
    },
    setUser: (username) => {
      if (userName) {
        userName.textContent = username;
      }
      if (userContainer) {
        userContainer.hidden = username === "";
      }
    },
  };
}

function buildModeToggle(initial: Mode, onMode?: (mode: Mode) => void): HTMLButtonElement {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "mode-toggle";
  button.dataset.testid = "mode-toggle";
  button.dataset.mode = initial;
  button.addEventListener("click", () => {
    if (button.disabled) {
      return;
    }
    onMode?.(button.dataset.mode === "raw" ? "wysiwyg" : "raw");
  });
  return button;
}

function applyMode(button: HTMLButtonElement, mode: Mode, rawMarkdownEnabled: boolean): void {
  button.dataset.mode = mode;
  button.replaceChildren(mode === "wysiwyg" ? createMarkdownIcon() : createALargeSmallIcon());
  if (rawMarkdownEnabled) {
    button.disabled = false;
    const title = mode === "wysiwyg" ? WYSIWYG_TOOLTIP : RAW_TOOLTIP;
    button.title = title;
    button.setAttribute("aria-label", title);
  } else {
    button.disabled = true;
    button.title = RAW_MARKDOWN_DISABLED_TOOLTIP;
    button.setAttribute("aria-label", RAW_MARKDOWN_DISABLED_TOOLTIP);
  }
}

function buildConnectivityButton(online: boolean, onClick?: () => void): HTMLButtonElement {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "connectivity-toggle";
  button.dataset.testid = "connectivity-toggle";
  applyConnectivity(button, online, onClick);
  return button;
}

function applyConnectivity(
  button: HTMLButtonElement,
  online: boolean,
  onClick?: () => void,
): void {
  button.replaceChildren(createConnectivityIcon(online));
  button.dataset.online = String(online);
  const title = online ? "Go offline?" : "Go back online?";
  button.title = title;
  button.setAttribute("aria-label", title);
  button.onclick = onClick ?? null;
}

function buildMenu(
  menu: MenuSpec,
  options: MenubarOptions,
  offlineButtons: Array<{ button: HTMLButtonElement; disabledWhenOffline: boolean }>,
): { container: HTMLElement; name: HTMLSpanElement | null } {
  const container = document.createElement("div");
  container.className = "menu";

  const label = document.createElement("button");
  label.type = "button";
  let name: HTMLSpanElement | null = null;
  if (menu.key === "user") {
    label.className = "user-label";
    label.dataset.testid = "user-label";
    label.title = "Account";
    label.setAttribute("aria-label", "Account");
    name = document.createElement("span");
    name.className = "user-label-name";
    label.append(createUserRoundIcon(), name);
    container.hidden = true;
  } else {
    label.className = "menu-label";
    label.dataset.testid = `menu-${menu.key}`;
    label.textContent = menu.label;
  }

  const dropdown = document.createElement("div");
  dropdown.className = "menu-dropdown";
  dropdown.dataset.testid = `menu-${menu.key}-dropdown`;

  const close = (): void => {
    dropdown.classList.remove("menu-dropdown--open");
    document.removeEventListener("mousedown", onBackgroundMousedown, true);
    window.removeEventListener("keydown", onKeydown);
  };

  const onBackgroundMousedown = (event: MouseEvent): void => {
    if (!container.contains(event.target as Node)) {
      close();
    }
  };

  const onKeydown = (event: KeyboardEvent): void => {
    if (event.key === "Escape") {
      close();
    }
  };

  label.addEventListener("click", () => {
    const opening = !dropdown.classList.contains("menu-dropdown--open");
    if (opening) {
      document.addEventListener("mousedown", onBackgroundMousedown, true);
      window.addEventListener("keydown", onKeydown);
    } else {
      close();
    }
    dropdown.classList.toggle("menu-dropdown--open", opening);
  });

  for (const item of menu.items) {
    if (item.children && item.children.length > 0) {
      const row = document.createElement("div");
      row.className = "menu-row";

      const parent = document.createElement("button");
      parent.type = "button";
      parent.className = "menu-item";
      parent.dataset.testid = `menu-item-${item.key}`;
      parent.textContent = item.label;

      const submenu = document.createElement("div");
      submenu.className = "menu-submenu";
      submenu.dataset.testid = `menu-submenu-${item.key}`;

      parent.addEventListener("click", () => {
        for (const open of dropdown.querySelectorAll(".menu-submenu--open")) {
          open.classList.remove("menu-submenu--open");
        }
        submenu.classList.toggle("menu-submenu--open");
      });

      for (const child of item.children) {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "menu-submenu-item";
        button.dataset.testid = `menu-item-${child.key}`;
        button.textContent = child.label;
        if (child.disabledWhenOffline === true) {
          offlineButtons.push({ button, disabledWhenOffline: true });
          button.disabled = (options.online ?? true) === false;
        }
        button.addEventListener("click", () => {
          close();
          dispatchItem(menu, child, options);
        });
        submenu.append(button);
      }

      row.append(parent, submenu);
      dropdown.append(row);
      continue;
    }

    const button = document.createElement("button");
    button.type = "button";
    button.className = "menu-item";
    button.dataset.testid = `menu-item-${item.key}`;
    button.textContent = item.label;
    if (item.disabledWhenOffline === true) {
      offlineButtons.push({ button, disabledWhenOffline: true });
      button.disabled = (options.online ?? true) === false;
    }
    button.addEventListener("click", () => {
      close();
      dispatchItem(menu, item, options);
    });
    dropdown.append(button);
  }

  container.append(label, dropdown);
  return { container, name };
}

function dispatchItem(menu: MenuSpec, item: MenuItemSpec, options: MenubarOptions): void {
  if (menu.key === "File" && item.key === "open") {
    options.onOpen?.();
  } else if (menu.key === "File" && item.key === "import") {
    options.onImport?.();
  } else if (menu.key === "File" && item.key === "info") {
    options.onInfo?.();
  } else if (menu.key === "File" && item.key === "delete-document") {
    options.onDeleteDocument?.();
  } else if (menu.key === "Settings" && item.key === "document") {
    options.onOpenDocumentSettings?.();
  } else if (menu.key === "Settings" && item.key === "language") {
    options.onOpenLanguageSettings?.();
  } else if (menu.key === "Settings" && item.key === "dictionary") {
    options.onOpenDictionary?.();
  } else if (menu.key === "Settings" && item.key === "file-cache") {
    options.onFileCache?.();
  } else if (menu.key === "user" && item.key === "sign-out") {
    options.onSignOut?.();
  } else if (menu.key === "user" && item.key === "user-settings") {
    options.onUserSettings?.();
  }
}
