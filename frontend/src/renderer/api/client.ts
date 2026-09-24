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
  MutationResponse,
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

  async getMe(): Promise<UserProfile> {
    const response = await request<{ user: UserProfile }>(this.url("/auth/me"));
    return response.user;
  }

  async getAuthConfig(): Promise<AuthConfig> {
    return request<AuthConfig>(this.url("/auth/config"));
  }

  async getLoginUrl(provider: string): Promise<string> {
    const response = await request<{ authorization_url: string }>(
      this.url(`/auth/login?provider=${encodeURIComponent(provider)}`),
    );
    return response.authorization_url;
  }
}