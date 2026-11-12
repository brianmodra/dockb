import { ResizeHandle } from "./ResizeHandle";
import { ResponseArea, type ResponseFunctions, type ResponseObject } from "./responseArea";
import { buildMenubar, type Mode } from "./menubar";

export interface AppLayoutOptions {
  initialMode?: Mode;
  onMode?: (mode: Mode) => void;
  onSave?: () => void;
  onOpen?: () => void;
  onImport?: () => void;
  onQuit?: () => void;
  onOpenLanguageSettings?: () => void;
  onOpenDictionary?: () => void;
  onDeleteDocument?: () => void;
  onEditDocument?: () => void;
  onEditChapter?: () => void;
  onSignOut?: () => void;
  onWidthsChange?: (widths: Record<string, number>) => void;
  onPrompt?: (prompt: string) => void;
  responseFunctions?: ResponseFunctions;
}

const MIN_LEFT_WIDTH = 120;
const DEFAULT_LEFT_WIDTH = 240;
const MIN_RIGHT_WIDTH = 10;
const MAX_RIGHT_WIDTH = 600;
const DEFAULT_RIGHT_WIDTH = 240;
const MIN_MESSAGE_HEIGHT = 24;
const CHAT_LINE_HEIGHT = 18;
const CHAT_VERTICAL_PADDING = 4;
const CHAT_LINE_UNIT = CHAT_LINE_HEIGHT + CHAT_VERTICAL_PADDING;
const LOG_LINE_HEIGHT = 20;
const SPINNER_HEIGHT = 24;
const RESPONSE_LINE_HEIGHT = 20;

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
  rightPanelEl(): HTMLElement {
    return this.rightPanel;
  }
  private readonly rightPanel: HTMLElement;
  private readonly messagePanel: HTMLElement;
  private readonly messageLog: HTMLElement;
  private responseArea: ResponseArea;
  private readonly chatLine: HTMLTextAreaElement;
  private lastPromptLines = 1;
  private leftWidth = DEFAULT_LEFT_WIDTH;
  private rightWidth = DEFAULT_RIGHT_WIDTH;
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
      onOpenDictionary: options.onOpenDictionary,
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
          this.lastPromptLines = chat.value.split("\n").length;
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
    this.responseArea = new ResponseArea({ functions: options.responseFunctions });
    this.messagePanel.append(this.messageLog, this.responseArea.element, this.chatLine);

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
        this.applyMessageHeight(this.messageHeight - delta);
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

  /**
   * Collapse the chat box and stand up the spinner strip while a prompt is in
   * flight; the reply (or the failure) decides what comes next. A panel too
   * small to show the submitted prompt's lines and the spinner line grows to
   * fit both; a taller panel keeps its writer-set height.
   */
  beginResponse(): void {
    this.chatLine.hidden = true;
    const needed =
      Math.max(1, this.lastPromptLines) * LOG_LINE_HEIGHT + SPINNER_HEIGHT + CHAT_VERTICAL_PADDING;
    if (needed > this.messageHeight) {
      this.applyMessageHeight(needed);
    }
    this.responseArea.showSpinner();
    this.updateResponseGeometry();
  }

  showResponse(objects: ResponseObject[]): void {
    this.chatLine.hidden = false;
    this.responseArea.show(objects);
    // A panel too small for the whole reply grows to fit it — capped at half
    // the window, past which the strip scrolls instead of the panel running
    // away. Text lines wrap, so this is a floor estimate.
    const lines = Math.max(1, objects.length);
    const needed =
      Math.max(1, this.lastPromptLines) * LOG_LINE_HEIGHT +
      lines * RESPONSE_LINE_HEIGHT +
      CHAT_LINE_UNIT +
      CHAT_VERTICAL_PADDING;
    const cap = Math.max(MIN_MESSAGE_HEIGHT, Math.floor(window.innerHeight / 2));
    if (needed > this.messageHeight) {
      this.applyMessageHeight(Math.min(needed, cap));
    }
    this.updateResponseGeometry();
  }

  cancelResponse(): void {
    this.chatLine.hidden = false;
    this.responseArea.clear();
  }

  private applyMessageHeight(height: number): void {
    this.messageHeight = Math.max(MIN_MESSAGE_HEIGHT, Math.round(height));
    this.messagePanel.style.height = `${this.messageHeight}px`;
    this.setChatHeight();
    this.options.onWidthsChange?.(this.panelWidths());
  }

  private setChatHeight(): void {
    const oneLine = this.isOneLinePanel();
    this.messageLog.hidden = oneLine;
    if (oneLine) {
      this.chatLine.style.height = `${this.messageHeight}px`;
    } else {
      const panel = this.messageHeight;
      const needed = Math.max(this.measuredChatLines(), this.chatLine.value.split("\n").length);
      const defaultLines = Math.max(1, Math.round(panel / 3 / CHAT_LINE_UNIT));
      const maxLines = Math.max(1, Math.floor((panel - MIN_MESSAGE_HEIGHT) / CHAT_LINE_UNIT));
      const lines = Math.min(Math.max(needed, defaultLines), maxLines);
      this.chatLine.style.height = `${lines * CHAT_LINE_UNIT}px`;
    }
    this.updateResponseGeometry();
  }

  /**
   * The response strip fills whatever panel height the chat box still needs:
   * the whole panel while the chat box is collapsed, panel-minus-chat otherwise.
   */
  private updateResponseGeometry(): void {
    const chat = this.chatLine.hidden ? 0 : parseInt(this.chatLine.style.height, 10) || 0;
    this.responseArea.element.style.maxHeight = `${Math.max(0, this.messageHeight - chat)}px`;
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