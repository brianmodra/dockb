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
): ContextMenuHandle {
  const element = document.createElement("div");
  element.className = "context-menu";
  element.dataset.testid = "context-menu";
  element.style.left = `${x}px`;
  element.style.top = `${y}px`;

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

  return { element, close };
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
      });
      const row = document.createElement("div");
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