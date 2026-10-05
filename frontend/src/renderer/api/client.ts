import { request } from "./http";
import type {
  AppState,
  AppStatePatch,
  AuthConfig,
  ChapterAttrs,
  ChapterListRow,
  ChapterNode,
  ChapterRelations,
  DocumentContentResponse,
  DocumentWire,
  ImportResponse,
  MutationResponse,
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
 * A picked file's relative path is renderer-supplied, and this is what becomes the
 * name the server stages the file under, so a path that is empty, absolute, or
 * climbing out of the document is refused here rather than sent for the server to
 * refuse. The server checks the same thing independently; this is the earlier of
 * the two.
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
  return `${name}/${path}`;
}

function badPath(path: string): string {
  return `Import needs a relative path within the document directory, got "${path}"`;
}

export interface UpdateDocumentData {
  title: string;
  author: string;
}

export class ApiClient {
  constructor(private readonly base: string = "/api") {}

  private url(path: string): string {
    return `${this.base}${path}`;
  }

  async listDocuments(): Promise<DocumentWire[]> {
    return request<DocumentWire[]>(this.url("/documents"));
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

  async getChapterDocument(chapterId: string): Promise<DocumentContentResponse> {
    return request<DocumentContentResponse>(
      this.url(`/chapters/${encodeURIComponent(chapterId)}/document`),
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
   * `directoryName` is the picked directory's own name, which webkitRelativePath
   * omits. The server requires every part to sit under one shared first segment and
   * takes that segment as the document's title, so it is prepended to each file's
   * relative path here and nowhere else.
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