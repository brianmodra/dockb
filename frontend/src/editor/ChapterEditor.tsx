import { useEditor, EditorContent } from '@tiptap/react'
import StarterKit from '@tiptap/starter-kit'
import Placeholder from '@tiptap/extension-placeholder'
import { useEffect, useRef } from 'react'
import { combineTransactionSteps } from '@tiptap/core'
import type { ChapterNode } from '@/types'
import type { SentenceChange } from './extractChanges'
import { extractChanges } from './extractChanges'
import { Chapter, Paragraph, Sentence } from './extensions'

interface ChapterEditorProps {
  chapter: ChapterNode
  onChange: (changes: SentenceChange[]) => void
  knownIds?: Set<string>
  createdIdsRef?: React.RefObject<Set<string>>
}

export function ChapterEditor({ chapter, onChange, knownIds, createdIdsRef }: ChapterEditorProps) {
  const onChangeRef = useRef(onChange)
  onChangeRef.current = onChange
  const knownIdsRef = useRef(knownIds)
  knownIdsRef.current = knownIds
  const createdIdsRefInternal = useRef(createdIdsRef)
  createdIdsRefInternal.current = createdIdsRef

  const getKnownIds = useRef(() => {
    const base = knownIdsRef.current
    const created = createdIdsRefInternal.current?.current
    if (!base && !created) return undefined
    if (!created) return base
    if (!base) return created
    const merged = new Set(base)
    for (const id of created) merged.add(id)
    return merged
  })
  const seededContentRef = useRef<Map<string, ChapterNode>>(new Map())

  let content: ChapterNode
  if (chapter.content && chapter.content.length > 0) {
    seededContentRef.current.delete(chapter.attrs.id)
    content = chapter
  } else {
    const cached = seededContentRef.current.get(chapter.attrs.id)
    if (cached) {
      content = cached
    } else {
      content = {
        ...chapter,
        content: [
          {
            type: 'paragraph' as const,
            attrs: { id: crypto.randomUUID() },
            content: [
              {
                type: 'sentence' as const,
                attrs: { id: crypto.randomUUID() },
                content: [],
              },
            ],
          },
        ],
      }
      seededContentRef.current.set(chapter.attrs.id, content)
    }
  }

  const editor = useEditor({
    extensions: [
      StarterKit.configure({
        heading: false,
        paragraph: false,
      }),
      Chapter,
      Paragraph,
      Sentence,
      Placeholder.configure({
        placeholder: 'Start writing...',
      }),
    ],
    content,
    onTransaction: ({ transaction }) => {
      if (!transaction.docChanged) return
      const transform = combineTransactionSteps(
        transaction.before,
        [transaction],
      )
      const changes = extractChanges(
        transform,
        transaction.before,
        transaction.doc,
        getKnownIds.current(),
      )
      if (changes.length > 0) {
        onChangeRef.current(changes)
      }
    },
  }, [chapter])

  useEffect(() => {
    if (editor && chapter) {
      const normalized = seededContentRef.current.get(chapter.attrs.id) || chapter
      const current = editor.getJSON()
      if (JSON.stringify(current) !== JSON.stringify(normalized)) {
        editor.commands.setContent(normalized)
      }
    }
  }, [chapter, editor])

  return (
    <div className="chapter-editor">
      <h2>{chapter.attrs.title}</h2>
      <EditorContent editor={editor} />
    </div>
  )
}
