import { useState, useEffect, useCallback, useMemo, useRef } from 'react'
import { api } from '@/api/client'
import { ChapterEditor } from '@/editor/ChapterEditor'
import type { SentenceChange } from '@/editor/extractChanges'
import type { Document, ChapterNode, ChapterSummary } from '@/types'

interface ChapterViewProps {
  document: Document
  onBack: () => void
}

export function ChapterView({ document, onBack }: ChapterViewProps) {
  const [chapters, setChapters] = useState<ChapterSummary[]>([])
  const [selectedChapter, setSelectedChapter] = useState<ChapterNode | null>(
    null
  )
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [showForm, setShowForm] = useState(false)
  const [chapterTitle, setChapterTitle] = useState('')

  const fetchChapters = useCallback(() =>
    api.chapters
      .list(document.attrs.id)
      .then((list) =>
        setChapters(
          list.map((c) => ({ id: c.id, title: c.title }))
        )
      )
      .catch((err) => setError(err.message)),
    [document.attrs.id]
  )

  useEffect(() => {
    fetchChapters()
  }, [fetchChapters])

  const loadChapter = async (chapterId: string) => {
    setLoading(true)
    setError(null)
    try {
      const chapter = await api.chapters.get(chapterId)
      setSelectedChapter(chapter)
      createdIdsRef.current = new Set()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load chapter')
    } finally {
      setLoading(false)
    }
  }

  const knownSentenceIds = useMemo(() => {
    if (!selectedChapter) return undefined
    const ids = new Set<string>()
    selectedChapter.content?.forEach((paragraph) => {
      paragraph.content?.forEach((sentence) => {
        if (sentence.attrs.id) ids.add(sentence.attrs.id)
      })
    })
    return ids
  }, [selectedChapter])

  const createdIdsRef = useRef(new Set<string>())

  const handleSentenceChanges = async (changes: SentenceChange[]) => {
    try {
      for (const change of changes) {
        if (change.type === 'update') {
          await api.sentences.update(change.id, { content: change.content })
        } else if (change.type === 'create') {
          await api.sentences.create({
            attrs: { id: change.id },
            content: change.content,
            relations: {
              paragraph_id: change.paragraphId,
              after_sentence_id: change.afterSentenceId,
            },
          })
          createdIdsRef.current.add(change.id)
        } else if (change.type === 'delete') {
          await api.sentences.delete(change.id)
          createdIdsRef.current.delete(change.id)
        }
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save')
    }
  }

  const handleCreateChapter = async () => {
    try {
      setError(null)
      const newId = crypto.randomUUID()
      await api.chapters.create({
        attrs: { id: newId, title: chapterTitle },
        relations: { document_id: document.attrs.id },
      })
      setShowForm(false)
      setChapterTitle('')
      await fetchChapters()
      await loadChapter(newId)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create chapter')
    }
  }

  const handleCancel = () => {
    setShowForm(false)
    setChapterTitle('')
    setError(null)
  }

  return (
    <div className="chapter-view">
      <div className="chapter-sidebar">
        <button onClick={onBack}>← Back</button>
        <h3>{document.attrs.title}</h3>
        {showForm ? (
          <div className="create-form">
            <div>
              <label htmlFor="chapter-title">Chapter Title</label>
              <input
                id="chapter-title"
                value={chapterTitle}
                onChange={(e) => setChapterTitle(e.target.value)}
              />
            </div>
            <button onClick={handleCreateChapter}>Create</button>
            <button onClick={handleCancel}>Cancel</button>
          </div>
        ) : (
          <>
            <button onClick={() => setShowForm(true)}>New Chapter</button>
            <ul>
              {chapters.map((ch) => (
                <li key={ch.id}>
                  <button
                    onClick={() => loadChapter(ch.id)}
                    className={
                      selectedChapter?.attrs.id === ch.id ? 'active' : ''
                    }
                  >
                    {ch.title}
                  </button>
                </li>
              ))}
            </ul>
          </>
        )}
      </div>
      <div className="chapter-content">
        {loading && <div>Loading chapter...</div>}
        {error && <div className="error">{error}</div>}
        {selectedChapter && (
          <ChapterEditor
            chapter={selectedChapter}
            onChange={handleSentenceChanges}
            knownIds={knownSentenceIds}
            createdIdsRef={createdIdsRef}
          />
        )}
      </div>
    </div>
  )
}
