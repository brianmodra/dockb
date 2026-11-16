import { createALargeSmallIcon, createMarkdownIcon } from "./modeIcons";

export type Mode = "wysiwyg" | "raw";

export interface MenubarOptions {
  mode?: Mode;
  /** Whether the raw-markdown mode is available; off, the mode toggle is disabled. */
  rawMarkdownEnabled?: boolean;
  onMode?: (mode: Mode) => void;
  onOpen?: () => void;
  onImport?: () => void;
  onOpenDocumentSettings?: () => void;
  onOpenLanguageSettings?: () => void;
  onOpenDictionary?: () => void;
  onDeleteDocument?: () => void;
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
}

const MENUS: MenuSpec[] = [
  {
    key: "File",
    label: "File",
    items: [
      { key: "open", label: "Open" },
      { key: "import", label: "Import…" },
      { key: "delete", label: "Delete", children: [{ key: "delete-document", label: "Document" }] },
    ],
  },
  {
    key: "Settings",
    label: "⚙",
    items: [
      { key: "document", label: "Document…" },
      { key: "language", label: "Language…" },
      { key: "dictionary", label: "Dictionary…" },
    ],
  },
];

export interface Menubar {
  element: HTMLElement;
  /** The right-aligned group holding Settings, and the editor's status labels. */
  right: HTMLElement;
  /** Redraw the mode toggle for *mode* (icon and tooltip). */
  setMode: (mode: Mode) => void;
  /** Enable or disable the mode toggle (and re-word its tooltip) for raw markdown. */
  setRawMarkdownEnabled: (enabled: boolean) => void;
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
  const toggle = buildModeToggle(options.mode ?? "wysiwyg", options.onMode);
  applyMode(toggle, options.mode ?? "wysiwyg", rawMarkdownEnabled);

  for (const menu of MENUS) {
    if (menu.key === "Settings") {
      right.append(buildMenu(menu, options));
    } else {
      element.append(buildMenu(menu, options));
      if (menu.key === "File") {
        element.append(toggle);
      }
    }
  }
  element.append(right);

  return {
    element,
    right,
    setMode: (mode) => applyMode(toggle, mode, rawMarkdownEnabled),
    setRawMarkdownEnabled: (enabled) => {
      rawMarkdownEnabled = enabled;
      applyMode(toggle, toggle.dataset.mode as Mode, enabled);
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

function buildMenu(menu: MenuSpec, options: MenubarOptions): HTMLElement {
  const container = document.createElement("div");
  container.className = "menu";

  const label = document.createElement("button");
  label.type = "button";
  label.className = "menu-label";
  label.dataset.testid = `menu-${menu.key}`;
  label.textContent = menu.label;

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
    button.addEventListener("click", () => {
      close();
      dispatchItem(menu, item, options);
    });
    dropdown.append(button);
  }

  container.append(label, dropdown);
  return container;
}

function dispatchItem(menu: MenuSpec, item: MenuItemSpec, options: MenubarOptions): void {
  if (menu.key === "File" && item.key === "open") {
    options.onOpen?.();
  } else if (menu.key === "File" && item.key === "import") {
    options.onImport?.();
  } else if (menu.key === "File" && item.key === "delete-document") {
    options.onDeleteDocument?.();
  } else if (menu.key === "Settings" && item.key === "document") {
    options.onOpenDocumentSettings?.();
  } else if (menu.key === "Settings" && item.key === "language") {
    options.onOpenLanguageSettings?.();
  } else if (menu.key === "Settings" && item.key === "dictionary") {
    options.onOpenDictionary?.();
  }
}
