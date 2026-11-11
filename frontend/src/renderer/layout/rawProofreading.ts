import type { ProofreadingDiagnostic } from "../api/types";
import { unescapeHtml, type ProofreadingParagraph, type WysiwygDiagnostic } from "./wysiwyg";

const FRONT_MATTER_RE = /^---\r?\n[\s\S]*?\r?\n---(?:\r?\n|$)/;
const PURE_SPAN_LINE_RE = /^\s*<\/?span(\s[^>]*)?>\s*$/;
const SPAN_TAG_RE = /<\/?span(\s[^>]*)?>/g;
const ENTITIES: Record<string, string> = {
  "&amp;": "&",
  "&lt;": "<",
  "&gt;": ">",
  "&quot;": '"',
  "&#x27;": "'",
  "&#39;": "'",
};

interface RawLine {
  start: number;
  end: number;
  text: string;
}

interface RawBlock {
  index: number;
  lines: RawLine[];
  start: number;
  end: number;
}

interface DisplayLine {
  textStart: number;
  textEnd: number;
  rawStart: number;
  rawEnd: number;
}

export interface RawProofreadingParagraph {
  context: ProofreadingParagraph;
  starts: number[];
  ends: number[];
}

/** The canonical paragraph at *head*: span markup and front matter stripped. */
export function rawProofreadingParagraphAt(
  buffer: string,
  head: number,
): RawProofreadingParagraph | null {
  const blocks = parseBlocks(buffer);
  const block = blocks.find((candidate) => head >= candidate.start && head <= candidate.end);
  return block ? buildParagraph(block, head) : null;
}

/** The writer-facing text of a raw buffer slice: span tags stripped, entities decoded. */
export function rawProofreadingText(slice: string): string {
  return unescapeHtml(slice.replace(SPAN_TAG_RE, ""));
}

/** Rebuild the mapping for a context captured before the check ran. */
export function rawProofreadingParagraphFor(
  buffer: string,
  context: ProofreadingParagraph,
): RawProofreadingParagraph | null {
  const block = parseBlocks(buffer).find(
    (candidate) =>
      candidate.index === context.paragraphIndex && candidate.start === context.contentStart,
  );
  if (!block) {
    return null;
  }
  const paragraph = buildParagraph(block, block.start);
  return paragraph.context.text === context.text ? paragraph : null;
}

/** Map paragraph-relative diagnostics onto CodeMirror offsets. */
export function mapRawProofreadingDiagnostics(
  paragraph: RawProofreadingParagraph,
  diagnostics: ProofreadingDiagnostic[],
): WysiwygDiagnostic[] {
  const { context, starts, ends } = paragraph;
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
      from: starts[start],
      to: ends[end - 1],
      word: context.text.slice(start, end),
      pair: mapRawQuotePair(diagnostic, starts, ends, context.text.length),
    });
  });
  return mapped;
}

function mapRawQuotePair(
  diagnostic: ProofreadingDiagnostic,
  starts: number[],
  ends: number[],
  textLength: number,
): WysiwygDiagnostic["pair"] {
  const pair = diagnostic.pair;
  if (!pair) {
    return undefined;
  }
  const { partner_start, partner_end } = pair;
  if (
    !Number.isInteger(partner_start) ||
    !Number.isInteger(partner_end) ||
    partner_start < 0 ||
    partner_end > textLength ||
    partner_start >= partner_end
  ) {
    return undefined;
  }
  return {
    replacement: pair.replacement,
    from: starts[partner_start],
    to: ends[partner_end - 1],
    partnerReplacement: pair.partner_replacement,
  };
}

function parseBlocks(buffer: string): RawBlock[] {
  const frontMatter = buffer.match(FRONT_MATTER_RE);
  let bodyStart = frontMatter ? frontMatter[0].length : 0;
  if (frontMatter && buffer[bodyStart] === "\n") {
    bodyStart += 1;
  }
  const body = buffer.slice(bodyStart);
  const lines: RawLine[] = [];
  let offset = bodyStart;
  for (const text of body.split("\n")) {
    lines.push({ start: offset, end: offset + text.length, text });
    offset += text.length + 1;
  }

  const blocks: RawBlock[] = [];
  let pendingBlanks = 0;
  let current: RawLine[] | null = null;
  const push = (blockLines: RawLine[]): void => {
    blocks.push({
      index: blocks.length,
      lines: blockLines,
      start: blockLines.length > 0 ? blockLines[0].start : bodyStart + body.length,
      end: blockLines.length > 0 ? blockLines[blockLines.length - 1].end : bodyStart + body.length,
    });
  };
  for (const line of lines) {
    if (line.text === "") {
      pendingBlanks += 1;
      if (current) {
        push(current);
        current = null;
      }
    } else if (current) {
      current.push(line);
    } else {
      current = [line];
      pendingBlanks = 0;
    }
  }
  if (current) {
    push(current);
  } else if (pendingBlanks > 0) {
    push([]);
  }
  return blocks;
}

function buildParagraph(block: RawBlock, head: number): RawProofreadingParagraph {
  const starts: number[] = [];
  const ends: number[] = [];
  const displayLines: DisplayLine[] = [];
  let text = "";
  let paragraphId: string | null = null;
  let previous: RawLine | null = null;

  block.lines.forEach((line) => {
    if (PURE_SPAN_LINE_RE.test(line.text)) {
      if (paragraphId === null) {
        const id = line.text.match(/\bdata-par-id="([^"]*)"/);
        paragraphId = id ? unescapeHtml(id[1]) : null;
      }
      return;
    }
    if (previous) {
      const newline = previous.end;
      starts.push(newline);
      ends.push(newline + 1);
      text += "\n";
    }
    const textStart = text.length;
    appendDecodedLine(line, (char, start, end) => {
      text += char;
      starts.push(start);
      ends.push(end);
    });
    displayLines.push({
      textStart,
      textEnd: text.length,
      rawStart: line.start,
      rawEnd: line.end,
    });
    previous = line;
  });

  const focus = focusLine(displayLines, head);
  return {
    context: {
      paragraphId,
      paragraphIndex: block.index,
      text,
      focus: focus ? { start: focus.textStart, end: focus.textEnd } : null,
      contentStart: block.start,
      contentEnd: block.end,
    },
    starts,
    ends,
  };
}

function appendDecodedLine(
  line: RawLine,
  append: (char: string, start: number, end: number) => void,
): void {
  let index = 0;
  while (index < line.text.length) {
    const tag = line.text.slice(index).match(/^<\/?span(\s[^>]*)?>/);
    if (tag) {
      index += tag[0].length;
      continue;
    }
    const char = line.text[index];
    if (char === "&") {
      const match = line.text.slice(index).match(/^&(amp|lt|gt|quot|#x27|#39);/);
      if (match) {
        append(ENTITIES[match[0]] ?? match[0], line.start + index, line.start + index + match[0].length);
        index += match[0].length;
        continue;
      }
    }
    append(char, line.start + index, line.start + index + 1);
    index += 1;
  }
}

function focusLine(displayLines: DisplayLine[], head: number): DisplayLine | null {
  if (displayLines.length === 0) {
    return null;
  }
  const containing = displayLines.find((line) => head >= line.rawStart && head <= line.rawEnd);
  if (containing) {
    return containing;
  }
  return displayLines.find((line) => head < line.rawStart) ?? displayLines[displayLines.length - 1] ?? null;
}
