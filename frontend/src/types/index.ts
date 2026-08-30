export interface DocumentAttrs {
  id: string
  title: string
  author: string
}

export interface ChapterSummary {
  id: string
  title: string
}

export interface Document {
  attrs: DocumentAttrs
  chapter_summaries: ChapterSummary[]
}

export interface ChapterAttrs {
  id: string
  title: string
}

export interface ParagraphAttrs {
  id: string
}

export interface SentenceAttrs {
  id: string
}

export interface TextNode {
  type: 'text'
  text: string
}

export interface SentenceNode {
  type: 'sentence'
  attrs: SentenceAttrs
  content: TextNode[]
}

export interface ParagraphNode {
  type: 'paragraph'
  attrs: ParagraphAttrs
  content: SentenceNode[]
}

export interface ChapterNode {
  type: 'chapter'
  attrs: ChapterAttrs
  content: ParagraphNode[]
}

export interface MutationStatus {
  code: string
  message: string
}

export interface MutationResponse {
  status: MutationStatus
  notifications?: Notification[]
}

export interface SentenceSplitNotification {
  type: 'sentence_split'
  paragraph_id: string
  changed_sentences: SentenceNode[]
}

export interface ParagraphSplitNotification {
  type: 'paragraph_split'
  chapter_id: string
  changed_paragraphs: ParagraphNode[]
}

export type Notification = SentenceSplitNotification | ParagraphSplitNotification

export interface HistorySnapshot {
  datetime: string
  commit_id: string
}

export interface HistoryList {
  snapshots: HistorySnapshot[]
}
