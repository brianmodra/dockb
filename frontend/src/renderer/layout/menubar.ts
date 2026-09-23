export type Mode = "wysiwyg" | "raw";

export interface MenubarOptions {
  mode?: Mode;
  onMode?: (mode: Mode) => void;
  onSave?: () => void;
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
  label.addEventListener("click", () => {
    dropdown.classList.toggle("menu-dropdown--open");
  });

  for (const item of menu.items) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "menu-item";
    button.dataset.testid = `menu-item-${item.key}`;
    button.textContent = item.label;
    button.addEventListener("click", () => {
      dropdown.classList.remove("menu-dropdown--open");
      if (menu.key === "Mode") {
        const mode: Mode = item.key === "raw" ? "raw" : "wysiwyg";
        options.onMode?.(mode);
      } else if (menu.key === "File" && item.key === "save") {
        options.onSave?.();
      }
    });
    dropdown.append(button);
  }

  container.append(label, dropdown);
  return container;
}