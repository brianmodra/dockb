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

  it("creates a character chapter with its category", async () => {
    mockFetch(200, { status: { code: "ok", message: "success" } });
    const client = new ApiClient();
    await client.createChapter(
      { id: "ch-9", title: "Dramatis", category: "Character" },
      { document_id: "d-1" },
    );
    expect(fetchCalls()[0].init.body).toContain('"category":"Character"');
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

  it("gets the session, including whether a password change is owed", async () => {
    mockFetch(200, {
      user: { id: "u-1", username: "abby", email: "a@b.c", display_name: "A", avatar_url: "" },
      password_change_required: true,
    });
    const client = new ApiClient();
    const me = await client.getMe();
    expect(me.user.username).toBe("abby");
    expect(me.passwordChangeRequired).toBe(true);
    expect(fetchCalls()[0].url).toBe("/api/auth/me");
  });

  it("reads the auth config from the backend", async () => {
    mockFetch(200, { login_required: false, providers: [] });
    const client = new ApiClient();
    const config = await client.getAuthConfig();
    expect(config.login_required).toBe(false);
    expect(config.providers).toEqual([]);
    expect(fetchCalls()[0].url).toBe("/api/auth/config");
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
function pickedFile(relativePath: string, contents = "text"): File {
  const file = new File([contents], relativePath.split("/").pop() ?? "file.md", {
    type: "text/markdown",
  });
  Object.defineProperty(file, "webkitRelativePath", { value: relativePath });
  return file;
}

function sentForm(): FormData {
  const calls = vi.mocked(globalThis.fetch).mock.calls;
  return (calls[0][1] ?? {}).body as FormData;
}

function partNames(form: FormData): string[] {
  return [...form.keys()];
}

function partFilenames(form: FormData, name: string): string[] {
  return form.getAll(name).map((entry) => (entry as File).name);
}

describe("ApiClient import", () => {
  it("posts the picked files as parts named files", async () => {
    mockFetch(200, { imports: [] });
    const client = new ApiClient();
    await client.importDocument("Linchpin", [
      pickedFile("Act I/Opening 1.md"),
      pickedFile("Act I/Opening 2.md"),
    ]);
    const call = fetchCalls()[0];
    expect(call.url).toBe("/api/import");
    expect(call.init.method).toBe("POST");
    expect(call.init.body).toBeInstanceOf(FormData);
    expect(partNames(sentForm())).toEqual(["files", "files"]);
  });

  it("names each part with the directory name ahead of its relative path", async () => {
    mockFetch(200, { imports: [] });
    const client = new ApiClient();
    await client.importDocument("Linchpin", [
      pickedFile("Act I/Opening 1.md"),
      pickedFile("document_metadata.yaml"),
    ]);
    expect(partFilenames(sentForm(), "files")).toEqual([
      "Linchpin/Act I/Opening 1.md",
      "Linchpin/document_metadata.yaml",
    ]);
  });

  it("sends no Content-Type so the browser sets the multipart boundary", async () => {
    mockFetch(200, { imports: [] });
    const client = new ApiClient();
    await client.importDocument("Linchpin", [pickedFile("Act I/Opening 1.md")]);
    const init = (vi.mocked(globalThis.fetch).mock.calls[0][1] ?? {}) as {
      headers?: Record<string, string>;
    };
    expect((init.headers ?? {})["Content-Type"]).toBeUndefined();
  });

  it("omits the paragraphs part when the option is off", async () => {
    mockFetch(200, { imports: [] });
    const client = new ApiClient();
    await client.importDocument("Linchpin", [pickedFile("Act I/Opening 1.md")]);
    expect(sentForm().has("single_newline_paragraphs")).toBe(false);
  });

  it("sends the paragraphs part as true when the option is on", async () => {
    mockFetch(200, { imports: [] });
    const client = new ApiClient();
    await client.importDocument("Linchpin", [pickedFile("Act I/Opening 1.md")], {
      singleNewlineParagraphs: true,
    });
    expect(sentForm().get("single_newline_paragraphs")).toBe("true");
  });

  it("sends the paragraphs part as false when the option is explicitly off", async () => {
    mockFetch(200, { imports: [] });
    const client = new ApiClient();
    await client.importDocument("Linchpin", [pickedFile("Act I/Opening 1.md")], {
      singleNewlineParagraphs: false,
    });
    expect(sentForm().has("single_newline_paragraphs")).toBe(false);
  });

  it("returns the per-chapter summaries", async () => {
    mockFetch(200, {
      imports: [
        {
          chapter_id: "ch-1",
          title: "Opening 1",
          category: "Chapter",
          created: true,
          changed: 3,
          added: 1,
          deleted: 0,
        },
        {
          chapter_id: "ch-2",
          title: "Dramatis Personae",
          category: "Character",
          created: true,
          changed: 0,
          added: 5,
          deleted: 0,
        },
      ],
    });
    const client = new ApiClient();
    const result = await client.importDocument("Linchpin", [pickedFile("Act I/Opening 1.md")]);
    expect(result.imports).toHaveLength(2);
    expect(result.imports[0].title).toBe("Opening 1");
    expect(result.imports[0].changed).toBe(3);
    expect(result.imports[1].category).toBe("Character");
  });

  it("raises the server's detail when the upload is rejected", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(JSON.stringify({ detail: "too many files" }), { status: 422 })),
    );
    const client = new ApiClient();
    await expect(
      client.importDocument("Linchpin", [pickedFile("Act I/Opening 1.md")]),
    ).rejects.toThrow("too many files");
  });

  it("raises the server's detail when the upload is too large", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(JSON.stringify({ detail: "upload exceeds 64.0 MiB" }), { status: 413 })),
    );
    const client = new ApiClient();
    await expect(
      client.importDocument("Linchpin", [pickedFile("Act I/Opening 1.md")]),
    ).rejects.toThrow("upload exceeds 64.0 MiB");
  });
});

