import { EditorState, Plugin, PluginKey, TextSelection, type Command } from "prosemirror-state";
import { EditorView, Decoration, DecorationSet } from "prosemirror-view";
import { Schema, type Node } from "prosemirror-model";
import { baseKeymap, splitBlock } from "prosemirror-commands";
import { keymap } from "prosemirror-keymap";
import { history, redo, undo } from "prosemirror-history";
import MarkdownIt from "markdown-it";

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

/** The canonical *buffer*'s per-paragraph quote types, in order — see `WysiwygView.quoteSignature`. */
export function quoteSignatureOf(buffer: string): string {
  return extractSpanAttrs(buffer)
    .quoteTypes.map((quote) => quote ?? "")
    .join("\u241F");
}

/**
 * The one quote type every *types* shares, or null when they disagree.
 *
 * A pulldown can only tick one entry: an empty list counts as `""` (nothing
 * quoted), a disagreement as null (nothing ticked).
 */
export function uniformQuoteType(types: string[]): string | null {
  if (types.length === 0) {
    return "";
  }
  return types.every((type) => type === types[0]) ? types[0] : null;
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

  /** Take the editable away (or give it back) while the panel is busy. */
  setEditable(enabled: boolean): void {
    this.innerView?.setProps({ editable: () => enabled });
  }

  /**
   * The document positions opening each paragraph a right-click acts on.
   *
   * A selection — even one spanning paragraphs — names every paragraph it
   * touches; an empty selection falls back to the paragraph the pointer is on.
   */
  paragraphPositions(target: EventTarget | null): number[] {
    if (!this.innerView) {
      return [];
    }
    const { from, to, empty } = this.innerView.state.selection;
    if (empty) {
      const pos = this.paragraphPosFromDom(target);
      return pos === null ? [] : [pos];
    }
    const positions: number[] = [];
    let offset = 0;
    this.innerView.state.doc.forEach((node, localStart) => {
      const contentStart = offset + 1;
      const contentEnd = offset + node.nodeSize - 1;
      if (contentEnd > from && contentStart < to) {
        positions.push(localStart);
      }
      offset += node.nodeSize;
    });
    return positions;
  }

  /** The quote type of the paragraph at *pos* ("" when it is not a quote). */
  quoteTypeAt(pos: number): string {
    const node = this.view.state.doc.nodeAt(pos);
    return node?.type.name === "paragraph" ? (node.attrs.quoteType ?? "") : "";
  }

  /**
   * Set the quote type of every paragraph at *positions*, in one transaction.
   *
   * A paragraph that has no id yet — brand-new, never saved — gains one now:
   * the quote type lives in the canonical span, so without an id there would
   * be nothing to carry it. One transaction keeps the whole marking one undo
   * step and one save-worthy change.
   */
  setQuoteTypeAtPositions(positions: number[], quoteType: string): boolean {
    if (positions.length === 0) {
      return false;
    }
    const tr = this.view.state.tr;
    for (const pos of positions) {
      const node = this.view.state.doc.nodeAt(pos);
      if (!node || node.type.name !== "paragraph") {
        continue;
      }
      tr.setNodeMarkup(pos, null, {
        id: node.attrs.id ?? crypto.randomUUID(),
        quoteType,
        blanksBefore: node.attrs.blanksBefore,
      });
    }
    this.view.dispatch(tr);
    return true;
  }

  /** The document position that opens the paragraph *target* sits in, if any. */
  private paragraphPosFromDom(target: EventTarget | null): number | null {
    if (!this.innerView || !(target instanceof Element)) {
      return null;
    }
    const dom = target.closest("p");
    if (!dom || !this.innerView.dom.contains(dom)) {
      return null;
    }
    try {
      const pos = this.innerView.posAtDOM(dom, 0);
      const $pos = this.innerView.state.doc.resolve(pos);
      return $pos.depth >= 1 ? $pos.before(1) : null;
    } catch {
      return null;
    }
  }

  setContent(buffer: string): void {
    const { ids, quoteTypes } = extractSpanAttrs(buffer);
    const display = chapterBody(buffer);
    this.lastFrontMatter = buffer.match(FRONT_MATTER_RE)?.[0] ?? null;
    if (!this.innerView) {
      const state = EditorState.create({
        schema,
        doc: bufferToDocWithIds(display, ids, quoteTypes),
        plugins: [history(), keymap(baseKeymap), keymap({ Enter: splitBlock, "Shift-Enter": insertHardBreak, "Mod-z": undo, "Shift-Mod-z": redo, "Mod-y": redo }), headingDecorations(new MarkdownIt())],
      });
      this.innerView = new EditorView(this.element, {
        state,
        dispatchTransaction: (tr) => {
          const newState = this.innerView!.state.apply(tr);
          this.innerView!.updateState(newState);
          if (tr.docChanged) {
            this.options.onChange?.(docToString(newState.doc));
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
        plugins: [history(), keymap(baseKeymap), keymap({ Enter: splitBlock, "Shift-Enter": insertHardBreak, "Mod-z": undo, "Shift-Mod-z": redo, "Mod-y": redo }), headingDecorations(new MarkdownIt())],
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
    const types: string[] = [];
    this.innerView.state.doc.forEach((paragraph) => types.push(paragraph.attrs.quoteType ?? ""));
    return types.join("\u241F");
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
   * Select a paragraph's sentence — the whole paragraph without an index — as
   * if the mouse had dragged over it, scrolled into view.
   *
   * The paragraph is found by its id (the one carried in the canonical span);
   * the sentence index counts the non-empty sentence runs, the same order the
   * wire format's sentences keep. An index past the paragraph's last sentence
   * selects that last one. Unknown paragraph, unmounted view, or a paragraph
   * with no sentences answer false and leave the selection alone.
   */
  selectSentence(paragraphId: string, sentenceIndex: number | null): boolean {
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
    if (sentenceIndex !== null) {
      const ranges = this.sentenceRanges(paragraph);
      if (ranges.length === 0) {
        return false;
      }
      const clamped = Math.min(Math.max(sentenceIndex, 0), ranges.length - 1);
      from = contentStart + ranges[clamped].from;
      to = contentStart + ranges[clamped].to;
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