export type Orientation = "vertical" | "horizontal";

export interface ResizeHandleOptions {
  orientation: Orientation;
  onDrag?: (delta: number) => void;
  onDragEnd?: () => void;
}

export class ResizeHandle {
  readonly element: HTMLElement;

  private startPos = 0;
  private lastPos = 0;
  private dragging = false;

  constructor(options: ResizeHandleOptions) {
    this.element = document.createElement("div");
    this.element.dataset.testid = `resize-handle-${options.orientation}`;
    this.element.className = `resize-handle resize-handle--${options.orientation}`;

    const grip = document.createElement("div");
    grip.className = "resize-grip";
    for (let i = 0; i < 3; i += 1) {
      const bar = document.createElement("span");
      bar.className = "resize-bar";
      grip.append(bar);
    }
    this.element.append(grip);

    this.element.addEventListener("mousedown", (event: MouseEvent) => {
      this.startPos = options.orientation === "vertical" ? event.clientX : event.clientY;
      this.lastPos = this.startPos;
      this.dragging = true;
      this.element.classList.add("is-dragging");
      window.addEventListener("mousemove", this.onMove);
      window.addEventListener("mouseup", this.onUp);
      event.preventDefault();
    });
    this.onMove = (event: MouseEvent) => {
      if (!this.dragging) {
        return;
      }
      const pos = options.orientation === "vertical" ? event.clientX : event.clientY;
      const delta = pos - this.lastPos;
      this.lastPos = pos;
      options.onDrag?.(delta);
    };
    this.onUp = (): void => {
      if (!this.dragging) {
        return;
      }
      this.dragging = false;
      this.element.classList.remove("is-dragging");
      window.removeEventListener("mousemove", this.onMove);
      window.removeEventListener("mouseup", this.onUp);
      options.onDragEnd?.();
    };
  }

  private readonly onMove: (event: MouseEvent) => void;
  private readonly onUp: () => void;
}