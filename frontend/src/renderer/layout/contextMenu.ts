export interface ContextMenuItem {
  label: string;
  /** What happens when the item is chosen; items with a submenu need none. */
  onSelect?: () => void;
  /** The currently-chosen entry of a pulldown, drawn with a tick. */
  checked?: boolean;
  children?: ContextMenuItem[];
}

export interface ContextMenuHandle {
  element: HTMLElement;
  close: () => void;
}

export function openContextMenu(
  x: number,
  y: number,
  items: ContextMenuItem[],
  options: { title?: string } = {},
): ContextMenuHandle {
  const element = document.createElement("div");
  element.className = "context-menu";
  element.dataset.testid = "context-menu";
  element.style.left = `${x}px`;
  element.style.top = `${y}px`;

  if (options.title) {
    // A title names the menu; it is not a choice, so it is not a button.
    const title = document.createElement("div");
    title.className = "context-title";
    title.textContent = options.title;
    element.append(title);
  }

  const close = (): void => {
    element.remove();
    document.removeEventListener("mousedown", onBackgroundMousedown, true);
    window.removeEventListener("keydown", onKeydown);
  };

  const onBackgroundMousedown = (event: MouseEvent): void => {
    if (!element.contains(event.target as Node)) {
      close();
    }
  };
  const onKeydown = (event: KeyboardEvent): void => {
    if (event.key === "Escape") {
      close();
    }
  };

  document.addEventListener("mousedown", onBackgroundMousedown, true);
  window.addEventListener("keydown", onKeydown);

  appendItems(element, items, close);

  document.body.append(element);
  clampIntoWindow(element, x, y);

  return { element, close };
}

/**
 * Pull *menu* back inside the window on both axes.
 *
 * Measured after mounting (the size is not known before), so a menu opened
 * near the edge shows all of itself: never left of 0, never right of the
 * window's edge, and the same vertically.
 */
function clampIntoWindow(menu: HTMLElement, x: number, y: number): void {
  const left = Math.max(0, Math.min(x, window.innerWidth - menu.offsetWidth));
  const top = Math.max(0, Math.min(y, window.innerHeight - menu.offsetHeight));
  menu.style.left = `${left}px`;
  menu.style.top = `${top}px`;
}

/**
 * Pull an open submenu back inside the window.
 *
 * A submenu hangs off its row's edge; when that would reach past the window's
 * bottom it slides up (but never above the menu's own top), and when it would
 * reach past the right edge it flips to the row's other side.
 */
function clampSubmenu(row: HTMLElement, submenu: HTMLElement): void {
  if (!submenu.classList.contains("context-submenu--open")) {
    return;
  }
  const menu = row.closest<HTMLElement>(".context-menu");
  if (!menu) {
    return;
  }
  const menuLeft = Number.parseInt(menu.style.left, 10) || 0;
  const menuTop = Number.parseInt(menu.style.top, 10) || 0;
  const viewportTop = menuTop + row.offsetTop;
  const overflowBelow = viewportTop + submenu.offsetHeight - window.innerHeight;
  if (overflowBelow > 0) {
    submenu.style.top = `-${Math.min(overflowBelow, viewportTop)}px`;
  }
  const overflowRight = menuLeft + row.offsetWidth + submenu.offsetWidth - window.innerWidth;
  if (overflowRight > 0) {
    submenu.style.left = "auto";
    submenu.style.right = "100%";
  }
}

/** Mount one level of items into *container*; a submenu opens when its parent is clicked. */
function appendItems(container: HTMLElement, items: ContextMenuItem[], close: () => void): void {
  for (const item of items) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "context-item";
    if (item.checked) {
      button.classList.add("is-checked");
    }
    button.textContent = item.label;

    if (item.children && item.children.length > 0) {
      const submenu = document.createElement("div");
      submenu.className = "context-submenu";
      appendItems(submenu, item.children, close);
      button.addEventListener("click", () => {
        submenu.classList.toggle("context-submenu--open");
        clampSubmenu(row, submenu);
      });
      const row = document.createElement("div") as HTMLDivElement;
      row.className = "context-row";
      row.append(button, submenu);
      container.append(row);
      continue;
    }

    button.addEventListener("click", () => {
      close();
      item.onSelect?.();
    });
    container.append(button);
  }
}