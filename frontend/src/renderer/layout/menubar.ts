export type Mode = "wysiwyg" | "raw";

export interface MenubarOptions {
  mode?: Mode;
  onMode?: (mode: Mode) => void;
  onSave?: () => void;
  onOpen?: () => void;
  onImport?: () => void;
  onQuit?: () => void;
  onOpenLanguageSettings?: () => void;
  onDeleteDocument?: () => void;
  onEditDocument?: () => void;
  onEditChapter?: () => void;
  onSignOut?: () => void;
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
      { key: "save", label: "Save" },
      { key: "delete", label: "Delete", children: [{ key: "delete-document", label: "Document" }] },
      {
        key: "edit",
        label: "Edit",
        children: [
          { key: "edit-document", label: "Document" },
          { key: "edit-chapter", label: "Chapter" },
        ],
      },
      { key: "sign-out", label: "Sign out" },
      { key: "quit", label: "Quit" },
    ],
  },
  {
    key: "Mode",
    label: "Mode",
    items: [
      { key: "wysiwyg", label: "WYSIWYG" },
      { key: "raw", label: "Raw MD" },
    ],
  },
  {
    key: "Settings",
    label: "⚙",
    items: [{ key: "language", label: "Language…" }],
  },
];

export interface Menubar {
  element: HTMLElement;
}

export function buildMenubar(options: MenubarOptions): Menubar {
  const element = document.createElement("div");
  element.dataset.testid = "menubar";
  element.className = "menubar";

  for (const menu of MENUS) {
    element.append(buildMenu(menu, options));
  }

  return { element };
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
  if (menu.key === "Mode") {
    const mode: Mode = item.key === "raw" ? "raw" : "wysiwyg";
    options.onMode?.(mode);
  } else if (menu.key === "File" && item.key === "save") {
    options.onSave?.();
  } else if (menu.key === "File" && item.key === "open") {
    options.onOpen?.();
  } else if (menu.key === "File" && item.key === "import") {
    options.onImport?.();
  } else if (menu.key === "File" && item.key === "quit") {
    options.onQuit?.();
  } else if (menu.key === "File" && item.key === "delete-document") {
    options.onDeleteDocument?.();
  } else if (menu.key === "File" && item.key === "edit-document") {
    options.onEditDocument?.();
  } else if (menu.key === "File" && item.key === "edit-chapter") {
    options.onEditChapter?.();
  } else if (menu.key === "File" && item.key === "sign-out") {
    options.onSignOut?.();
  } else if (menu.key === "Settings" && item.key === "language") {
    options.onOpenLanguageSettings?.();
  }
}