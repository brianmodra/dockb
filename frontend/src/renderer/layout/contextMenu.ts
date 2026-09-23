export interface ContextMenuItem {
  label: string;
  onSelect: () => void;
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

  for (const item of items) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "context-item";
    button.textContent = item.label;
    button.addEventListener("click", () => {
      close();
      item.onSelect();
    });
    element.append(button);
  }

  document.body.append(element);

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

  return { element, close };
}