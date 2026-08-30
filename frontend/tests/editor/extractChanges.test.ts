import { describe, it, expect } from 'vitest'
import { Schema } from 'prosemirror-model'
import { Transform } from 'prosemirror-transform'
import { extractChanges } from '../../src/editor/extractChanges'

const testSchema = new Schema({
  topNode: 'chapter',
  nodes: {
    chapter: {
      content: 'paragraph*',
      attrs: { id: { default: null }, title: { default: null } },
    },
    paragraph: {
      content: 'sentence*',
      attrs: { id: { default: null } },
    },
    sentence: {
      content: 'text*',
      attrs: { id: { default: null } },
    },
    text: { inline: true },
  },
})

function makeChapter(paragraphs: { id: string; sentences: { id: string; text: string }[] }[]) {
  return testSchema.node(
    'chapter',
    { id: 'ch-1', title: 'Test' },
    paragraphs.map((p) =>
      testSchema.node(
        'paragraph',
        { id: p.id },
        p.sentences.map((s) =>
          testSchema.node(
            'sentence',
            { id: s.id },
            s.text ? [testSchema.text(s.text)] : [],
          ),
        ),
      ),
    ),
  )
}

function replaceText(
  ctx: { doc: ReturnType<typeof makeChapter>; pos: (id: string) => number },
  sentenceId: string,
  fromOffset: number,
  toOffset: number,
  newText: string,
) {
  const tr = new Transform(ctx.doc)
  const from = ctx.pos(sentenceId) + fromOffset
  const to = from + (toOffset - fromOffset)
  if (newText.length > 0) {
    tr.replaceWith(from, to, testSchema.text(newText))
  } else {
    tr.delete(from, to)
  }
  return tr
}

function docWithPositions(chapterNode: ReturnType<typeof makeChapter>) {
  return {
    doc: chapterNode,
    pos(sentenceId: string): number {
      let found = -1
      chapterNode.descendants((node, pos) => {
        if (node.type.name === 'sentence' && node.attrs.id === sentenceId) {
          found = pos + 1
          return false
        }
        return undefined
      })
      return found
    },
  }
}

function makeDocWithSentences(
  paragraphs: { id: string; sentences: { id: string; text: string }[] }[],
) {
  return testSchema.node(
    'chapter',
    { id: 'ch-1', title: 'Test' },
    paragraphs.map((p) =>
      testSchema.node(
        'paragraph',
        { id: p.id },
        p.sentences.map((s) =>
          testSchema.node(
            'sentence',
            { id: s.id },
            s.text ? [testSchema.text(s.text)] : [],
          ),
        ),
      ),
    ),
  )
}

function nodePos(doc: ReturnType<typeof makeChapter>, sentenceId: string): number {
  let found = -1
  doc.descendants((node, pos) => {
    if (node.type.name === 'sentence' && node.attrs.id === sentenceId) {
      found = pos
      return false
    }
    return undefined
  })
  return found
}

function mergeSentences(
  ctx: { doc: ReturnType<typeof makeChapter> },
  keepId: string,
  absorbId: string,
) {
  const tr = new Transform(ctx.doc)
  const keepPos = nodePos(ctx.doc, keepId)
  const absorbPos = nodePos(ctx.doc, absorbId)
  const absorbNode = ctx.doc.resolve(absorbPos).nodeAfter!
  const keepNode = ctx.doc.resolve(keepPos).nodeAfter!
  const mergedText = keepNode.textContent + absorbNode.textContent
  const mergedSentence = testSchema.node('sentence', { id: keepId }, [
    testSchema.text(mergedText),
  ])
  tr.replaceWith(keepPos, absorbPos + absorbNode.nodeSize, mergedSentence)
  return tr
}

