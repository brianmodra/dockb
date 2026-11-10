import { EditorState, Plugin, PluginKey, TextSelection, type Command } from "prosemirror-state";
import { EditorView, Decoration, DecorationSet } from "prosemirror-view";
import { Schema, type Node } from "prosemirror-model";
import { baseKeymap, splitBlock } from "prosemirror-commands";
import { keymap } from "prosemirror-keymap";
import { history, redo, undo } from "prosemirror-history";
import MarkdownIt from "markdown-it";
import type { ProofreadingDiagnostic } from "../api/types";

const insertHardBreak: Command = (state, dispatch) => {
  const br = state.schema.nodes.hardBreak;
  if (!br) {
    return false;
  }
  if (dispatch) {
    dispatch(state.tr.replaceSelectionWith(br.create()));
  }
  return true;
};

const schema = new Schema({
  nodes: {
    doc: { content: "paragraph+" },
    paragraph: {
      content: "inline*",
      attrs: { blanksBefore: { default: 0 }, id: { default: null }, quoteType: { default: "" } },
      toDOM: (node) =>
        node.attrs.quoteType
          ? ["p", { class: "quoted", "data-quote-type": node.attrs.quoteType }, 0]
          : ["p", 0],
    },
    text: { group: "inline" },
    hardBreak: { inline: true, group: "inline", selectable: false, toDOM: () => ["br"] },
  },
  marks: {
    sentenceBreak: { toDOM: () => ["span", { class: "wysiwyg-sb" }] },
  },
});

const SENTENCE_BREAK = "sentenceBreak";

const FRONT_MATTER_RE = /^---\r?\n[\s\S]*?\r?\n---(?:\r?\n|$)/;
const SPAN_TAG_RE = /<\/?span(\s[^>]*)?>/g;
const PURE_SPAN_LINE_RE = /^\s*<\/?span(\s[^>]*)?>\s*$/;

const ENTITIES: Record<string, string> = {
  "&amp;": "&",
  "&lt;": "<",
  "&gt;": ">",
  "&quot;": '"',
  "&#x27;": "'",
  "&#39;": "'",
};

export function unescapeHtml(text: string): string {
  return text.replace(/&(amp|lt|gt|quot|#x27|#39);/g, (match) => ENTITIES[match] ?? match);
}

export function escapeHtml(text: string): string {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#x27;");
}

interface SpanAttrs {
  ids: Array<string | null>;
  quoteTypes: Array<string | null>;
}

function extractSpanAttrs(buffer: string): SpanAttrs {
  const hadFrontMatter = FRONT_MATTER_RE.test(buffer);
  const withoutFrontMatter = buffer.replace(FRONT_MATTER_RE, "");
  const body = hadFrontMatter ? withoutFrontMatter.replace(/^\n/, "") : withoutFrontMatter;
  const ids: Array<string | null> = [];
  const quoteTypes: Array<string | null> = [];
  body.split("\n\n").forEach((block) => {
    const open = block.match(/<span\b([^>]*)>/);
    if (!open) {
      ids.push(null);
      quoteTypes.push(null);
      return;
    }
    const attr = open[1].match(/\bdata-par-id="([^"]*)"/);
    ids.push(attr ? unescapeHtml(attr[1]) : null);
    const quote = open[1].match(/\bdata-quote-type="([^"]*)"/);
    quoteTypes.push(quote ? unescapeHtml(quote[1]) : null);
  });
  return { ids, quoteTypes };
}

/** The per-paragraph quote types of *doc*, in order — the dirty check's comparison. */
function signatureFromDoc(doc: Node): string {
  const types: string[] = [];
  doc.forEach((paragraph) => types.push(paragraph.attrs.quoteType ?? ""));
  return types.join("\u241F");
}

/** The canonical *buffer*'s per-paragraph quote types, in order — see `WysiwygView.quoteSignature`. */
export function quoteSignatureOf(buffer: string): string {
  const { ids, quoteTypes } = extractSpanAttrs(buffer);
  return signatureFromDoc(bufferToDocWithIds(chapterBody(buffer), ids, quoteTypes));
}

