export interface UserProfile {
  id: string;
  username: string;
  email: string;
  display_name: string;
  avatar_url: string;
}

export interface AuthConfig {
  login_required: boolean;
  providers: string[];
}

export interface DocumentAttrs {
  id: string;
  title: string;
  author: string;
}

export interface ChapterSummary {
  id: string;
  title: string;
  act: string;
  category?: "Chapter" | "Character";
}

export interface DocumentWire {
  attrs: DocumentAttrs;
  chapter_summaries: ChapterSummary[];
}

export interface ChapterAttrs {
  id: string | null;
  title: string;
  act?: string;
  category?: "Chapter" | "Character";
}

export interface ChapterNodeAttrs {
  id: string | null;
  title: string;
  act: string;
  category?: "Chapter" | "Character";
}

export interface TextNode {
  type: "text";
  text: string;
}

export interface SentenceNode {
  type: "sentence";
  attrs: { id: string | null };
  content: TextNode[];
}

export interface ParagraphNode {
  type: "paragraph";
  attrs: { id: string | null };
  content: SentenceNode[];
}

export interface ChapterNode {
  type: "chapter";
  attrs: ChapterNodeAttrs;
  content: ParagraphNode[];
}

export interface ChapterListRow {
  id: string;
  title: string;
  act: string;
  index: number;
  category?: "Chapter" | "Character";
}

export interface ChapterRelations {
  document_id: string;
  after_chapter_id?: string | null;
}

export interface ChapterImportSummaryWire {
  created: boolean;
  changed: number;
  added: number;
  deleted: number;
}

/**
 * What importing one chapter file persisted, as POST /api/import reports it.
 *
 * Not to be confused with ChapterImportSummaryWire above, which is the chapter
 * save summary and carries only counts: a caller that uploaded a directory has
 * to learn which chapters now exist and what they are called, so this adds
 * identity and category. Mirrors ImportSummaryWire in the server's
 * controllers/schemas/imports.py.
 */
export interface ImportSummaryWire {
  chapter_id: string;
  title: string;
  category: string;
  created: boolean;
  changed: number;
  added: number;
  deleted: number;
}

/** POST /api/import response — one summary per imported chapter file. */
export interface ImportResponse {
  imports: ImportSummaryWire[];
}

export interface DocumentContentResponse {
  content: string;
  summary: ChapterImportSummaryWire | null;
}

export interface Status {
  code: string;
  message: string;
}

export interface MutationResponse {
  status: Status;
  notifications?: Array<Record<string, unknown>> | null;
}

export interface AppState {
  last_document_id: string | null;
  panel_widths: Record<string, number> | null;
  edit_mode: string | null;
}

export interface AppStatePatch {
  last_document_id?: string | null;
  panel_widths?: Record<string, number> | null;
  edit_mode?: string | null;
}