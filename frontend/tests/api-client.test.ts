import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiClient } from "../src/renderer/api/client";
import { ApiError } from "../src/renderer/api/http";
import type {
  ChapterNode,
  DocumentContentResponse,
  StatusWire,
} from "../src/renderer/api/types";

type FetchCall = { url: string; init: RequestInit };

function mockFetch(status: number, body: unknown): void {
  vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify(body), { status })));
}

function fetchCalls(): FetchCall[] {
  const fetchMock = vi.mocked(globalThis.fetch);
  return fetchMock.mock.calls.map(([url, init]) => ({
    url: String(url),
    init: (init ?? {}) as RequestInit,
  }));
}

const chapterNode: ChapterNode = {
  type: "chapter",
  attrs: { id: "ch-1", title: "Intro", act: "" },
  content: [],
};

beforeEach(() => {
  vi.restoreAllMocks();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("ApiClient documents", () => {
  it("lists documents", async () => {
    mockFetch(200, [{ attrs: { id: "d-1", title: "Faith", author: "A" }, chapter_summaries: [] }]);
    const client = new ApiClient();
    const docs = await client.listDocuments();
    expect(docs).toHaveLength(1);
    expect(fetchCalls()[0].url).toBe("/api/documents");
  });

  it("gets a document with its chapter summaries", async () => {
    const body = {
      attrs: { id: "d-1", title: "Faith", author: "A" },
      chapter_summaries: [{ id: "ch-1", title: "Intro", act: "Act I" }],
    };
    mockFetch(200, body);
    const client = new ApiClient();
    const doc = await client.getDocument("d-1");
    expect(doc.attrs.title).toBe("Faith");
    expect(doc.chapter_summaries[0].act).toBe("Act I");
    expect(fetchCalls()[0].url).toBe("/api/documents/d-1");
  });

  it("creates a document with the attrs body", async () => {
    mockFetch(200, { status: { code: "ok", message: "success" } });
    const client = new ApiClient();
    await client.createDocument({ id: "d-1", title: "Faith", author: "A" });
    const call = fetchCalls()[0];
    expect(call.url).toBe("/api/documents");
    expect(call.init.method).toBe("POST");
    expect(call.init.body).toContain('"title":"Faith"');
  });

  it("updates a document's attrs", async () => {
    mockFetch(200, { status: { code: "ok", message: "success" } });
    const client = new ApiClient();
    await client.updateDocument("d-1", { title: "Love", author: "B" });
    const call = fetchCalls()[0];
    expect(call.url).toBe("/api/documents/d-1");
    expect(call.init.method).toBe("PUT");
  });

  it("deletes a document", async () => {
    mockFetch(200, { status: { code: "ok", message: "success" } });
    const client = new ApiClient();
    await client.deleteDocument("d-1");
    const call = fetchCalls()[0];
    expect(call.url).toBe("/api/documents/d-1");
    expect(call.init.method).toBe("DELETE");
  });
});

describe("ApiClient chapters and lifecycle", () => {
  it("lists chapters by document id", async () => {
    const rows = [
      { id: "ch-1", title: "Intro", act: "Act I", index: 0 },
      { id: "ch-2", title: "Later", act: "Act I", index: 1 },
    ];
    mockFetch(200, rows);
    const client = new ApiClient();
    const chapters = await client.listChapters("d-1");
    expect(chapters).toHaveLength(2);
    expect(chapters[0].act).toBe("Act I");
    expect(fetchCalls()[0].url).toBe("/api/chapters?document=d-1");
  });

  it("creates a chapter with relations", async () => {
    mockFetch(200, { status: { code: "ok", message: "success" } });
    const client = new ApiClient();
    await client.createChapter(
      { id: "ch-1", title: "Intro", act: "Act I" },
      { document_id: "d-1", after_chapter_id: "ch-0" },
    );
    const call = fetchCalls()[0];
    expect(call.url).toBe("/api/chapters");
    expect(call.init.method).toBe("POST");
    expect(call.init.body).toContain('"after_chapter_id":"ch-0"');
  });

  it("gets a chapter as a ProseMirror tree", async () => {
    mockFetch(200, chapterNode);
    const client = new ApiClient();
    const ch = await client.getChapter("ch-1");
    expect(ch.type).toBe("chapter");
    expect(ch.attrs.title).toBe("Intro");
    expect(fetchCalls()[0].url).toBe("/api/chapters/ch-1");
  });

  it("gets a chapter's document text", async () => {
    mockFetch(200, { content: "# Intro\n\ntext", summary: null });
    const client = new ApiClient();
    const doc = await client.getChapterDocument("ch-1");
    expect(doc.content).toContain("# Intro");
    expect(fetchCalls()[0].url).toBe("/api/chapters/ch-1/document");
  });

  it("saves a chapter document and returns canonical text", async () => {
    const response: DocumentContentResponse = {
      content: "canonical text",
      summary: { created: false, changed: 1, added: 0, deleted: 0 },
    };
    mockFetch(200, response);
    const client = new ApiClient();
    const saved = await client.saveChapterDocument("ch-1", "edits");
    expect(saved.content).toBe("canonical text");
    const call = fetchCalls()[0];
    expect(call.url).toBe("/api/chapters/ch-1/document");
    expect(call.init.method).toBe("PUT");
    expect(call.init.body).toContain('"content":"edits"');
  });

  it("reorders a chapter after a sibling (null moves first)", async () => {
    mockFetch(200, { status: { code: "ok", message: "success" } });
    const client = new ApiClient();
    await client.reorderChapter("ch-2", "ch-1");
    await client.reorderChapter("ch-2", null);
    const calls = fetchCalls();
    expect(calls[0].url).toBe("/api/chapters/ch-2/reorder");
    expect(calls[0].init.body).toContain('"after_chapter_id":"ch-1"');
    expect(calls[1].init.body).toContain('"after_chapter_id":null');
  });

  it("renames a chapter via update", async () => {
    mockFetch(200, { status: { code: "ok", message: "success" } });
    const client = new ApiClient();
    await client.updateChapter("ch-1", { title: "Renamed" });
    const call = fetchCalls()[0];
    expect(call.url).toBe("/api/chapters/ch-1");
    expect(call.init.method).toBe("PUT");
    expect(call.init.body).toContain('"title":"Renamed"');
  });

  it("deletes a chapter", async () => {
    mockFetch(200, { status: { code: "ok", message: "success" } });
    const client = new ApiClient();
    await client.deleteChapter("ch-1");
    const call = fetchCalls()[0];
    expect(call.url).toBe("/api/chapters/ch-1");
    expect(call.init.method).toBe("DELETE");
  });
});

describe("ApiClient errors and auth", () => {
  it("surfaces a typed ApiError with detail on non-2xx", async () => {
    mockFetch(404, { detail: "chapter_not_found: ch-1" });
    const client = new ApiClient();
    await expect(client.getChapter("ch-1")).rejects.toBeInstanceOf(ApiError);
    const err = await client.getChapter("ch-1").catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect((err as ApiError).detail).toBe("chapter_not_found: ch-1");
  });

  it("rejects with ApiError on 401 from /me", async () => {
    mockFetch(401, { detail: "not_authenticated" });
    const client = new ApiClient();
    await expect(client.getMe()).rejects.toBeInstanceOf(ApiError);
  });

  it("gets the current user profile", async () => {
    mockFetch(200, {
      user: { id: "u-1", email: "a@b.c", display_name: "A", avatar_url: "" },
    });
    const client = new ApiClient();
    const me = await client.getMe();
    expect(me.id).toBe("u-1");
    expect(fetchCalls()[0].url).toBe("/api/auth/me");
  });

  it("fetches a login (authorization) URL for a provider", async () => {
    mockFetch(200, { authorization_url: "https://accounts.google.com/o/oauth2/v2/auth?x=1" });
    const client = new ApiClient();
    const url = await client.getLoginUrl("google");
    expect(url).toContain("accounts.google.com");
    expect(fetchCalls()[0].url).toBe("/api/auth/login?provider=google");
  });
});

describe("ApiClient error envelope", () => {
  it("parses a status envelope with code and message", async () => {
    const envelope: StatusWire = { status: { code: "ok", message: "success" } };
    mockFetch(200, envelope);
    const client = new ApiClient();
    const result = await client.createDocument({ id: "d-1", title: "F", author: "A" });
    expect(result.status.code).toBe("ok");
  });
});

describe("ApiClient app state", () => {
  it("gets per-user app state", async () => {
    mockFetch(200, { last_document_id: "d-1", panel_widths: { left: 240 }, edit_mode: "wysiwyg" });
    const client = new ApiClient();
    const state = await client.getAppState();
    expect(state.last_document_id).toBe("d-1");
    expect(fetchCalls()[0].url).toBe("/api/app/state");
  });

  it("puts per-user app state", async () => {
    mockFetch(200, { last_document_id: "d-2", panel_widths: null, edit_mode: "raw" });
    const client = new ApiClient();
    const saved = await client.putAppState({ last_document_id: "d-2" });
    expect(saved.edit_mode).toBe("raw");
    const call = fetchCalls()[0];
    expect(call.url).toBe("/api/app/state");
    expect(call.init.method).toBe("PUT");
  });
});