export function chapterBody(buffer: string): string {
  const hadFrontMatter = FRONT_MATTER_RE.test(buffer);
  const withoutFrontMatter = buffer.replace(FRONT_MATTER_RE, "");
  const body = withoutFrontMatter
    .split("\n")
    .filter((line) => !PURE_SPAN_LINE_RE.test(line))
    .map((line) => unescapeHtml(line.replace(SPAN_TAG_RE, "")))
    .join("\n");
  return hadFrontMatter ? body.replace(/^\n/, "") : body;
}

interface BodyBlock {
  blanksBefore: number;
  lines: string[];
}

function parseBodyBlocks(body: string): BodyBlock[] {
  if (body.length === 0) {
    return [];
  }
  const blocks: BodyBlock[] = [];
  let pendingBlanks = 0;
  let current: string[] | null = null;
  let currentBlanks = 0;
  for (const line of body.split("\n")) {
    if (line === "") {
      pendingBlanks += 1;
      if (current) {
        blocks.push({ blanksBefore: currentBlanks, lines: current });
        current = null;
      }
    } else if (current) {
      current.push(line);
    } else {
      current = [line];
      currentBlanks = pendingBlanks;
      pendingBlanks = 0;
    }
  }
  if (current) {
    blocks.push({ blanksBefore: currentBlanks, lines: current });
  } else if (pendingBlanks > 0) {
    blocks.push({ blanksBefore: pendingBlanks, lines: [] });
  }
  return blocks;
}

function paragraphContent(block: BodyBlock): Node[] {
  const content: Node[] = [];
  block.lines.forEach((line, index) => {
    const trimmed = line.replace(/[ \t]+$/, "");
    const escaped = trimmed.endsWith("\\");
    const text = escaped ? trimmed.slice(0, -1) : trimmed;
    if (text) {
      content.push(schema.text(text));
    }
    const isLast = index === block.lines.length - 1;
    if (escaped) {
      content.push(schema.node("hardBreak"));
    } else if (!isLast) {
      content.push(schema.text(" ", [schema.mark(SENTENCE_BREAK)]));
    }
  });
  return content;
}

export function bufferToDoc(body: string) {
  return bufferToDocWithIds(body, []);
}

export function bufferToDocWithIds(body: string, ids: Array<string | null>, quoteTypes: Array<string | null> = []) {
  const blocks = parseBodyBlocks(body);
  const paragraphs =
    blocks.length > 0
      ? blocks.map((block, index) =>
          schema.node(
            "paragraph",
            { blanksBefore: block.blanksBefore, id: ids[index] ?? null, quoteType: quoteTypes[index] ?? "" },
            paragraphContent(block),
          ),
        )
      : [schema.node("paragraph", { blanksBefore: 0, id: null, quoteType: "" })];
  return schema.node("doc", {}, paragraphs);
}

function serializeParagraph(paragraph: Node): string {
  const sentences: string[] = [];
  let pending = "";
  paragraph.forEach((node) => {
    if (node.isText && node.text) {
      if (node.text === " " && node.marks.some((mark) => mark.type.name === SENTENCE_BREAK)) {
        sentences.push(pending.replace(/[ \t]+$/, ""));
        pending = "";
      } else {
        pending += node.text;
      }
    } else if (node.type.name === "hardBreak") {
      sentences.push(pending.replace(/[ \t]+$/, "") + "\\");
      pending = "";
    }
  });
  sentences.push(pending.replace(/[ \t]+$/, ""));
  return sentences.join("\n");
}

export function docToString(doc: Node): string {
  const parts: string[] = [];
  let isFirst = true;
  doc.forEach((paragraph) => {
    const blanks = paragraph.attrs.blanksBefore ?? 0;
    const separator = !isFirst && paragraph.childCount > 0 ? (blanks > 0 ? blanks + 1 : 2) : blanks;
    parts.push("\n".repeat(separator) + serializeParagraph(paragraph));
    isFirst = false;
  });
  return parts.join("");
}

