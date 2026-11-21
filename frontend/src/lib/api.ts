/**
 * API client.
 *
 * The browser never holds AWS credentials, database URLs or any other secret —
 * it only ever talks to our own backend through the Next.js rewrite proxy.
 *
 * The access token is short-lived and kept in memory only. The refresh token
 * is issued to this browser by the backend on login; we keep it in
 * localStorage because the backend returns it in the response body rather than
 * an httpOnly cookie. It is still scoped to this origin and never leaves the
 * browser except to our own /auth/refresh endpoint.
 */

import type {
  AdminStats,
  Answer,
  ArchiveDocument,
  AuditEntry,
  Conversation,
  DocumentList,
  Permission,
  Role,
  SearchResult,
  StoredMessage,
  Summary,
  User,
} from "./types";

const BASE = process.env.NEXT_PUBLIC_API_BASE || "/api/v1";
const REFRESH_KEY = "ata.refresh_token";

let accessToken: string | null = null;
let refreshing: Promise<boolean> | null = null;

export function setAccessToken(token: string | null) {
  accessToken = token;
}
export function getAccessToken() {
  return accessToken;
}
export function getRefreshToken() {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(REFRESH_KEY);
}
export function clearTokens() {
  accessToken = null;
  if (typeof window !== "undefined") window.localStorage.removeItem(REFRESH_KEY);
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
    this.name = "ApiError";
  }
}

async function parseError(res: Response): Promise<string> {
  try {
    const body = await res.json();
    if (typeof body?.detail === "string") return body.detail;
    if (Array.isArray(body?.detail)) {
      return body.detail
        .map((d: { msg?: string }) => d?.msg ?? JSON.stringify(d))
        .join("; ");
    }
    if (body?.message) return String(body.message);
    return JSON.stringify(body).slice(0, 300);
  } catch {
    return `Request failed (${res.status})`;
  }
}

async function rawRequest<T>(
  path: string,
  init: RequestInit = {},
  retry = true,
): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body !== undefined && !(init.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }
  if (accessToken) headers.set("Authorization", `Bearer ${accessToken}`);

  const res = await fetch(`${BASE}${path}`, { ...init, headers });

  if (res.status === 401 && retry && !path.startsWith("/auth/")) {
    if (await tryRefresh()) return rawRequest<T>(path, init, false);
  }

  if (!res.ok) throw new ApiError(res.status, await parseError(res));
  if (res.status === 204) return undefined as T;
  const text = await res.text();
  return (text ? JSON.parse(text) : undefined) as T;
}

/** Refresh the access token; concurrent callers share one in-flight refresh. */
export async function tryRefresh(): Promise<boolean> {
  if (refreshing) return refreshing;
  const token = getRefreshToken();
  if (!token) return false;
  refreshing = (async () => {
    try {
      const res = await fetch(`${BASE}/auth/refresh`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: token }),
      });
      if (!res.ok) {
        clearTokens();
        return false;
      }
      const data = await res.json();
      accessToken = data.access_token;
      if (data.refresh_token) {
        window.localStorage.setItem(REFRESH_KEY, data.refresh_token);
      }
      return true;
    } catch {
      return false;
    } finally {
      refreshing = null;
    }
  })();
  return refreshing;
}

