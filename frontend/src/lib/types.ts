export type Role = "admin" | "analyst" | "viewer";

export interface User {
  id: string;
  email: string;
  display_name: string;
  role: Role;
  is_active: boolean;
  created_at: string;
}

export interface ArchiveDocument {
  id: string;
  filename: string;
  title: string | null;
  content_type: string;
  byte_size: number;
  status: string;
  doc_type: string | null;
  expiry_date: string | null;
  classification_confidence: number | null;
  page_count: number | null;
  uploaded_by: string | null;
  created_at: string | null;
  indexed_at: string | null;
  extracted_metadata: Record<string, unknown> | null;
}

export interface DocumentList {
  items: ArchiveDocument[];
  total: number;
}

export interface Permission {
  id: string;
  grantee_type: "user" | "role";
  grantee_user_id: string | null;
  grantee_role: string | null;
  permission: "view" | "download" | "manage";
  granted_by: string | null;
  granted_at: string | null;
}

export interface Citation {
  index: number;
  document_id: string;
  filename: string;
  page_start: number;
  page_end: number;
  quote: string;
  score?: number | null;
}

/** A passage surfaced in the evidence panel before the answer is generated. */
export interface Passage {
  index: number;
  document_id: string;
  filename: string;
  page_start: number;
  page_end: number;
  quote?: string;
  score?: number;
}

export interface Answer {
  answer: string;
  found: boolean;
  citations: Citation[];
  intent: string;
  model: string;
  conversation_id: string | null;
  message_id: string | null;
}

export interface SearchHit {
  chunk_id: string;
  document_id: string;
  filename: string;
  doc_type: string | null;
  page_start: number;
  page_end: number;
  score: number;
  excerpt: string;
}

export interface SearchResult {
  query: string;
  hits: SearchHit[];
  count: number;
}

export interface Conversation {
  id: string;
  title: string | null;
  created_at: string | null;
}

export interface StoredMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  answer_found: boolean | null;
  created_at: string | null;
}

export interface AuditEntry {
  id: string;
  actor_user_id: string | null;
  action: string;
  resource_type: string | null;
  resource_id: string | null;
  ip: string | null;
  meta: Record<string, unknown> | null;
  created_at: string | null;
}

export interface AdminStats {
  users: number;
  documents: number;
  ready_documents: number;
  conversations: number;
  citations: number;
}

export interface Summary {
  document_id: string;
  summary: string;
  model: string;
  prompt_version: string;
  generated_at: string | null;
}