export function docToCanonical(doc: Node): string {
  const parts: string[] = [];
  const seen = new Set<string>();
  let isFirst = true;
  doc.forEach((paragraph) => {
    const blanks = paragraph.attrs.blanksBefore ?? 0;
    const separator = !isFirst && paragraph.childCount > 0 ? (blanks > 0 ? blanks + 1 : 2) : blanks;
    let id: string | null = paragraph.attrs.id ?? null;
    if (id !== null) {
      if (seen.has(id)) {
        id = null;
      } else {
        seen.add(id);
      }
    }
    const lines = serializeParagraph(paragraph);
    const quote = paragraph.attrs.quoteType ? ` data-quote-type="${escapeHtml(paragraph.attrs.quoteType)}"` : "";
    const body =
      id !== null
        ? `<span data-par-id="${escapeHtml(id)}"${quote}>\n${escapeHtml(lines)}\n</span>`
        : lines;
    parts.push("\n".repeat(separator) + body);
    isFirst = false;
  });
  return parts.join("");
}

export function findHeadingLines(
  buffer: string,
  md: ReturnType<typeof MarkdownIt>,
): Set<number> {
  const headings = new Set<number>();
  for (const token of md.parse(buffer, {})) {
    if (token.type === "heading_open" && token.map) {
      headings.add(token.map[0]);
    }
  }
  return headings;
}

const headingMarkupKey = new PluginKey<DecorationSet>("heading-markup");

function headingDecorations(md: ReturnType<typeof MarkdownIt>): Plugin<DecorationSet> {
  const compute = (doc: Node) => {
    const text = docToString(doc);
    const headings = findHeadingLines(text, md);
    const decorations: Decoration[] = [];
    let line = 0;
    doc.forEach((node, offset) => {
      line += node.attrs.blanksBefore ?? 0;
      if (headings.has(line)) {
        decorations.push(
          Decoration.node(offset, offset + node.nodeSize, { class: "prose-heading" }),
        );
      }
      line += serializeParagraph(node).split("\n").length;
    });
    return DecorationSet.create(doc, decorations);
  };

  return new Plugin({
    key: headingMarkupKey,
    state: {
      init: (_config, state) => compute(state.doc),
      apply: (_tr, _old, _oldState, newState) => compute(newState.doc),
    },
    props: {
      decorations: (state) => headingMarkupKey.getState(state) ?? DecorationSet.empty,
    },
  });
}

export interface WysiwygViewOptions {
  onChange?: (content: string) => void;
  onSelectionChange?: () => void;
}

export interface SelectionPoint {
  paragraphId: string | null;
  paragraphIndex: number;
  sentenceIndex: number;
  offset: number;
}

/** The paragraph whose check a cursor position selects. */
export interface ProofreadingParagraph {
  paragraphId: string | null;
  paragraphIndex: number;
  text: string;
  focus: { start: number; end: number } | null;
  contentStart: number;
  contentEnd: number;
}

/** A wire diagnostic mapped onto ProseMirror positions in the open document. */
export interface WysiwygDiagnostic extends ProofreadingDiagnostic {
  from: number;
  to: number;
  word: string;
}

/** The editor state a selected-text action needs, captured when it is chosen. */
export interface SelectionContext {
  text: string;
  paragraphIds: Array<string | null>;
  paragraphIndexes: number[];
  quoteType: string;
  start: SelectionPoint;
  end: SelectionPoint;
}

interface ParagraphSpan {
  node: Node;
  pos: number;
  index: number;
  contentStart: number;
  contentEnd: number;
}

function paragraphSpans(doc: Node): ParagraphSpan[] {
  const spans: ParagraphSpan[] = [];
  doc.forEach((node, offset) => {
    spans.push({
      node,
      pos: offset,
      index: spans.length,
      contentStart: offset + 1,
      contentEnd: offset + node.nodeSize - 1,
    });
  });
  return spans;
}

interface ProofreadingState {
  diagnostics: WysiwygDiagnostic[];
  decorations: DecorationSet;
}

const proofreadingPluginKey = new PluginKey<ProofreadingState>("proofreading");

