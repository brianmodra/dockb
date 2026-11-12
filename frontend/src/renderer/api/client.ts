import { request } from "./http";
import type {
  AppState,
  AppStatePatch,
  AuthConfig,
  ChapterAttrs,
  ChapterListRow,
  ChapterNode,
  ChapterRelations,
  ChatResponse,
  DocumentContentResponse,
  DocumentMentionsResponse,
  DocumentWire,
  GlossaryResponse,
  ImportResponse,
  MutationResponse,
  NarrativePerspectivesResponse,
  PovResponse,
  ProofreadingCheckRequest,
  ProofreadingCheckResponse,
  ProofreadingLanguagesResponse,
  RenumberResponse,
  Session,
  UserProfile,
} from "./types";

export interface UpdateChapterData {
  id?: string | null;
  title?: string;
  act?: string;
}

export interface CreateDocumentData {
  id: string;
  title: string;
  author: string;
}

/**
 * The multipart filename for one picked file: the document directory, then the
 * file's path within it.
 *
 * webkitRelativePath already starts with the picked directory's name, so a path
 * that carries it is sent as-is instead of repeating it; a bare path inside the
 * directory gets the name prepended. A picked file's relative path is
 * renderer-supplied, and this is what becomes the name the server stages the file
 * under, so a path that is empty, absolute, or climbing out of the document is
 * refused here rather than sent for the server to refuse. The server checks the
 * same thing independently; this is the earlier of the two.
 */
function partName(directoryName: string, relativePath: string): string {
  const name = directoryName.trim();
  if (name === "") {
    throw new Error("Import needs the document directory name");
  }
  const path = String(relativePath ?? "");
  if (path.includes("\\") || /^[a-zA-Z]:/.test(path) || /^[\\/]/.test(path)) {
    throw new Error(badPath(path));
  }
  for (const char of path) {
    const code = char.codePointAt(0) ?? 0;
    if (code < 32 || code === 127) {
      throw new Error(badPath(path));
    }
  }
  for (const segment of path.split("/")) {
    if (segment === "" || segment === "." || segment === "..") {
      throw new Error(badPath(path));
    }
  }
  if (path === name || path.startsWith(`${name}/`)) {
    return path;
  }
  return `${name}/${path}`;
}

function badPath(path: string): string {
  return `Import needs a relative path within the document directory, got "${path}"`;
}

export interface UpdateDocumentData {
  title: string;
  author: string;
  narrative_perspective?: string;
}

export class ApiClient {
  constructor(private readonly base: string = "/api") {}

  private url(path: string): string {
    return `${this.base}${path}`;
  }

  async listDocuments(): Promise<DocumentWire[]> {
    return request<DocumentWire[]>(this.url("/documents"));
  }

  /** Return the fixed narrative-perspective vocabulary the editor offers. */
  async getNarrativePerspectives(): Promise<NarrativePerspectivesResponse> {
    return request<NarrativePerspectivesResponse>(this.url("/documents/narrative-perspectives"));
  }

  async getDocument(documentId: string): Promise<DocumentWire> {
    return request<DocumentWire>(this.url(`/documents/${encodeURIComponent(documentId)}`));
  }

  async createDocument(data: CreateDocumentData): Promise<MutationResponse> {
    return request<MutationResponse>(this.url("/documents"), {
      method: "POST",
      body: JSON.stringify({ attrs: data }),
    });
  }

  async updateDocument(documentId: string, data: UpdateDocumentData): Promise<MutationResponse> {
    return request<MutationResponse>(this.url(`/documents/${encodeURIComponent(documentId)}`), {
      method: "PUT",
      body: JSON.stringify({ attrs: data }),
    });
  }

  async deleteDocument(documentId: string): Promise<MutationResponse> {
    return request<MutationResponse>(this.url(`/documents/${encodeURIComponent(documentId)}`), {
      method: "DELETE",
    });
  }

  /** Post the editor's prompt for the model; the backend holds the OpenAI key. */
  async sendPrompt(prompt: string, documentId?: string | null): Promise<ChatResponse> {
    return request<ChatResponse>(this.url("/ai/chat"), {
      method: "POST",
      body: JSON.stringify({ prompt, ...(documentId ? { document_id: documentId } : {}) }),
    });
  }

  /** Check one paragraph; *signal* lets a newer check abort a stale one. */
  async checkText(
    body: ProofreadingCheckRequest,
    signal?: AbortSignal,
  ): Promise<ProofreadingCheckResponse> {
    return request<ProofreadingCheckResponse>(this.url("/check"), {
      method: "POST",
      body: JSON.stringify(body),
      signal,
    });
  }

  /** Return the proofreading languages the backend accepts. */
  async getProofreadingLanguages(): Promise<ProofreadingLanguagesResponse> {
    return request<ProofreadingLanguagesResponse>(this.url("/check/languages"));
  }

  /** Return this document's stored accepted words. */
  async getGlossary(documentId: string): Promise<GlossaryResponse> {
    return request<GlossaryResponse>(this.url(`/documents/${encodeURIComponent(documentId)}/glossary`));
  }

  /** Add one word to this document's accepted words. */
  async postGlossary(documentId: string, word: string): Promise<GlossaryResponse> {
    return request<GlossaryResponse>(this.url(`/documents/${encodeURIComponent(documentId)}/glossary`), {
      method: "POST",
      body: JSON.stringify({ word }),
    });
  }

  /** Remove one word from this document's accepted words. */
  async deleteGlossary(documentId: string, word: string): Promise<GlossaryResponse> {
    return request<GlossaryResponse>(
      this.url(`/documents/${encodeURIComponent(documentId)}/glossary/${encodeURIComponent(word)}`),
      { method: "DELETE" },
    );
  }

