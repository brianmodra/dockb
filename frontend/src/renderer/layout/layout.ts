import { ResizeHandle } from "./ResizeHandle";
import { buildMenubar, type Mode } from "./menubar";

export interface AppLayoutOptions {
  initialMode?: Mode;
  onMode?: (mode: Mode) => void;
  onSave?: () => void;
  onQuit?: () => void;
  onWidthsChange?: (widths: Record<string, number>) => void;
}

const MIN_LEFT_WIDTH = 120;
const DEFAULT_LEFT_WIDTH = 240;
const MAX_RIGHT_WIDTH = 600;
const MIN_MESSAGE_HEIGHT = 24;

export class AppLayout {
  readonly element: HTMLElement;
  mode: Mode;

  private readonly options: AppLayoutOptions;
  private readonly leftPanel: HTMLElement;
  private editPanel!: HTMLElement;
  leftPanelEl(): HTMLElement {
    return this.leftPanel;
  }
  editPanelEl(): HTMLElement {
    return this.editPanel;
  }
  private readonly rightPanel: HTMLElement;
  private readonly messagePanel: HTMLElement;
  private leftWidth = DEFAULT_LEFT_WIDTH;
  private rightWidth = 0;
  private messageHeight = MIN_MESSAGE_HEIGHT;

  constructor(options: AppLayoutOptions = {}) {
    this.options = options;
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
      onSave: options.onSave,
      onQuit: options.onQuit,
    });

    this.leftPanel = this.panel("panel-left");
    const editPanel = this.panel("panel-edit");
    this.editPanel = editPanel;
    this.rightPanel = this.panel("panel-right");
    this.messagePanel = this.panel("panel-message");

    const mainRow = document.createElement("div");
    mainRow.className = "main-row";
    mainRow.append(
      this.leftPanel,
      this.seam("resize-handle-v-left", "vertical", (delta) => {
        this.leftWidth = Math.max(MIN_LEFT_WIDTH, this.leftWidth + delta);
        this.leftPanel.style.width = `${this.leftWidth}px`;
        this.options.onWidthsChange?.(this.panelWidths());
      }),
      editPanel,
      this.seam("resize-handle-v-right", "vertical", (delta) => {
        this.rightWidth = Math.max(0, Math.min(MAX_RIGHT_WIDTH, this.rightWidth + delta));
        this.rightPanel.style.width = `${this.rightWidth}px`;
        this.options.onWidthsChange?.(this.panelWidths());
      }),
      this.rightPanel,
    );

    this.element.append(
      menubar.element,
      mainRow,
      this.seam("resize-handle-h-bottom", "horizontal", (delta) => {
        this.messageHeight = Math.max(MIN_MESSAGE_HEIGHT, this.messageHeight - delta);
        this.messagePanel.style.height = `${this.messageHeight}px`;
        this.options.onWidthsChange?.(this.panelWidths());
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

  setMode(mode: Mode): void {
    this.mode = mode;
    this.applyMode();
    this.options.onMode?.(mode);
  }

  restoreState(state: { panel_widths?: Record<string, number> | null; edit_mode?: string | null }): void {
    if (state.edit_mode === "wysiwyg" || state.edit_mode === "raw") {
      this.setMode(state.edit_mode);
    }
    const widths = state.panel_widths;
    if (widths) {
      if (typeof widths.left === "number") {
        this.leftWidth = widths.left;
        this.leftPanel.style.width = `${this.leftWidth}px`;
      }
      if (typeof widths.right === "number") {
        this.rightWidth = widths.right;
        this.rightPanel.style.width = `${this.rightWidth}px`;
      }
      if (typeof widths.message === "number") {
        this.messageHeight = widths.message;
        this.messagePanel.style.height = `${this.messageHeight}px`;
      }
      this.options.onWidthsChange?.(this.panelWidths());
    }
  }

  panelWidths(): Record<string, number> {
    return { left: this.leftWidth, right: this.rightWidth, message: this.messageHeight };
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