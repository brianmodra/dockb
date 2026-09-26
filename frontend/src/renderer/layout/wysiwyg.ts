import { EditorState, Plugin, PluginKey, type Command } from "prosemirror-state";
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
      attrs: { blanksBefore: { default: 0 }, id: { default: null } },
      toDOM: () => ["p", 0],
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

function extractSpanIds(buffer: string): Array<string | null> {
  const hadFrontMatter = FRONT_MATTER_RE.test(buffer);
  const withoutFrontMatter = buffer.replace(FRONT_MATTER_RE, "");
  const body = hadFrontMatter ? withoutFrontMatter.replace(/^\n/, "") : withoutFrontMatter;
  return body.split("\n\n").map((block) => {
    const open = block.match(/<span\b([^>]*)>/);
    if (!open) {
      return null;
    }
    const attr = open[1].match(/\bdata-par-id="([^"]*)"/);
    return attr ? unescapeHtml(attr[1]) : null;
  });
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

export function bufferToDocWithIds(body: string, ids: Array<string | null>) {
  const blocks = parseBodyBlocks(body);
  const paragraphs =
    blocks.length > 0
      ? blocks.map((block, index) =>
          schema.node(
            "paragraph",
            { blanksBefore: block.blanksBefore, id: ids[index] ?? null },
            paragraphContent(block),
          ),
        )
      : [schema.node("paragraph", { blanksBefore: 0, id: null })];
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
    const body =
      id !== null
        ? `<span data-par-id="${escapeHtml(id)}">\n${escapeHtml(lines)}\n</span>`
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

  setContent(buffer: string): void {
    const ids = extractSpanIds(buffer);
    const display = chapterBody(buffer);
    this.lastFrontMatter = buffer.match(FRONT_MATTER_RE)?.[0] ?? null;
    if (!this.innerView) {
      const state = EditorState.create({
        schema,
        doc: bufferToDocWithIds(display, ids),
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
        doc: bufferToDocWithIds(display, ids),
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

  destroy(): void {
    this.innerView?.destroy();
    this.innerView = null;
    this.element.replaceChildren();
  }
}