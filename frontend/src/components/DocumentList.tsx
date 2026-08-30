import { useState, useEffect } from 'react'
import { api } from '@/api/client'
import type { Document } from '@/types'

interface DocumentListProps {
  onSelect: (doc: Document) => void
}

export function DocumentList({ onSelect }: DocumentListProps) {
  const [documents, setDocuments] = useState<Document[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [showForm, setShowForm] = useState(false)
  const [title, setTitle] = useState('')
  const [author, setAuthor] = useState('')

  const fetchDocuments = () =>
    api.documents
      .list()
      .then(setDocuments)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false))

  useEffect(() => {
    fetchDocuments()
  }, [])

  const handleCreate = async () => {
    try {
      setError(null)
      await api.documents.create({
        attrs: { id: crypto.randomUUID(), title, author },
      })
      setShowForm(false)
      setTitle('')
      setAuthor('')
      setLoading(true)
      await fetchDocuments()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create document')
    }
  }

  const handleCancel = () => {
    setShowForm(false)
    setTitle('')
    setAuthor('')
    setError(null)
  }

  const handleDelete = async (id: string) => {
    try {
      setError(null)
      await api.documents.delete(id)
      setLoading(true)
      await fetchDocuments()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete document')
    }
  }

  if (loading) return <div>Loading documents...</div>
  if (error && !showForm) return <div className="error">{error}</div>

  return (
    <div className="document-list">
      <h2>Documents</h2>
      {showForm ? (
        <div className="create-form">
          {error && <div className="error">{error}</div>}
          <div>
            <label htmlFor="doc-title">Title</label>
            <input
              id="doc-title"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
            />
          </div>
          <div>
            <label htmlFor="doc-author">Author</label>
            <input
              id="doc-author"
              value={author}
              onChange={(e) => setAuthor(e.target.value)}
            />
          </div>
          <button onClick={handleCreate}>Create</button>
          <button onClick={handleCancel}>Cancel</button>
        </div>
      ) : (
        <>
          <button onClick={() => setShowForm(true)}>New Document</button>
          {documents.length === 0 ? (
            <p>No documents yet.</p>
          ) : (
            <ul>
              {documents.map((doc) => (
                <li key={doc.attrs.id}>
                  <button onClick={() => onSelect(doc)}>
                    {doc.attrs.title}
                  </button>
                  <span className="author">by {doc.attrs.author}</span>
                  <button onClick={() => handleDelete(doc.attrs.id)}>
                    Delete
                  </button>
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </div>
  )
}
