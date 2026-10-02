// Thin fetch wrapper for the NearShop API (proxied at /api by next.config.ts).

export class ApiError extends Error {
  status: number;
  code: string;
  field?: string;

  constructor(message: string, status: number, code = "error", field?: string) {
    super(message);
    this.status = status;
    this.code = code;
    this.field = field;
  }
}

type Query = Record<string, string | number | boolean | null | undefined>;

function withQuery(path: string, query?: Query) {
  if (!query) return path;
  const params = new URLSearchParams();
  for (const [k, v] of Object.entries(query)) {
    if (v === undefined || v === null || v === "") continue;
    params.set(k, String(v));
  }
  const qs = params.toString();
  return qs ? `${path}?${qs}` : path;
}

async function request<T>(method: string, path: string, body?: unknown, query?: Query): Promise<T> {
  const isForm = typeof FormData !== "undefined" && body instanceof FormData;
  let res: Response;
  try {
    res = await fetch(withQuery(`/api${path}`, query), {
      method,
      credentials: "same-origin",
      headers: {
        // Required by the API on state-changing requests (CSRF defence in depth).
        "X-NearShop-Client": "web",
        ...(body !== undefined && !isForm ? { "Content-Type": "application/json" } : {}),
      },
      body: body === undefined ? undefined : isForm ? (body as FormData) : JSON.stringify(body),
    });
  } catch {
    throw new ApiError("Can't reach NearShop right now. Check your connection and try again.", 0, "network");
  }

  if (res.status === 204) return undefined as T;
  const data = await res.json().catch(() => null);
  if (!res.ok) {
    const err = data?.error;
    const detail = typeof data?.detail === "string" ? data.detail : undefined;
    throw new ApiError(
      err?.message ?? detail ?? (res.status >= 500 ? "Something went wrong on our side. Please try again." : "Request failed"),
      res.status,
      err?.code ?? (res.status === 401 ? "unauthorized" : "error"),
      err?.field,
    );
  }
  return data as T;
}

export const api = {
  get: <T>(path: string, query?: Query) => request<T>("GET", path, undefined, query),
  post: <T>(path: string, body?: unknown, query?: Query) => request<T>("POST", path, body ?? {}, query),
  put: <T>(path: string, body?: unknown) => request<T>("PUT", path, body ?? {}),
  patch: <T>(path: string, body?: unknown) => request<T>("PATCH", path, body ?? {}),
  delete: <T>(path: string) => request<T>("DELETE", path),
  upload: <T>(path: string, file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<T>("POST", path, form);
  },
};

export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  if (error instanceof Error) return error.message;
  return "Something went wrong";
}
