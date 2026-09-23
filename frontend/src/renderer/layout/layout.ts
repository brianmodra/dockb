import { ResizeHandle } from "./ResizeHandle";
import { buildMenubar, type Mode } from "./menubar";

export interface AppLayoutOptions {
  initialMode?: Mode;
  onMode?: (mode: Mode) => void;
}

const MIN_LEFT_WIDTH = 120;
const DEFAULT_LEFT_WIDTH = 240;
const MAX_RIGHT_WIDTH = 600;
const MIN_MESSAGE_HEIGHT = 24;

export class AppLayout {
  readonly element: HTMLElement;
  mode: Mode;

  private readonly leftPanel: HTMLElement;
  private readonly rightPanel: HTMLElement;
  private readonly messagePanel: HTMLElement;
  private leftWidth = DEFAULT_LEFT_WIDTH;
  private rightWidth = 0;
  private messageHeight = MIN_MESSAGE_HEIGHT;

  constructor(options: AppLayoutOptions = {}) {
    this.mode = options.initialMode ?? "wysiwyg";

    this.element = document.createElement("div");
    this.element.dataset.testid = "app-shell";
    this.element.className = "app-shell";

    const menubar = buildMenubar({
      mode: this.mode,
      onMode: (mode) => {
        this.mode = mode;
        this.applyMode();
        options.onMode?.(mode);
      },
    });

    this.leftPanel = this.panel("panel-left");
    const editPanel = this.panel("panel-edit");
    this.rightPanel = this.panel("panel-right");
    this.messagePanel = this.panel("panel-message");

    const mainRow = document.createElement("div");
    mainRow.className = "main-row";
    mainRow.append(
      this.leftPanel,
      this.seam("resize-handle-v-left", "vertical", (delta) => {
        this.leftWidth = Math.max(MIN_LEFT_WIDTH, this.leftWidth + delta);
        this.leftPanel.style.width = `${this.leftWidth}px`;
      }),
      editPanel,
      this.seam("resize-handle-v-right", "vertical", (delta) => {
        this.rightWidth = Math.max(0, Math.min(MAX_RIGHT_WIDTH, this.rightWidth + delta));
        this.rightPanel.style.width = `${this.rightWidth}px`;
      }),
      this.rightPanel,
    );

    this.element.append(
      menubar.element,
      mainRow,
      this.seam("resize-handle-h-bottom", "horizontal", (delta) => {
        this.messageHeight = Math.max(MIN_MESSAGE_HEIGHT, this.messageHeight - delta);
        this.messagePanel.style.height = `${this.messageHeight}px`;
      }),
      this.messagePanel,
    );

    this.leftPanel.style.width = `${this.leftWidth}px`;
    this.rightPanel.style.width = "0px";
    this.messagePanel.style.height = `${this.messageHeight}px`;
    this.applyMode();
  }

  pushMessage(text: string): void {
    const line = document.createElement("div");
    line.className = "message-line";
    line.textContent = text;
    this.messagePanel.append(line);
  }

  private panel(name: string): HTMLElement {
    const el = document.createElement("section");
    el.dataset.testid = name;
    el.className = "panel";
    return el;
  }

  private seam(
    testid: string,
    orientation: "vertical" | "horizontal",
    onDrag: (delta: number) => void,
  ): HTMLElement {
    const handle = new ResizeHandle({ orientation, onDrag });
    handle.element.dataset.testid = testid;
    return handle.element;
  }

  private applyMode(): void {
    const edit = this.element.querySelector<HTMLElement>("[data-testid='panel-edit']");
    edit?.setAttribute("data-mode", this.mode);
  }
}