describe('extractChanges', () => {
  it('returns empty when nothing changed', () => {
    const doc = makeChapter([
      { id: 'p-1', sentences: [{ id: 's-1', text: 'Hello world.' }] },
    ])
    const tr = new Transform(doc)
    const changes = extractChanges(tr, doc, doc)
    expect(changes).toEqual([])
  })

  it('returns update when text changes in a sentence', () => {
    const oldDoc = makeChapter([
      { id: 'p-1', sentences: [{ id: 's-1', text: 'Hello world.' }] },
    ])
    const ctx = docWithPositions(oldDoc)
    const tr = replaceText(ctx, 's-1', 6, 11, 'there')
    const newDoc = tr.doc

    const changes = extractChanges(tr, oldDoc, newDoc)
    expect(changes).toEqual([
      {
        type: 'update',
        id: 's-1',
        content: [{ type: 'text', text: 'Hello there.' }],
      },
    ])
  })

  it('returns update for correct sentence when chapter has multiple', () => {
    const oldDoc = makeChapter([
      {
        id: 'p-1',
        sentences: [
          { id: 's-1', text: 'First sentence.' },
          { id: 's-2', text: 'Second sentence.' },
        ],
      },
    ])
    const ctx = docWithPositions(oldDoc)
    const tr = replaceText(ctx, 's-2', 7, 15, 'paragraph')
    const newDoc = tr.doc

    const changes = extractChanges(tr, oldDoc, newDoc)
    expect(changes).toEqual([
      {
        type: 'update',
        id: 's-2',
        content: [{ type: 'text', text: 'Second paragraph.' }],
      },
    ])
  })

  it('returns updates for sentences in different paragraphs', () => {
    const oldDoc = makeChapter([
      { id: 'p-1', sentences: [{ id: 's-1', text: 'Hello.' }] },
      { id: 'p-2', sentences: [{ id: 's-2', text: 'World.' }] },
    ])
    const ctx = docWithPositions(oldDoc)
    const tr = replaceText(ctx, 's-1', 0, 5, 'Goodbye')
    const newDoc = tr.doc

    const changes = extractChanges(tr, oldDoc, newDoc)
    expect(changes).toEqual([
      {
        type: 'update',
        id: 's-1',
        content: [{ type: 'text', text: 'Goodbye.' }],
      },
    ])
  })

  it('handles inserting text at start of sentence', () => {
    const oldDoc = makeChapter([
      { id: 'p-1', sentences: [{ id: 's-1', text: 'Hello.' }] },
    ])
    const ctx = docWithPositions(oldDoc)
    const tr = replaceText(ctx, 's-1', 0, 0, 'Say ')
    const newDoc = tr.doc

    const changes = extractChanges(tr, oldDoc, newDoc)
    expect(changes).toEqual([
      {
        type: 'update',
        id: 's-1',
        content: [{ type: 'text', text: 'Say Hello.' }],
      },
    ])
  })

  it('handles appending text at end of sentence', () => {
    const oldDoc = makeChapter([
      { id: 'p-1', sentences: [{ id: 's-1', text: 'Hello.' }] },
    ])
    const ctx = docWithPositions(oldDoc)
    const tr = replaceText(ctx, 's-1', 6, 6, ' Goodbye')
    const newDoc = tr.doc

    const changes = extractChanges(tr, oldDoc, newDoc)
    expect(changes).toEqual([
      {
        type: 'update',
        id: 's-1',
        content: [{ type: 'text', text: 'Hello. Goodbye' }],
      },
    ])
  })

  it('returns update for original sentence and create for new sentence on split', () => {
    const oldDoc = makeChapter([
      { id: 'p-1', sentences: [{ id: 's-1', text: 'Hello world.' }] },
    ])
    const newDoc = makeDocWithSentences([
      {
        id: 'p-1',
        sentences: [
          { id: 's-1', text: 'Hello ' },
          { id: 's-2', text: 'world.' },
        ],
      },
    ])
    const tr = new Transform(oldDoc)

    const changes = extractChanges(tr, oldDoc, newDoc)

    const update = changes.find(
      (c) => c.type === 'update' && c.id === 's-1',
    )
    expect(update).toBeDefined()
    expect(update!.type).toBe('update')

    const create = changes.find((c) => c.type === 'create')
    expect(create).toBeDefined()
    expect(create!.type).toBe('create')
    expect((create as { type: 'create'; id: string }).id).toBe('s-2')
  })

  it('returns update for surviving sentence and delete for absorbed sentence on merge', () => {
    const oldDoc = makeChapter([
      {
        id: 'p-1',
        sentences: [
          { id: 's-1', text: 'Hello.' },
          { id: 's-2', text: 'World.' },
        ],
      },
    ])
    const ctx = docWithPositions(oldDoc)
    const tr = mergeSentences(ctx, 's-1', 's-2')
    const newDoc = tr.doc

    const changes = extractChanges(tr, oldDoc, newDoc)

    const deletes = changes.filter((c) => c.type === 'delete')
    expect(deletes.length).toBeGreaterThanOrEqual(1)
  })

  it('handles typing a character within a sentence', () => {
    const oldDoc = makeChapter([
      { id: 'p-1', sentences: [{ id: 's-1', text: 'Hello.' }] },
    ])
    const ctx = docWithPositions(oldDoc)
    const tr = replaceText(ctx, 's-1', 5, 5, '!')
    const newDoc = tr.doc

    const changes = extractChanges(tr, oldDoc, newDoc)
    expect(changes).toEqual([
      {
        type: 'update',
        id: 's-1',
        content: [{ type: 'text', text: 'Hello!.' }],
      },
    ])
  })

  it('handles deleting a character within a sentence', () => {
    const oldDoc = makeChapter([
      { id: 'p-1', sentences: [{ id: 's-1', text: 'Hello.' }] },
    ])
    const ctx = docWithPositions(oldDoc)
    const tr = replaceText(ctx, 's-1', 4, 5, '')
    const newDoc = tr.doc

    const changes = extractChanges(tr, oldDoc, newDoc)
    expect(changes).toEqual([
      {
        type: 'update',
        id: 's-1',
        content: [{ type: 'text', text: 'Hell.' }],
      },
    ])
  })

  it('emits create instead of update when knownIds excludes the sentence', () => {
    const oldDoc = makeChapter([
      { id: 'p-1', sentences: [{ id: 's-1', text: 'Hello.' }] },
    ])
    const ctx = docWithPositions(oldDoc)
    const tr = replaceText(ctx, 's-1', 5, 5, '!')
    const newDoc = tr.doc

    const changes = extractChanges(tr, oldDoc, newDoc, new Set())
    expect(changes).toEqual([
      {
        type: 'create',
        id: 's-1',
        paragraphId: 'p-1',
        content: [{ type: 'text', text: 'Hello!.' }],
      },
    ])
  })

  it('emits update when knownIds includes the sentence', () => {
    const oldDoc = makeChapter([
      { id: 'p-1', sentences: [{ id: 's-1', text: 'Hello.' }] },
    ])
    const ctx = docWithPositions(oldDoc)
    const tr = replaceText(ctx, 's-1', 5, 5, '!')
    const newDoc = tr.doc

    const changes = extractChanges(tr, oldDoc, newDoc, new Set(['s-1']))
    expect(changes).toEqual([
      {
        type: 'update',
        id: 's-1',
        content: [{ type: 'text', text: 'Hello!.' }],
      },
    ])
  })
})