describe("ApiClient import part naming", () => {
  it("refuses a file that carries no relative path", async () => {
    mockFetch(200, { imports: [] });
    const client = new ApiClient();
    const stray = new File(["text"], "stray.md", { type: "text/markdown" });
    await expect(client.importDocument("Linchpin", [stray])).rejects.toThrow(
      /relative path/,
    );
    expect(fetchCalls()).toHaveLength(0);
  });

  it("refuses a directory name that is empty", async () => {
    mockFetch(200, { imports: [] });
    const client = new ApiClient();
    await expect(
      client.importDocument("", [pickedFile("Act I/Opening 1.md")]),
    ).rejects.toThrow(/directory name/);
    expect(fetchCalls()).toHaveLength(0);
  });

  it("refuses an empty file list", async () => {
    mockFetch(200, { imports: [] });
    const client = new ApiClient();
    await expect(client.importDocument("Linchpin", [])).rejects.toThrow(/at least one file/);
    expect(fetchCalls()).toHaveLength(0);
  });

  it("prepends without normalising, so the layout rule has one implementation", async () => {
    mockFetch(200, { imports: [] });
    const client = new ApiClient();
    await client.importDocument("Linchpin", [pickedFile("Linchpin/Act I/Opening 1.md")]);
    // webkitRelativePath never repeats the picked directory, so this input does not
    // occur. The doubled segment pins the decision: the client prepends and leaves
    // the caller's path alone rather than also knowing how to strip, which would put
    // the layout rule in two places.
    expect(partFilenames(sentForm(), "files")).toEqual(["Linchpin/Linchpin/Act I/Opening 1.md"]);
  });

  it("rejects a relative path that climbs out of the document directory", async () => {
    mockFetch(200, { imports: [] });
    const client = new ApiClient();
    await expect(
      client.importDocument("Linchpin", [pickedFile("../outside.md")]),
    ).rejects.toThrow(/relative path/);
    expect(fetchCalls()).toHaveLength(0);
  });

  it("rejects a relative path that reaches the filesystem root", async () => {
    mockFetch(200, { imports: [] });
    const client = new ApiClient();
    await expect(
      client.importDocument("Linchpin", [pickedFile("/etc/passwd")]),
    ).rejects.toThrow(/relative path/);
    expect(fetchCalls()).toHaveLength(0);
  });

  it("rejects a backslash, as the server's own path rule does", async () => {
    mockFetch(200, { imports: [] });
    const client = new ApiClient();
    await expect(
      client.importDocument("Linchpin", [pickedFile("Act I\\Opening 1.md")]),
    ).rejects.toThrow(/relative path/);
    expect(fetchCalls()).toHaveLength(0);
  });

  it("rejects a drive letter, as the server's own path rule does", async () => {
    mockFetch(200, { imports: [] });
    const client = new ApiClient();
    await expect(
      client.importDocument("Linchpin", [pickedFile("C:/Windows/system.ini")]),
    ).rejects.toThrow(/relative path/);
    expect(fetchCalls()).toHaveLength(0);
  });

  it("rejects a control character, as the server's own path rule does", async () => {
    mockFetch(200, { imports: [] });
    const client = new ApiClient();
    await expect(
      client.importDocument("Linchpin", [pickedFile("Act I/Opening\u0007 1.md")]),
    ).rejects.toThrow(/relative path/);
    expect(fetchCalls()).toHaveLength(0);
  });

  it("rejects a . segment, as the server's own path rule does", async () => {
    mockFetch(200, { imports: [] });
    const client = new ApiClient();
    await expect(
      client.importDocument("Linchpin", [pickedFile("Act I/./Opening 1.md")]),
    ).rejects.toThrow(/relative path/);
    expect(fetchCalls()).toHaveLength(0);
  });

  it("rejects an empty segment, as the server's own path rule does", async () => {
    mockFetch(200, { imports: [] });
    const client = new ApiClient();
    await expect(
      client.importDocument("Linchpin", [pickedFile("Act I//Opening 1.md")]),
    ).rejects.toThrow(/relative path/);
    expect(fetchCalls()).toHaveLength(0);
  });

  it("normalises a backslash-free path without changing its segments", async () => {
    mockFetch(200, { imports: [] });
    const client = new ApiClient();
    await client.importDocument("Linchpin", [pickedFile("Act I/Opening 1.md")]);
    expect(partFilenames(sentForm(), "files")).toEqual(["Linchpin/Act I/Opening 1.md"]);
  });
});


describe("ApiClient auth", () => {
  it("ends the session with POST /api/auth/logout", async () => {
    mockFetch(200, { status: "ok" });
    await new ApiClient().logout();
    const call = fetchCalls()[0];
    expect(call.url).toBe("/api/auth/logout");
    expect(call.init.method).toBe("POST");
  });
});