function proofreadingDecoration(diagnostic: WysiwygDiagnostic): Decoration {
  return Decoration.inline(diagnostic.from, diagnostic.to, {
    class: diagnostic.severity === "info" ? "proofreading-info" : "proofreading-warning",
    "data-severity": diagnostic.severity,
    title: diagnostic.message,
  });
}

function proofreadingPlugin(): Plugin<ProofreadingState> {
  return new Plugin<ProofreadingState>({
    key: proofreadingPluginKey,
    state: {
      init: () => ({ diagnostics: [], decorations: DecorationSet.empty }),
      apply: (tr, value) => {
        const set = tr.getMeta(proofreadingPluginKey) as WysiwygDiagnostic[] | undefined;
        if (set !== undefined) {
          const diagnostics = set.filter(
            (diagnostic) => diagnostic.from < diagnostic.to && diagnostic.to <= tr.doc.content.size,
          );
          return {
            diagnostics,
            decorations: DecorationSet.create(tr.doc, diagnostics.map(proofreadingDecoration)),
          };
        }
        if (!tr.docChanged) {
          return value;
        }
        const diagnostics = value.diagnostics
          .map((diagnostic) => {
            const from = tr.mapping.map(diagnostic.from);
            const to = tr.mapping.map(diagnostic.to);
            return { ...diagnostic, from, to, word: tr.doc.textBetween(from, to, " ") };
          })
          .filter((diagnostic) => diagnostic.from < diagnostic.to);
        return {
          diagnostics,
          decorations: DecorationSet.create(tr.doc, diagnostics.map(proofreadingDecoration)),
        };
      },
    },
    props: {
      decorations: (state) => proofreadingPluginKey.getState(state)?.decorations ?? null,
    },
  });
}

export class WysiwygView {
  readonly element: HTMLElement;
  private readonly options: WysiwygViewOptions;
  private innerView: EditorView | null = null;
  private lastFrontMatter: string | null = null;
  private language: string;

  constructor(options: WysiwygViewOptions = {}) {
    this.options = options;
    this.language = document.documentElement.lang || "en-US";
    this.element = document.createElement("div");
    this.element.dataset.testid = "wysiwyg-view";
  }

  get view(): EditorView {
    if (!this.innerView) {
      throw new Error("WysiwygView is not mounted");
    }
    return this.innerView;
  }

  getLanguage(): string {
    return this.language;
  }

  setLanguage(lang: string): void {
    this.language = lang;
    this.innerView?.dom.setAttribute("lang", lang);
  }

  /** The paragraph and sentence the cursor is in, ready for a backend check. */
  currentProofreadingParagraph(): ProofreadingParagraph | null {
    if (!this.innerView) {
      return null;
    }
    const { from } = this.innerView.state.selection;
    const span = this.paragraphAt(paragraphSpans(this.innerView.state.doc), from);
    if (!span) {
      return null;
    }
    const text = span.node.textBetween(0, span.node.content.size, " ");
    const offset = Math.min(Math.max(from - span.contentStart, 0), span.node.content.size);
    const range =
      this.sentenceRanges(span.node).find(
        (candidate) => offset >= candidate.from && offset <= candidate.to,
      ) ?? null;
    const focus = range ? { start: range.from, end: range.to } : null;
    return {
      paragraphId: span.node.attrs.id ?? null,
      paragraphIndex: span.index,
      text,
      focus,
      contentStart: span.contentStart,
      contentEnd: span.contentEnd,
    };
  }

  /** Decorate *context*'s diagnostics and return them mapped to document positions. */
  setProofreadingDiagnostics(
    context: ProofreadingParagraph,
    diagnostics: ProofreadingDiagnostic[],
  ): WysiwygDiagnostic[] {
    if (!this.innerView) {
      return [];
    }
    const span = paragraphSpans(this.innerView.state.doc).find(
      (candidate) => candidate.index === context.paragraphIndex && candidate.contentStart === context.contentStart,
    );
    if (!span || span.node.textBetween(0, span.node.content.size, " ") !== context.text) {
      return [];
    }
    const mapped: WysiwygDiagnostic[] = [];
    diagnostics.forEach((diagnostic) => {
      const { start, end } = diagnostic;
      if (
        !Number.isInteger(start) ||
        !Number.isInteger(end) ||
        start < 0 ||
        end > context.text.length ||
        start >= end
      ) {
        return;
      }
      mapped.push({
        ...diagnostic,
        from: span.contentStart + start,
        to: span.contentStart + end,
        word: context.text.slice(start, end),
      });
    });
    this.innerView.dispatch(this.innerView.state.tr.setMeta(proofreadingPluginKey, mapped));
    return mapped;
  }

