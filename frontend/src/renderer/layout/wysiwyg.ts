import { EditorState, Plugin, PluginKey } from "prosemirror-state";
import { EditorView, Decoration, DecorationSet } from "prosemirror-view";
import { Schema, type Node } from "prosemirror-model";
import { baseKeymap } from "prosemirror-commands";
import { keymap } from "prosemirror-keymap";
import MarkdownIt from "markdown-it";

const schema = new Schema({
  nodes: {
    doc: { content: "paragraph+" },
    paragraph: {
      content: "inline*",
      attrs: { blanksBefore: { default: 0 } },
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
  const blocks = parseBodyBlocks(body);
  const paragraphs =
    blocks.length > 0
      ? blocks.map((block) =>
          schema.node("paragraph", { blanksBefore: block.blanksBefore }, paragraphContent(block)),
        )
      : [schema.node("paragraph", { blanksBefore: 0 })];
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
    let newlines = "\n".repeat(blanks);
    if (!isFirst && paragraph.childCount > 0) {
      newlines += "\n";
    }
    parts.push(newlines + serializeParagraph(paragraph));
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

  constructor(options: WysiwygViewOptions = {}) {
    this.options = options;
    this.element = document.createElement("div");
    this.element.dataset.testid = "wysiwyg-view";
  }

  get view(): EditorView {
    if (!this.innerView) {
      throw new Error("WysiwygView is not mounted");
    }
    return this.innerView;
  }

  setContent(buffer: string): void {
    const display = chapterBody(buffer);
    if (!this.innerView) {
      const state = EditorState.create({
        schema,
        doc: bufferToDoc(display),
        plugins: [keymap(baseKeymap), headingDecorations(new MarkdownIt())],
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
      return;
    }
    this.innerView.updateState(
      EditorState.create({
        schema,
        doc: bufferToDoc(display),
        plugins: [keymap(baseKeymap), headingDecorations(new MarkdownIt())],
      }),
    );
  }

  content(): string {
    return this.innerView ? docToString(this.innerView.state.doc) : "";
  }

  destroy(): void {
    this.innerView?.destroy();
    this.innerView = null;
    this.element.replaceChildren();
  }
}