  async listChapters(documentId: string): Promise<ChapterListRow[]> {
    return request<ChapterListRow[]>(
      this.url(`/chapters?document=${encodeURIComponent(documentId)}`),
    );
  }

  async createChapter(attrs: ChapterAttrs, relations: ChapterRelations): Promise<MutationResponse> {
    return request<MutationResponse>(this.url("/chapters"), {
      method: "POST",
      body: JSON.stringify({ attrs, relations }),
    });
  }

  async getChapter(chapterId: string): Promise<ChapterNode> {
    return request<ChapterNode>(this.url(`/chapters/${encodeURIComponent(chapterId)}`));
  }

  async getChapterDocument(
    chapterId: string,
    options: { readonly?: boolean } = {},
  ): Promise<DocumentContentResponse> {
    const query = options.readonly ? "?readonly=1" : "";
    return request<DocumentContentResponse>(
      this.url(`/chapters/${encodeURIComponent(chapterId)}/document${query}`),
    );
  }

  /** Return the document's paragraph → mentioned-character-chapter map. */
  async getDocumentMentions(documentId: string): Promise<DocumentMentionsResponse> {
    return request<DocumentMentionsResponse>(
      this.url(`/documents/${encodeURIComponent(documentId)}/mentions`),
    );
  }

  async saveChapterDocument(chapterId: string, content: string): Promise<DocumentContentResponse> {
    return request<DocumentContentResponse>(
      this.url(`/chapters/${encodeURIComponent(chapterId)}/document`),
      {
        method: "PUT",
        body: JSON.stringify({ content }),
      },
    );
  }

  async reorderChapter(chapterId: string, afterChapterId: string | null): Promise<MutationResponse> {
    return request<MutationResponse>(
      this.url(`/chapters/${encodeURIComponent(chapterId)}/reorder`),
      {
        method: "POST",
        body: JSON.stringify({ after_chapter_id: afterChapterId }),
      },
    );
  }

  /**
   * Set, suggest, or clear a chapter's point-of-view character.
   *
   * An empty name clears. A name that matches nothing — or only part of a
   * character's name — is not applied: `applied` is false and `warning` says
   * why (`suggestion` carries the character's title, when one is near).
   */
  async setPov(chapterId: string, name: string): Promise<PovResponse> {
    return request<PovResponse>(this.url(`/chapters/${encodeURIComponent(chapterId)}/pov`), {
      method: "POST",
      body: JSON.stringify({ name }),
    });
  }

  /**
   * Renumber every act chapter of a document, from `start` (1 unless told
   * otherwise), in display order.
   *
   * Returns one entry per chapter whose title changed, so the caller can say
   * what happened; an empty list means the numbering was already right.
   */
  async renumberChapters(documentId: string, options: { start?: number } = {}): Promise<RenumberResponse> {
    return request<RenumberResponse>(this.url("/chapters/renumber"), {
      method: "POST",
      body: JSON.stringify({ document_id: documentId, start: options.start ?? 1 }),
    });
  }

  async updateChapter(chapterId: string, attrs: UpdateChapterData): Promise<MutationResponse> {
    return request<MutationResponse>(this.url(`/chapters/${encodeURIComponent(chapterId)}`), {
      method: "PUT",
      body: JSON.stringify({ attrs }),
    });
  }

  async deleteChapter(chapterId: string): Promise<MutationResponse> {
    return request<MutationResponse>(this.url(`/chapters/${encodeURIComponent(chapterId)}`), {
      method: "DELETE",
    });
  }

  async getAppState(): Promise<AppState> {
    return request<AppState>(this.url("/app/state"));
  }

  async putAppState(state: AppStatePatch): Promise<AppState> {
    return request<AppState>(this.url("/app/state"), {
      method: "PUT",
      body: JSON.stringify(state),
    });
  }

  async getMe(): Promise<Session> {
    const response = await request<{ user: UserProfile; password_change_required: boolean }>(
      this.url("/auth/me"),
    );
    return { user: response.user, passwordChangeRequired: response.password_change_required };
  }

  async loginWithPassword(username: string, password: string): Promise<Session> {
    const response = await request<{ user: UserProfile; password_change_required: boolean }>(
      this.url("/auth/login/password"),
      { method: "POST", body: JSON.stringify({ username, password }) },
    );
    return { user: response.user, passwordChangeRequired: response.password_change_required };
  }

  /** Returns nothing useful: the response is always `{status: "ok", signed_out: true}`. */
  async changePassword(currentPassword: string, newPassword: string): Promise<void> {
    await request(this.url("/auth/change-password"), {
      method: "POST",
      body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
    });
  }

  async logout(): Promise<void> {
    await request(this.url("/auth/logout"), { method: "POST" });
  }

  async getAuthConfig(): Promise<AuthConfig> {
    return request<AuthConfig>(this.url("/auth/config"));
  }

  /**
   * Import a document directory as multipart parts.
   *
   * `directoryName` is the picked directory's own name, which is the first segment
   * of each file's webkitRelativePath. The server requires every part to sit under
   * one shared first segment and takes that segment as the document's title, so a
   * relative path that already carries the name is sent unchanged and a bare one
   * has the name prepended.
   */
  async importDocument(
    directoryName: string,
    files: File[],
    options: { singleNewlineParagraphs?: boolean } = {},
  ): Promise<ImportResponse> {
    if (files.length === 0) {
      throw new Error("Import needs at least one file");
    }
    const form = new FormData();
    for (const file of files) {
      form.append("files", file, partName(directoryName, file.webkitRelativePath));
    }
    if (options.singleNewlineParagraphs === true) {
      form.append("single_newline_paragraphs", "true");
    }
    return request<ImportResponse>(this.url("/import"), { method: "POST", body: form });
  }
}