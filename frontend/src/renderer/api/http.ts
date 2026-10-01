export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly detail: string,
  ) {
    super(detail);
    this.name = "ApiError";
  }
}

async function parseError(response: Response): Promise<string> {
  try {
    const body: unknown = await response.json();
    if (body && typeof body === "object" && "detail" in body) {
      return String((body as { detail: unknown }).detail);
    }
  } catch {
    // non-JSON error body: fall back to the status text
  }
  return response.statusText || `HTTP ${response.status}`;
}

function defaultHeaders(init: RequestInit): HeadersInit {
  if (typeof FormData !== "undefined" && init.body instanceof FormData) {
    return init.headers ?? {};
  }
  return { "Content-Type": "application/json", ...(init.headers ?? {}) };
}

export async function request<T>(
  url: string,
  init: RequestInit = {},
): Promise<T> {
  const response = await fetch(url, {
    ...init,
    headers: defaultHeaders(init),
  });
  if (!response.ok) {
    throw new ApiError(response.status, await parseError(response));
  }
  return (await response.json()) as T;
}