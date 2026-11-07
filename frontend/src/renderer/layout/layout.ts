import { ResizeHandle } from "./ResizeHandle";
import { buildMenubar, type Mode } from "./menubar";

export interface AppLayoutOptions {
  initialMode?: Mode;
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
  onWidthsChange?: (widths: Record<string, number>) => void;
  onPrompt?: (prompt: string) => void;
}

const MIN_LEFT_WIDTH = 120;
const DEFAULT_LEFT_WIDTH = 240;
const MIN_RIGHT_WIDTH = 10;
const MAX_RIGHT_WIDTH = 600;
const MIN_MESSAGE_HEIGHT = 24;
const CHAT_LINE_HEIGHT = 18;
const CHAT_VERTICAL_PADDING = 4;
const CHAT_LINE_UNIT = CHAT_LINE_HEIGHT + CHAT_VERTICAL_PADDING;

export class AppLayout {
  readonly element: HTMLElement;
  mode: Mode;

  private readonly options: AppLayoutOptions;
  private readonly leftPanel: HTMLElement;
  private editPanel!: HTMLElement;
  private readonly dirtyIndicator: HTMLElement;
  private readonly userLabel: HTMLElement;
  leftPanelEl(): HTMLElement {
    return this.leftPanel;
  }
  editPanelEl(): HTMLElement {
    return this.editPanel;
  }
  private readonly rightPanel: HTMLElement;
  private readonly messagePanel: HTMLElement;
  private readonly messageLog: HTMLElement;
  private readonly chatLine: HTMLTextAreaElement;
  private leftWidth = DEFAULT_LEFT_WIDTH;
  private rightWidth = MIN_RIGHT_WIDTH;
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
      onOpen: options.onOpen,
      onImport: options.onImport,
      onQuit: options.onQuit,
      onOpenLanguageSettings: options.onOpenLanguageSettings,
      onDeleteDocument: options.onDeleteDocument,
      onEditDocument: options.onEditDocument,
      onEditChapter: options.onEditChapter,
      onSignOut: options.onSignOut,
    });

    this.leftPanel = this.panel("panel-left");

    const chat = document.createElement("textarea");
    chat.dataset.testid = "chat-line";
    chat.className = "chat-line";
    chat.setAttribute("rows", "1");
    chat.placeholder = "Prompt AI here";
    chat.spellcheck = false;
    chat.addEventListener("input", () => {
      this.setChatHeight();
    });
    chat.addEventListener("keydown", (event: KeyboardEvent) => {
      const text = chat.value.trim();
      if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        if (text !== "") {
          this.pushMessage(chat.value);
          chat.value = "";
          this.setChatHeight();
          chat.focus();
          this.options.onPrompt?.(text);
        }
      }
    });
    this.chatLine = chat;

    const dirty = document.createElement("div");
    dirty.dataset.testid = "dirty-indicator";
    dirty.className = "dirty-indicator";
    dirty.textContent = "● Unsaved";
    dirty.hidden = true;
    menubar.element.append(dirty);
    this.dirtyIndicator = dirty;

    const user = document.createElement("div");
    user.dataset.testid = "user-label";
    user.className = "user-label";
    user.hidden = true;
    menubar.element.append(user);
    this.userLabel = user;

    const editPanel = this.panel("panel-edit");
    this.editPanel = editPanel;
    this.rightPanel = this.panel("panel-right");
    this.messagePanel = this.panel("panel-message");
    const messageLog = document.createElement("div");
    messageLog.dataset.testid = "message-log";
    messageLog.className = "message-log";
    this.messageLog = messageLog;
    this.messagePanel.append(this.messageLog, this.chatLine);

    this.messagePanel.style.height = `${this.messageHeight}px`;
    this.setChatHeight();

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
        this.rightWidth = Math.max(MIN_RIGHT_WIDTH, Math.min(MAX_RIGHT_WIDTH, this.rightWidth - delta));
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
        this.setChatHeight();
        this.options.onWidthsChange?.(this.panelWidths());
      }),
      this.messagePanel,
    );

    this.leftPanel.style.width = `${this.leftWidth}px`;
    this.rightPanel.style.width = `${this.rightWidth}px`;
    this.messagePanel.style.height = `${this.messageHeight}px`;
    this.setChatHeight();
    this.applyMode();
  }

  pushMessage(text: string): void {
    for (const line of text.split("\n")) {
      if (line === "") {
        continue;
      }
      const entry = document.createElement("div");
      entry.className = "message-line";
      entry.textContent = line;
      this.messageLog.append(entry);
    }
    this.messageLog.scrollTop = this.messageLog.scrollHeight;
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
        this.leftWidth = Math.max(MIN_LEFT_WIDTH, widths.left);
        this.leftPanel.style.width = `${this.leftWidth}px`;
      }
      if (typeof widths.right === "number") {
        this.rightWidth = Math.max(MIN_RIGHT_WIDTH, Math.min(MAX_RIGHT_WIDTH, widths.right));
        this.rightPanel.style.width = `${this.rightWidth}px`;
      }
      if (typeof widths.message === "number") {
        this.messageHeight = Math.max(MIN_MESSAGE_HEIGHT, widths.message);
        this.messagePanel.style.height = `${this.messageHeight}px`;
        this.setChatHeight();
      }
      this.options.onWidthsChange?.(this.panelWidths());
    }
  }

  panelWidths(): Record<string, number> {
    return { left: this.leftWidth, right: this.rightWidth, message: this.messageHeight };
  }

  setDirty(dirty: boolean): void {
    this.dirtyIndicator.hidden = !dirty;
  }

  setUser(username: string): void {
    this.userLabel.textContent = username;
    this.userLabel.hidden = username === "";
  }

  private panel(name: string): HTMLElement {
    const el = document.createElement("section");
    el.dataset.testid = name;
    el.className = "panel";
    return el;
  }

  private isOneLinePanel(): boolean {
    return this.messageHeight <= MIN_MESSAGE_HEIGHT;
  }

  private measuredChatLines(): number {
    const scrollHeight = this.chatLine.scrollHeight;
    if (scrollHeight <= this.chatLine.clientHeight) {
      return 0;
    }
    return Math.ceil((scrollHeight - CHAT_VERTICAL_PADDING) / CHAT_LINE_HEIGHT);
  }

  private setChatHeight(): void {
    const oneLine = this.isOneLinePanel();
    this.messageLog.hidden = oneLine;
    if (oneLine) {
      this.chatLine.style.height = `${this.messageHeight}px`;
      return;
    }
    const panel = this.messageHeight;
    const needed = Math.max(this.measuredChatLines(), this.chatLine.value.split("\n").length);
    const defaultLines = Math.max(1, Math.round(panel / 3 / CHAT_LINE_UNIT));
    const maxLines = Math.max(1, Math.floor((panel - MIN_MESSAGE_HEIGHT) / CHAT_LINE_UNIT));
    const lines = Math.min(Math.max(needed, defaultLines), maxLines);
    this.chatLine.style.height = `${lines * CHAT_LINE_UNIT}px`;
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