  clearProofreadingDiagnostics(): void {
    this.innerView?.dispatch(this.innerView.state.tr.setMeta(proofreadingPluginKey, []));
  }

  /** The diagnostic under a screen point, for the right-click popover. */
  diagnosticAtPoint(x: number, y: number): WysiwygDiagnostic | null {
    if (!this.innerView) {
      return null;
    }
    try {
      const at = this.innerView.posAtCoords({ left: x, top: y });
      return at ? this.diagnosticAtPos(at.pos) : null;
    } catch {
      return null;
    }
  }

  /** The diagnostic covering a document position, if one does. */
  diagnosticAtPos(pos: number): WysiwygDiagnostic | null {
    if (!this.innerView) {
      return null;
    }
    const diagnostics = proofreadingPluginKey.getState(this.innerView.state)?.diagnostics ?? [];
    return diagnostics.find((diagnostic) => pos >= diagnostic.from && pos <= diagnostic.to) ?? null;
  }

  /** Replace one diagnostic's range with *replacement* in one transaction. */
  applyProofreadingReplacement(
    diagnostic: WysiwygDiagnostic,
    replacement: string,
  ): boolean {
    if (!this.innerView) {
      return false;
    }
    const size = this.innerView.state.doc.content.size;
    if (diagnostic.from < 0 || diagnostic.to > size || diagnostic.from >= diagnostic.to) {
      return false;
    }
    this.innerView.dispatch(
      this.innerView.state.tr.insertText(replacement, diagnostic.from, diagnostic.to),
    );
    return true;
  }

  /** Take the editable away (or give it back) while the panel is busy. */
  setEditable(enabled: boolean): void {
    this.innerView?.setProps({ editable: () => enabled });
  }

  /**
   * The selected text and where it starts and ends: the paragraph ids and
   * indexes it touches, each endpoint's sentence and character offset, and the
   * quote type they share. Empty selection, unmounted view, or a selection that
   * names no paragraph answer null.
   */
  selectionContext(): SelectionContext | null {
    if (!this.innerView) {
      return null;
    }
    const { from, to, empty } = this.innerView.state.selection;
    if (empty) {
      return null;
    }
    const doc = this.innerView.state.doc;
    const spans = paragraphSpans(doc);
    const touched = spans.filter(
      (span) => span.contentEnd > from && span.contentStart < to,
    );
    if (touched.length === 0) {
      return null;
    }
    const startSpan = this.paragraphAt(spans, from) ?? touched[0];
    const endSpan = this.paragraphAt(spans, to) ?? touched[touched.length - 1];
    const quoteTypes = touched.map((span) => span.node.attrs.quoteType ?? "");
    return {
      text: doc.textBetween(from, to, " "),
      paragraphIds: touched.map((span) => span.node.attrs.id ?? null),
      paragraphIndexes: touched.map((span) => span.index),
      quoteType: quoteTypes.every((type) => type === quoteTypes[0]) ? quoteTypes[0] : "",
      start: this.selectionPoint(startSpan, from),
      end: this.selectionPoint(endSpan, to),
    };
  }

  private paragraphAt(spans: ParagraphSpan[], pos: number): ParagraphSpan | null {
    return (
      spans.find((span) => pos >= span.contentStart && pos <= span.contentEnd) ??
      spans.find((span) => span.contentStart > pos) ??
      spans[spans.length - 1] ??
      null
    );
  }