export const api = {
  health: () => rawRequest<Record<string, unknown>>("/health"),

  async login(email: string, password: string) {
    const res = await fetch(`${BASE}/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    });
    if (!res.ok) throw new ApiError(res.status, await parseError(res));
    const data = await res.json();
    accessToken = data.access_token;
    if (typeof window !== "undefined" && data.refresh_token) {
      window.localStorage.setItem(REFRESH_KEY, data.refresh_token);
    }
    return data;
  },

  logout() {
    clearTokens();
  },

  me: () => rawRequest<User>("/auth/me"),

  ask: (question: string, conversationId?: string | null) =>
    rawRequest<Answer>("/chat/ask", {
      method: "POST",
      body: JSON.stringify({ question, conversation_id: conversationId ?? null }),
    }),

  conversations: () => rawRequest<Conversation[]>("/chat/conversations"),

  messages: (id: string) =>
    rawRequest<StoredMessage[]>(`/chat/conversations/${id}/messages`),

  documents: () => rawRequest<DocumentList>("/documents"),

  document: (id: string) => rawRequest<ArchiveDocument>(`/documents/${id}`),

  preview: (id: string) =>
    rawRequest<{
      id: string;
      filename: string;
      doc_type: string | null;
      expiry_date: string | null;
      status: string;
      pages: {
        chunk_index: number;
        page_start: number;
        page_end: number;
        text: string;
      }[];
    }>(`/documents/${id}/preview`),

  download: (id: string) =>
    rawRequest<{ url: string; expires_in: number }>(`/documents/${id}/download`),

  /**
   * Download the original. The backend's download URL is permission-checked
   * and protected by the bearer token, so it is fetched with the header
   * rather than handed to the browser as a plain navigation — otherwise the
   * request would arrive unauthenticated and be refused.
   */
  downloadBlob: async (id: string, filename: string) => {
    const { url } = await api.download(id);
    const res = await fetch(url, {
      headers: accessToken ? { Authorization: `Bearer ${accessToken}` } : {},
    });
    if (!res.ok) throw new ApiError(res.status, await parseError(res));
    const blob = await res.blob();
    const objectUrl = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = objectUrl;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(objectUrl), 2000);
  },

  upload: async (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return rawRequest<ArchiveDocument>("/documents", { method: "POST", body: form });
  },

  deleteDocument: (id: string) =>
    rawRequest<void>(`/documents/${id}`, { method: "DELETE" }),

  permissions: (id: string) =>
    rawRequest<Permission[]>(`/documents/${id}/permissions`),

  addPermission: (
    id: string,
    body: {
      grantee_type: "user" | "role";
      grantee_user_id?: string | null;
      grantee_role?: string | null;
      permission: "view" | "download" | "manage";
    },
  ) =>
    rawRequest<Permission>(`/documents/${id}/permissions`, {
      method: "POST",
      body: JSON.stringify(body),
    }),

  removePermission: (
    id: string,
    body: {
      grantee_type: "user" | "role";
      grantee_user_id?: string | null;
      grantee_role?: string | null;
      permission: "view" | "download" | "manage";
    },
  ) =>
    rawRequest<{ removed: number }>(`/documents/${id}/permissions`, {
      method: "DELETE",
      body: JSON.stringify(body),
    }),

  summary: (id: string) => rawRequest<Summary>(`/summaries/${id}`),

  createSummary: (id: string) =>
    rawRequest<Summary>(`/summaries/${id}`, { method: "POST" }),

  search: (q: string, topK = 10) =>
    rawRequest<SearchResult>(
      `/search?q=${encodeURIComponent(q)}&top_k=${topK}`,
    ),

  adminUsers: () => rawRequest<{ items: User[]; total: number }>("/admin/users"),

  adminCreateUser: (body: {
    email: string;
    display_name: string;
    password: string;
    role: Role;
  }) =>
    rawRequest<User>("/admin/users", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  adminUpdateUser: (
    id: string,
    body: Partial<{
      display_name: string;
      role: Role;
      is_active: boolean;
      password: string;
    }>,
  ) =>
    rawRequest<User>(`/admin/users/${id}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),

  adminDeleteUser: (id: string) =>
    rawRequest<void>(`/admin/users/${id}`, { method: "DELETE" }),

  adminAudit: () => rawRequest<AuditEntry[]>("/admin/audit"),

  adminStats: () => rawRequest<AdminStats>("/admin/stats"),
};

export interface StreamHandlers {
  onEvidence?: (payload: {
    intent: string;
    found: boolean;
    passages: import("./types").Passage[];
  }) => void;
  onDelta?: (text: string) => void;
  onCitations?: (citations: import("./types").Citation[]) => void;
  onDone?: (payload: Record<string, unknown>) => void;
  onError?: (message: string) => void;
}

/** Stream an answer as SSE, surfacing each frame to the caller as it lands. */
export async function streamAnswer(
  question: string,
  handlers: StreamHandlers,
): Promise<void> {
  const res = await fetch(`${BASE}/chat/stream`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
    },
    body: JSON.stringify({ question, conversation_id: null }),
  });

  if (!res.ok || !res.body) {
    handlers.onError?.(await parseError(res));
    return;
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  const dispatch = (raw: string) => {
    let event = "";
    const data: string[] = [];
    for (const line of raw.split("\n")) {
      if (line.startsWith("event:")) event = line.slice(6).trim();
      else if (line.startsWith("data:")) data.push(line.slice(5).trim());
    }
    if (!data.length) return;
    const text = data.join("\n");
    let payload: any = text;
    try {
      payload = JSON.parse(text);
    } catch {
      /* plain-text frame */
    }
    switch (event) {
      case "evidence":
        handlers.onEvidence?.(payload);
        break;
      case "delta":
        handlers.onDelta?.(payload?.text ?? String(payload));
        break;
      case "citations":
        handlers.onCitations?.(payload?.citations ?? []);
        break;
      case "done":
        handlers.onDone?.(payload);
        break;
      case "error":
        handlers.onError?.(payload?.message ?? "Generation failed");
        break;
    }
  };

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split("\n\n");
    buffer = parts.pop() ?? "";
    for (const part of parts) if (part.trim()) dispatch(part);
  }
  if (buffer.trim()) dispatch(buffer);
}
