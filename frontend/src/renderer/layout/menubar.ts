export type Mode = "wysiwyg" | "raw";

export interface MenubarOptions {
  mode?: Mode;
  onMode?: (mode: Mode) => void;
  onSave?: () => void;
  onOpen?: () => void;
  onQuit?: () => void;
}

interface MenuSpec {
  key: string;
  label: string;
  items: MenuItemSpec[];
}

interface MenuItemSpec {
  key: string;
  label: string;
}

const MENUS: MenuSpec[] = [
  {
    key: "File",
    label: "File",
    items: [
      { key: "open", label: "Open" },
      { key: "save", label: "Save" },
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
    items: [{ key: "general", label: "General" }],
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
    const button = document.createElement("button");
    button.type = "button";
    button.className = "menu-item";
    button.dataset.testid = `menu-item-${item.key}`;
    button.textContent = item.label;
    button.addEventListener("click", () => {
      close();
      if (menu.key === "Mode") {
        const mode: Mode = item.key === "raw" ? "raw" : "wysiwyg";
        options.onMode?.(mode);
      } else if (menu.key === "File" && item.key === "save") {
        options.onSave?.();
      } else if (menu.key === "File" && item.key === "open") {
        options.onOpen?.();
      } else if (menu.key === "File" && item.key === "quit") {
        options.onQuit?.();
      }
    });
    dropdown.append(button);
  }

  container.append(label, dropdown);
  return container;
}