  private selectionPoint(span: ParagraphSpan, pos: number): SelectionPoint {
    const offset = Math.min(Math.max(pos - span.contentStart, 0), span.node.content.size);
    return {
      paragraphId: span.node.attrs.id ?? null,
      paragraphIndex: span.index,
      sentenceIndex: this.sentenceIndexAt(span.node, offset),
      offset,
    };
  }

  private sentenceIndexAt(paragraph: Node, offset: number): number {
    const ranges = this.sentenceRanges(paragraph);
    const index = ranges.findIndex((range) => offset >= range.from && offset <= range.to);
    return index === -1 ? Math.max(ranges.length - 1, 0) : index;
  }

  /**
   * Set the quote type of the paragraphs named by *ids* (falling back to
   * *indexes* when an id is null, as on a paragraph not yet saved), in one
   * transaction. A paragraph that has no id gains one now, because the quote
   * type lives in the canonical span.
   */
  setQuoteTypeByIds(
    ids: Array<string | null>,
    indexes: number[],
    quoteType: string,
  ): boolean {
    if (!this.innerView || ids.length === 0) {
      return false;
    }
    const doc = this.innerView.state.doc;
    const spans = paragraphSpans(doc);
    const targets = new Set<number>();
    ids.forEach((id, index) => {
      const byId = id === null ? undefined : spans.find((span) => span.node.attrs.id === id);
      const indexValue = indexes[index];
      const byIndex =
        typeof indexValue === "number" &&
        Number.isInteger(indexValue) &&
        indexValue >= 0 &&
        indexValue < spans.length
          ? spans[indexValue]
          : undefined;
      const target = byId ?? byIndex;
      if (target) {
        targets.add(target.pos);
      }
    });
    if (targets.size === 0) {
      return false;
    }
    const tr = this.innerView.state.tr;
    targets.forEach((pos) => {
      const node = doc.nodeAt(pos);
      if (!node || node.type.name !== "paragraph") {
        return;
      }
      tr.setNodeMarkup(pos, null, {
        id: node.attrs.id ?? crypto.randomUUID(),
        quoteType,
        blanksBefore: node.attrs.blanksBefore,
      });
    });
    this.innerView.dispatch(tr);
    return true;
  }

  setContent(buffer: string): void {
    const { ids, quoteTypes } = extractSpanAttrs(buffer);
    const display = chapterBody(buffer);
    this.lastFrontMatter = buffer.match(FRONT_MATTER_RE)?.[0] ?? null;
    if (!this.innerView) {
      const state = EditorState.create({
        schema,
        doc: bufferToDocWithIds(display, ids, quoteTypes),
        plugins: [history(), keymap(baseKeymap), keymap({ Enter: splitBlock, "Shift-Enter": insertHardBreak, "Mod-z": undo, "Shift-Mod-z": redo, "Mod-y": redo }), headingDecorations(new MarkdownIt()), proofreadingPlugin()],
      });
      this.innerView = new EditorView(this.element, {
        state,
        attributes: { spellcheck: "false" },
        dispatchTransaction: (tr) => {
          const prevSelection = this.innerView!.state.selection;
          const newState = this.innerView!.state.apply(tr);
          this.innerView!.updateState(newState);
          if (tr.docChanged) {
            this.options.onChange?.(docToString(newState.doc));
          }
          if (!newState.selection.eq(prevSelection)) {
            this.options.onSelectionChange?.();
          }
        },
      });
      this.innerView.dom.setAttribute("lang", this.language);
      return;
    }
    this.innerView.updateState(
      EditorState.create({
        schema,
        doc: bufferToDocWithIds(display, ids, quoteTypes),
        plugins: [history(), keymap(baseKeymap), keymap({ Enter: splitBlock, "Shift-Enter": insertHardBreak, "Mod-z": undo, "Shift-Mod-z": redo, "Mod-y": redo }), headingDecorations(new MarkdownIt()), proofreadingPlugin()],
      }),
    );
  }

  content(): string {
    const body = this.innerView ? docToCanonical(this.innerView.state.doc) : "";
    const frontMatter = this.lastFrontMatter ? this.lastFrontMatter.replace(/\r?\n$/, "") : null;
    return frontMatter === null ? body : frontMatter + "\n\n" + body;
  }

