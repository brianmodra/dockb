import type { Transform } from 'prosemirror-transform'
import type { Node as ProseMirrorNode } from 'prosemirror-model'
import type { TextNode } from '@/types'

export type SentenceChange =
  | { type: 'update'; id: string; content: TextNode[] }
  | {
      type: 'create'
      id: string
      paragraphId: string
      afterSentenceId?: string
      content: TextNode[]
    }
  | { type: 'delete'; id: string }

function sentenceContent(node: ProseMirrorNode): TextNode[] {
  const textContent: TextNode[] = []
  node.forEach((child) => {
    if (child.isText) {
      textContent.push({ type: 'text', text: child.text || '' })
    }
  })
  return textContent
}

function collectSentences(
  doc: ProseMirrorNode,
): Map<string, { node: ProseMirrorNode; paragraphId: string; afterSentenceId?: string }> {
  const map = new Map()
  doc.descendants((paragraph) => {
    if (paragraph.type.name !== 'paragraph') return undefined
    let prevId: string | undefined
    paragraph.forEach((child) => {
      if (child.type.name === 'sentence') {
        map.set(child.attrs.id, {
          node: child,
          paragraphId: paragraph.attrs.id,
          afterSentenceId: prevId,
        })
        prevId = child.attrs.id
      }
    })
    return false
  })
  return map
}

function textNodesEqual(a: ProseMirrorNode, b: ProseMirrorNode): boolean {
  const aText: string[] = []
  const bText: string[] = []
  a.forEach((child) => {
    if (child.isText) aText.push(child.text || '')
  })
  b.forEach((child) => {
    if (child.isText) bText.push(child.text || '')
  })
  return aText.join('') === bText.join('')
}

export function extractChanges(
  _transform: Transform,
  oldDoc: ProseMirrorNode,
  newDoc: ProseMirrorNode,
  knownIds?: Set<string>,
): SentenceChange[] {
  const oldSentences = collectSentences(oldDoc)
  const newSentences = collectSentences(newDoc)
  const changes: SentenceChange[] = []

  for (const [id, entry] of newSentences) {
    if (!oldSentences.has(id)) {
      changes.push({
        type: 'create',
        id,
        paragraphId: entry.paragraphId,
        afterSentenceId: entry.afterSentenceId,
        content: sentenceContent(entry.node),
      })
    } else if (knownIds && !knownIds.has(id)) {
      changes.push({
        type: 'create',
        id,
        paragraphId: entry.paragraphId,
        afterSentenceId: entry.afterSentenceId,
        content: sentenceContent(entry.node),
      })
    } else if (!textNodesEqual(entry.node, oldSentences.get(id)!.node)) {
      changes.push({
        type: 'update',
        id,
        content: sentenceContent(entry.node),
      })
    }
  }

  for (const [id] of oldSentences) {
    if (!newSentences.has(id)) {
      changes.push({ type: 'delete', id })
    }
  }

  return changes
}
