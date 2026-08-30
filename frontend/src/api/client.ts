import type {
  Document,
  ChapterNode,
  ParagraphNode,
  SentenceNode,
  MutationResponse,
  HistoryList,
} from '@/types'

const BASE_URL = '/api'

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE_URL}${path}`, {
    headers: {
      'Content-Type': 'application/json',
      ...options?.headers,
    },
    ...options,
  })

  if (!response.ok) {
    const error = await response.json()
    throw new Error(error.status?.message || `HTTP ${response.status}`)
  }

  return response.json()
}

export const api = {
  documents: {
    list: () => request<Document[]>('/documents'),
    get: (id: string) => request<Document>(`/documents/${id}`),
    create: (doc: { attrs: { id: string; title: string; author: string } }) =>
      request<MutationResponse>('/documents', {
        method: 'POST',
        body: JSON.stringify(doc),
      }),
    update: (id: string, attrs: { title: string; author: string }) =>
      request<MutationResponse>(`/documents/${id}`, {
        method: 'PUT',
        body: JSON.stringify({ attrs }),
      }),
    delete: (id: string) =>
      request<MutationResponse>(`/documents/${id}`, {
        method: 'DELETE',
      }),
  },

  chapters: {
    list: (documentId: string) =>
      request<{ id: string; title: string }[]>(
        `/chapters?document=${documentId}`
      ),
    get: (id: string) => request<ChapterNode>(`/chapters/${id}`),
    create: (chapter: {
      attrs: { id: string; title: string }
      relations: { document_id: string; after_chapter_id?: string }
    }) =>
      request<MutationResponse>('/chapters', {
        method: 'POST',
        body: JSON.stringify(chapter),
      }),
    update: (id: string, attrs: { title: string }) =>
      request<MutationResponse>(`/chapters/${id}`, {
        method: 'PUT',
        body: JSON.stringify({ attrs }),
      }),
    delete: (id: string) =>
      request<MutationResponse>(`/chapters/${id}`, {
        method: 'DELETE',
      }),
  },

  paragraphs: {
    list: (chapterId: string) =>
      request<{ id: string }[]>(`/paragraphs?chapter=${chapterId}`),
    get: (id: string) => request<ParagraphNode>(`/paragraphs/${id}`),
    create: (paragraph: {
      attrs: { id: string }
      content: SentenceNode[]
      relations: { chapter_id: string; after_paragraph_id?: string }
    }) =>
      request<MutationResponse>('/paragraphs', {
        method: 'POST',
        body: JSON.stringify(paragraph),
      }),
    update: (id: string, data: { content: SentenceNode[] }) =>
      request<MutationResponse>(`/paragraphs/${id}`, {
        method: 'PUT',
        body: JSON.stringify(data),
      }),
    delete: (id: string) =>
      request<MutationResponse>(`/paragraphs/${id}`, {
        method: 'DELETE',
      }),
  },

  sentences: {
    list: (paragraphId: string) =>
      request<{ id: string }[]>(`/sentences?paragraph=${paragraphId}`),
    get: (id: string) => request<SentenceNode>(`/sentences/${id}`),
    create: (sentence: {
      attrs: { id: string }
      content: { type: 'text'; text: string }[]
      relations: { paragraph_id: string; after_sentence_id?: string }
    }) =>
      request<MutationResponse>('/sentences', {
        method: 'POST',
        body: JSON.stringify(sentence),
      }),
    update: (id: string, data: { content: { type: 'text'; text: string }[] }) =>
      request<MutationResponse>(`/sentences/${id}`, {
        method: 'PUT',
        body: JSON.stringify(data),
      }),
    delete: (id: string) =>
      request<MutationResponse>(`/sentences/${id}`, {
        method: 'DELETE',
      }),
  },

  history: {
    list: (chapterId: string, limit = 20, offset = 0) =>
      request<HistoryList>(
        `/history/${chapterId}?limit=${limit}&offset=${offset}`
      ),
    restore: (chapterId: string, commitId: string) =>
      request<ChapterNode>(`/history/${chapterId}`, {
        method: 'PATCH',
        body: JSON.stringify({ commit_id: commitId }),
      }),
  },

  notifications: {
    poll: () =>
      request<{ notifications: Notification[] }>('/notifications'),
  },
}