  plainContent(): string {
    return this.innerView ? docToString(this.innerView.state.doc) : "";
  }

  /**
   * The open doc's per-paragraph quote types, in order.
   *
   * `plainContent()` cannot see them — they are node attributes, not text —
   * so the dirty check reads this beside it.
   */
  quoteSignature(): string {
    if (!this.innerView) {
      return "";
    }
    return signatureFromDoc(this.innerView.state.doc);
  }

  /** The position spans of the sentences of one paragraph node, in content coordinates. */
  private sentenceRanges(paragraph: Node): Array<{ from: number; to: number }> {
    const ranges: Array<{ from: number; to: number }> = [];
    let start = 0;
    let pos = 0;
    paragraph.forEach((child) => {
      const childStart = pos;
      pos += child.nodeSize;
      const breaks =
        child.isText &&
        child.text === " " &&
        child.marks.some((mark) => mark.type.name === SENTENCE_BREAK)
          ? true
          : child.type.name === "hardBreak";
      if (breaks) {
        ranges.push({ from: start, to: childStart });
        start = pos;
      }
    });
    ranges.push({ from: start, to: pos });
    return ranges.filter((range) => range.from < range.to);
  }

  /** The text the current selection spans, joined by spaces at paragraph bounds. */
  selectedText(): string {
    if (!this.innerView) {
      return "";
    }
    const { from, to } = this.innerView.state.selection;
    return this.innerView.state.doc.textBetween(from, to, " ");
  }

  /**
   * Select a paragraph's sentences — the whole paragraph with none named — as
   * if the mouse had dragged over them, scrolled into view.
   *
   * The paragraph is found by its id (the one carried in the canonical span);
   * the sentence indexes count the non-empty sentence runs, the same order the
   * wire format's sentences keep. One selection only, so the named sentences
   * become one span over all of them. An index past the paragraph's last
   * sentence selects that last one. Unknown paragraph, unmounted view, or a
   * paragraph with no sentences answer false and leave the selection alone.
   */
  selectSentences(paragraphId: string, sentenceIndexes: number[] | null): boolean {
    if (!this.innerView) {
      return false;
    }
    const doc = this.innerView.state.doc;
    let paragraphPos: number | null = null;
    doc.forEach((node, offset) => {
      if (
        paragraphPos === null &&
        node.type.name === "paragraph" &&
        node.attrs.id === paragraphId
      ) {
        paragraphPos = offset;
      }
    });
    if (paragraphPos === null) {
      return false;
    }
    const paragraph = doc.nodeAt(paragraphPos);
    if (!paragraph) {
      return false;
    }
    const contentStart = paragraphPos + 1;
    let from = contentStart;
    let to = contentStart + paragraph.content.size;
    if (sentenceIndexes !== null && sentenceIndexes.length > 0) {
      const ranges = this.sentenceRanges(paragraph);
      if (ranges.length === 0) {
        return false;
      }
      const clamped = sentenceIndexes.map((index) =>
        ranges[Math.min(Math.max(index, 0), ranges.length - 1)],
      );
      from = contentStart + Math.min(...clamped.map((range) => range.from));
      to = contentStart + Math.max(...clamped.map((range) => range.to));
    }
    const tr = this.innerView.state.tr;
    tr.setSelection(TextSelection.create(doc, Math.min(from, to), Math.max(from, to)));
    this.innerView.dispatch(tr);
    // The selection highlight is drawn while the editor has focus; bring the
    // view back so the rectangle is on the screen the writer is looking at.
    this.innerView.focus();
    // ProseMirror's Own scrollIntoView stops at the nearest edge — the last
    // line when the paragraph hangs below — so the whole paragraph box is
    // scrolled in instead.
    const dom = this.innerView.nodeDOM(paragraphPos) as HTMLElement | null;
    if (dom && typeof dom.scrollIntoView === "function") {
      dom.scrollIntoView({ block: "nearest" });
    }
    return true;
  }

  destroy(): void {
    this.innerView?.destroy();
    this.innerView = null;
    this.element.replaceChildren();
  }
}