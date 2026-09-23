import { EditorState, Plugin, PluginKey } from "prosemirror-state";
import { EditorView, Decoration, DecorationSet } from "prosemirror-view";
import { Schema } from "prosemirror-model";
import { baseKeymap } from "prosemirror-commands";
import { keymap } from "prosemirror-keymap";
import MarkdownIt from "markdown-it";

const schema = new Schema({
  nodes: {
    doc: { content: "paragraph+" },
    paragraph: { content: "text*", toDOM: () => ["p", 0] },
    text: { group: "inline" },
  },
});

export function bufferToDoc(buffer: string) {
  const paragraphs = buffer
    .split("\n")
    .map((line) =>
      schema.node("paragraph", {}, line.length > 0 ? [schema.text(line)] : []),
    );
  return schema.node("doc", {}, paragraphs);
}

export function docToString(doc: {
  forEach: (fn: (n: { textContent: string }) => void) => void;
}): string {
  const lines: string[] = [];
  doc.forEach((node) => lines.push(node.textContent));
  return lines.join("\n");
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
  const compute = (doc: {
    forEach: (
      fn: (node: { textContent: string; nodeSize: number }, offset: number) => void,
    ) => void;
  }) => {
    const lines: string[] = [];
    doc.forEach((node) => lines.push(node.textContent));
    const headings = findHeadingLines(lines.join("\n"), md);
    const decorations: Decoration[] = [];
    let line = 0;
    doc.forEach((node, offset) => {
      if (headings.has(line)) {
        decorations.push(
          Decoration.node(offset, offset + node.nodeSize, { class: "prose-heading" }),
        );
      }
      line += 1;
    });
    return DecorationSet.create(doc as never, decorations);
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
    if (!this.innerView) {
      const state = EditorState.create({
        schema,
        doc: bufferToDoc(buffer),
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
        doc: bufferToDoc(buffer),
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