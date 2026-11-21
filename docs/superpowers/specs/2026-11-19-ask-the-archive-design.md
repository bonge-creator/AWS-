# Ask the Archive — Design Specification

**Generated with** [Claude Code](https://claude.com/claude-code)
**Date:** 2026-11-19
**Project:** Ask the Archive — TDW × AWS Innovation Challenge

---

## 1. Overview & Goals

### 1.1 Purpose
Build an AI-powered enterprise document intelligence platform that lets **authorised users** ask natural‑language questions about a collection of organisational documents and receive **accurate answers linked to their original sources** — under **strict per‑document access control**.

### 1.2 Mandatory Judging Requirements (5 live demos)

| # | Test | What judges verify |
|---|---|---|
| 1 | **Lease expiry query** — "which lease agreements expire next year?" | Deterministic structured metadata query (dates must be correct) + RAG citations. |
| 2 | **Contract summary** — select a contract, request summary | Document summarisation, citation panel, page reference extraction. |
| 3 | **Citation click** → open the original document | Secure download / page preview, provenance integrity. |
| 4 | **Two users, same question, different answers** — cross‑user information leakage must be provably impossible. | ACL‑scoped retrieval + model‑side verification that unauthorised text never reaches the model. |
| 5 | **Honest "not in archive"** — ask a question whose answer doesn't exist | Model must say it does not know (no hallucination). |

### 1.3 Core Guiding Principles

1. **Technical clarity** — complex engineering concepts presented accessibly; no oversimplification that loses correctness.
2. **Permission boundary before retrieval** — unauthorised text never enters the model prompt, verified at the SQL level.
3. **Deterministic fallbacks** — every question type has a deterministic path (date arithmetic, structured extraction, abstention guard) that works even when the model is "confused."
4. **Honest responses** — when information cannot be found, the system explicitly says so; no invented citations.
5. **Performance conscious** — balance RAG quality with fast retrieval; only scan what's necessary per user.

### 1.4 Out of Scope (not in 30h)

- Full‑text search engine (ElasticSearch is referenced in the existing stack but Pgvector + pg_trgm suffices for demo scale).
- Real‑time collaborative editing or versioning of original documents.
- Multi‑tenant isolation beyond document‑level permissions.
- Mobile‑first responsive polish beyond the 5 core screens.

---

## 2. Non‑Negotiable Security (brief, not design‑by‑default)

- **Enforce permissions before retrieval** — the SQL CTE that resolves permitted document IDs runs *before* any vector search.
- **Never send unauthorised document content to the model** — post‑retrieval re‑validation step; every chunk_id placed in the prompt is verified against `document_permissions`.
- **Prevent cross-user information leakage** — model prompt is scoped to user‑granted documents only; the prompt itself contains only allowed text.
- **Protect original documents** — S3 originals are SSE‑KMS encrypted; downloads flow through the backend with a fresh presigned URL + permission check; raw bytes never served from frontend.
- **Secure document previews and downloads** — only the currently‑authenticated user can generate a presigned URL; URLs are 60‑second TTL.
- **Use secure AWS IAM permissions** — policy‑as‑code; each service role has only the minimum actions it needs.
- **Never expose credentials in frontend code** — all AWS SDK calls happen in the Python FastAPI backend behind environment‑variable‑configured boto3 sessions.
- **Validate uploads and API requests** — MIME‑type guard, size limits, magic‑byte verification for PDFs/Office docs; Pydantic schemas with `class-validator` equivalents.

---

## 3. Tech Stack & Rationale

| Layer | Technology | Why |
|---|---|---|
| **Frontend** | Next.js 15+ (App Router), TypeScript, Tailwind v4 | The spec explicitly mandates Next.js + React + TS + Tailwind. Design matches the charcoal/concrete/copper palette (hybrid with AWS‑orange accents). |
| **Backend** | Python 3.12, FastAPI, Pydantic 2, SQLAlchemy 2, Alembic | Brief explicitly demands Python/FastAPI/Pydantic/SQLAlchemy/Alembic. FastAPI gives OpenAPI schema for free, SSE streaming for SSE chat, dependency‑injection cleanly. |
| **Database** | PostgreSQL 16 + pgvector | pgvector is the canonical vector store in the brief. No Docker available → use a managed free tier (Neon/Supabase) with pgvector enabled; `vector(1024)` dimension for Titan embeddings. |
| **Embeddings** | Amazon Titan Text Embeddings V2 (Bedrock, 1024 dims) + local fallback `BAAI/bge-m3` via sentence‑transformers (also 1024 dims) | Provider‑port design (see §6) so Bedrock is default but a real open‑source model is the hard fail‑over. |
| **OCR / Extraction** | Amazon Textract (`StartDocumentAnalysis` / `StartDocumentTextDetection`) + PyMuPDF/pypdf digital‑PDF fallback | “Do not fake AWS integrations” — Textract is the primary path; local fallback is only invoked when AWS creds are genuinely absent. |
| **LLM Generation** | Amazon Bedrock Converse API with Claude 3.5 Sonnet / Haiku | Bedrock Converse gives a standardised chat interface (system prompt + tool use capability). Model id configurable via env. |
| **Auth** | Self‑managed JWT (HS256) + argon2id password hashing + documented Cognito adapter hook | Cognito setup (~3‑4h) is deferred; self‑managed JWT is reliable in 30h and satisfies judges’ “where appropriate” clause. |
| **Storage** | Amazon S3 (SSE‑KMS) + backend‑generated presigned URLs | S3 is a brief requirement; presigned URLs are issued *after* permission check, never leaked to frontend. |
| **CI / Schema** | Alembic migrations, OpenAPI → TypeScript client (via `openapi-typescript-codegen`) | Zero‑drift API contract between frontend and backend. |
| **Design system** | Charcoal (#171A1D), Concrete (#F3F1EC), Steel Grey (#8A9095), Warm Copper (#B9784B) + AWS‑orange (#FF9900) accents | Hybrid visual identity approved by the user; the charcoal/concrete/copper system is the user’s existing direction; AWS‑orange surfaces only on AWS‑related surfaces (model calls, ingestion status). |

### 3.1 Ports & Config‑Driven Fallbacks

The backend defines a set of **protocols** (`StoragePort`, `ExtractorPort`, `EmbedderPort`, `LlmPort`, `JobRunnerPort`). Two implementations per protocol:

| Protocol | Active impl (default) | Fallback impl (when AWS creds absent) |
|---|---|---|
| `StoragePort` | S3Adapter (boto3) | LocalFsAdapter (cwd/uploads dir) |
| `ExtractorPort` | TextractAdapter (async job + poll) | PdfPlumberAdapter (digital PDF text extraction) |
| `EmbedderPort` | BedrockTitanAdapter (runtime.invoke_model) | BgeM3Adapter (sentence‑transformers) |
| `LlmPort` | BedrockConverseAdapter (Claude via Converse) | ExtractiveFallback (answer strictly from retrieved passages without model generation) |
| `JobRunnerPort` | LocalRunner (FastAPI BackgroundTasks / thread‑pool) | LambdaSqsRunner (SQS → Lambda; stretch) |

The active implementation is selected per `config.py` from `os.getenv()`. This satisfies “no fake AWS integrations” — the active impls are real boto3 calls; the fallbacks are also real (local models, real PDF parsing), just not AWS‑backed.

---

## 4. Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         NEXT.JS 15 (App Router)                         │
│  /login · / · /assistant · /library · /documents/[id] · /admin           │
│  └─▶ fetch API / SSE / auth tokens                                       │
└─────────────────────┬───────────────────────────────────────────────────────┘
                      │  JSON / SSE streaming
                      ▼
              ┌──────────────────────┐
              │  FASTAPI · Pydantic  │
              │  app/               │
              │  ├─ core/           │  config, logging, deps, errors │
              │  ├─ db/             │  session, models/, repositories │
              │  ├─ modules/        │  auth, documents, ingestion,    │
              │  │                 │       retrieval, chat, citations, │
              │  │                 │       admin, audit               │
              │  ├─ ports/          │  protocols + AWS+local adapters │
              │  └─ shared/         │  schemas, utils, prompts        │
              └───────▲─────────────┘
                      │  SQLAlchemy 2 + pgvector
                      ▼
              ┌──────────────────────┐
              │  PostgreSQL 16 + pgvector │
              │  tables:                │
              │  users · documents ·   │
              │  document_chunks ·     │
              │  document_permissions │
              │  conversations ·       │
              │  messages · citations  │
              │  ingestion_jobs ·      │
              │  document_summaries   │
              │  audit_logs            │
              └──────────────────────┘
```

The **security boundary** is the `permitted` CTE in the retrieval SQL (see §7). All other queries flow through it.

---

## 5. Data Model (PostgreSQL + pgvector)

> **All tables use UUID primary keys. Timestamps are UTC. Enum types are PostgreSQL `ENUM`.**

### 5.1 `users`

| Column | Type | Constraints | Comment |
|---|---|---|---|
| `id` | UUID | PK, default `gen_random_uuid()` | |
| `email` | CITEXT | UNIQUE, NOT NULL | Login username |
| `display_name` | TEXT | NOT NULL | Shown in UI |
| `password_hash` | TEXT | NOT NULL | argon2id hash |
| `role` | `user_role` enum(`admin`,`analyst`,`viewer`) | NOT NULL | org‑level role |
| `is_active` | BOOLEAN | DEFAULT true | |
| `created_at` | TIMESTAMPTZ | DEFAULT now() | |
| `updated_at` | TIMESTAMPTZ | DEFAULT now() | |

### 5.2 `documents`

| Column | Type | Constraints | Comment |
|---|---|---|---|
| `id` | UUID | PK, default `gen_random_uuid()` | |
| `s3_key` | TEXT | UNIQUE, NOT NULL | S3 object key (original) |
| `filename` | TEXT | NOT NULL | Original client filename |
| `content_type` | TEXT | NOT NULL | e.g. `application/pdf` |
| `byte_size` | BIGINT | NOT NULL | |
| `checksum_sha256` | TEXT | NOT NULL | SHA‑256 of uploaded bytes |
| `status` | `document_status` enum(`uploaded`,`processing`,`ready`,`failed`) | DEFAULT `uploaded` | |
| `doc_type` | `doc_type_enum` enum(`contract`,`lease`,`invoice`,`report`,`policy`,`nda`,`other`) | NULLABLE | Ingested from extracted metadata |
| `page_count` | INTEGER | NULLABLE | |
| `classification_confidence` | REAL | NULLABLE | LLM‑extracted confidence |
| `extracted_metadata` | JSONB | NULLABLE | Key‑value pairs: parties, dates, amounts, etc. |
| `expiry_date` | DATE | NULLABLE | Populated for leases; used in TEST 1 |
| `uploaded_by` | UUID FK → `users.id` | | |
| `created_at` | TIMESTAMPTZ | DEFAULT now() | |
| `indexed_at` | TIMESTAMPTZ | NULLABLE | When embedding pipeline finished |

### 5.3 `document_chunks`

| Column | Type | Constraints | Comment |
|---|---|---|---|
| `id` | UUID | PK, default `gen_random_uuid()` | |
| `document_id` | UUID FK → `documents.id` | ON DELETE CASCADE | |
| `chunk_index` | INTEGER | NOT NULL | 0‑based within doc |
| `page_start` | INTEGER | NOT NULL | First page number |
| `page_end` | INTEGER | NOT NULL | Last page number (inclusive) |
| `text` | TEXT | NOT NULL | The passage; *never* contains unauthorised content after ACL filter |
| `token_count` | INTEGER | DEFAULT 0 | Approx. token count |
| `heading_path` | TEXT[] | DEFAULT '{}' | `["Terminology","5.1"]` etc. |
| `embedding` | vector(1024) | NOT NULL | Cosine‑normed; Titan / bge‑m3 output |
| `embedding_model` | TEXT | NOT NULL | `titan-v2` | `bge-m3` (records provenance) |
| `unique(document_id, chunk_index)` | | | |

**HNSW index:** `CREATE INDEX ON document_chunks USING hnsw (embedding vector_cosine_ops) WITH (m=16, ef_construction=64);`

### 5.4 `document_permissions` (the **ACL**)

| Column | Type | Constraints | Comment |
|---|---|---|---|
| `id` | UUID | PK, default `gen_random_uuid()` | |
| `document_id` | UUID FK → `documents.id` | ON DELETE CASCADE | |
| `grantee_type` | `grantee_type_enum` enum(`user`,`role`) | NOT NULL | |
| `grantee_id` | UUID | FK → `users.id` | Used when `grantee_type='user'` |
| `grantee_role` | `user_role` enum(`admin`,`analyst`,`viewer`) | NULLABLE | Used when `grantee_type='role'` |
| `permission` | `permission_enum` enum(`view`,`download`,`manage`) | NOT NULL | |
| `granted_by` | UUID FK → `users.id` | | Admin who granted |
| `granted_at` | TIMESTAMPTZ | DEFAULT now() | |
| **CHECK** `(grantee_type='user' AND grantee_id IS NOT NULL AND grantee_role IS NULL) OR (grantee_type='role' AND grantee_id IS NULL AND grantee_role IS NOT NULL)` | | | Enforces exactly one grantee. |
| **UNIQUE** `(document_id, grantee_type, grantee_id/grantee_role, permission)` | | | |

### 5.5 `conversations`

| Column | Type | Constraints | Comment |
|---|---|---|---|
| `id` | UUID | PK, default `gen_random_uuid()` | |
| `user_id` | UUID FK → `users.id` | | Owner; each user has their own conversation space |
| `title` | TEXT | NULLABLE | e.g. "Lease expiry query" |
| `created_at` | TIMESTAMPTZ | DEFAULT now() | |

### 5.6 `messages`

| Column | Type | Constraints | Comment |
|---|---|---|---|
| `id` | UUID | PK, default `gen_random_uuid()` | |
| `conversation_id` | UUID FK → `conversations.id` | ON DELETE CASCADE | |
| `role` | `message_role` enum(`user`,`assistant`) | NOT NULL | |
| `content` | TEXT | NOT NULL | Model answer (may contain `[1]`, `[2]` citation markers) |
| `created_at` | TIMESTAMPTZ | DEFAULT now() | |

### 5.7 `citations` (provenance)

| Column | Type | Constraints | Comment |
|---|---|---|---|
| `id` | UUID | PK, default `gen_random_uuid()` | |
| `message_id` | UUID FK → `messages.id` | ON DELETE CASCADE | |
| `document_id` | UUID FK → `documents.id` | | |
| `chunk_id` | UUID FK → `document_chunks.id` | | |
| `page_start` | INTEGER | | |
| `page_end` | INTEGER | | |
| `quote` | TEXT | | The exact passage cited |
| `confidence` | REAL | | LLM‑assigned confidence (usually 1.0 when server‑side) |
| **UNIQUE** `(message_id, chunk_id)` | | | One citation per chunk per message. |

### 5.8 `retrieval_evidence` (audit trail — one row per retrieved chunk per answer)

| Column | Type | Constraints | Comment |
|---|---|---|---|
| `id` | UUID | PK, default `gen_random_uuid()` | |
| `message_id` | UUID FK → `messages.id` | | |
| `chunk_id` | UUID FK → `document_chunks.id` | | |
| `rank` | INTEGER | | 1‑based rank in result set |
| `score` | REAL | | Cosine similarity (1 - distance) |
| `token_count` | INTEGER | | Token count of the chunk |
| `created_at` | TIMESTAMPTZ | DEFAULT now() | |

### 5.9 `ingestion_jobs`

| Column | Type | Constraints | Comment |
|---|---|---|---|
| `id` | UUID | PK, default `gen_random_uuid()` | |
| `document_id` | UUID FK → `documents.id` | | |
| `status` | `job_status` enum(`queued`,`running`,`succeeded`,`failed`) | DEFAULT `queued` | |
| `stage` | TEXT | e.g. `extract`, `chunk`, `embed` | |
| `progress` | INTEGER | 0‑100 | |
| `error` | TEXT | NULLABLE | |
| `attempts` | INTEGER | DEFAULT 0 | |
| `started_at` | TIMESTAMPTZ | | |
| `finished_at` | TIMESTAMPTZ | NULLABLE | |

### 5.10 `document_summaries`

| Column | Type | Constraints | Comment |
|---|---|---|---|
| `id` | UUID | PK, default `gen_random_uuid()` | |
| `document_id` | UUID FK → `documents.id` | UNIQUE | |
| `summary` | TEXT | | Model‑generated summary |
| `model` | TEXT | e.g. `bedrock-claude-3-5-sonnet` | |
| `prompt_version` | TEXT | | Incremented when summary strategy changes |
| `generated_at` | TIMESTAMPTZ | DEFAULT now() | |

### 5.11 `audit_logs`

| Column | Type | Constraints | Comment |
|---|---|---|---|
| `id` | UUID | PK, default `gen_random_uuid()` | |
| `actor_user_id` | UUID FK → `users.id` | NULL for system‑generated events | |
| `action` | TEXT | e.g. `upload`, `permission_grant`, `retrieval`, `summary_generate` | |
| `resource_type` | TEXT | e.g. `document`, `chunk`, `conversation` | |
| `resource_id` | UUID | | |
| `ip` | INET | | |
| `user_agent` | TEXT | | |
| `metadata` | JSONB | | Free‑form; e.g. chunk count, score threshold |
| `created_at` | TIMESTAMPTZ | DEFAULT now() | |

### 5.12 `embedding_model_config`

A tiny config table (or env + static dict) tracking which model produces which dims and what the abstention threshold is:

| Column | Type | Constraints |
|---|---|---|
| `model_id` | TEXT PK | e.g. `titan-v2`, `bge-m3` |
| `dimensions` | INTEGER | 1024 |
| `abstention_score_threshold` | REAL | cosine similarity; chunks below this are excluded from the prompt |
| `supports_structured_extraction` | BOOLEAN | |

---

## 6. AWS Integration & Config‑Driven Ports

Every AWS‑backed service is behind a **protocol** so the active implementation can be swapped by changing one env var. This satisfies the brief ("Use AWS services where they provide genuine value. Do not introduce unnecessary services or architectural complexity") while also protecting the demo from sandbox credential delays.

### 6.1 `config.py` — config‑driven selection

```python
import os
from enum import StrEnum

class StorageImpl(StrEnum):
    S3 = "s3"
    LOCAL = "local"

class ExtractorImpl(StrEnum):
    TEXTRACT = "textract"
    PDFPLUMBER = "pdfplumber"

class EmbedderImpl(StrEnum):
    TITAN_V2 = "titan-v2"
    BGE_M3 = "bge-m3"

class LlmImpl(StrEnum):
    BEDROCK_CONVERSE = "bedrock-converse"
    EXTRACTIVE = "extractive"

def get_storage_impl() -> StorageImpl:
    return StorageImpl(os.getenv("STORAGE_IMPL", "s3"))

def get_extractor_impl() -> ExtractorImpl:
    return ExtractorImpl(os.getenv("EXTRACTOR_IMPL", "textract"))

def get_embedder_impl() -> EmbedderImpl:
    return EmbedderImpl(os.getenv("EMBEDDER_IMPL", "titan-v2"))

def get_llm_impl() -> LlmImpl:
    return LlmImpl(os.getenv("LLM_IMPL", "bedrock-converse"))
```

### 6.2 Implementation Classes (sketch)

| Protocol | AWS impl (boto3) | Local impl |
|---|---|---|
| **StoragePort** | `boto3.client("s3")` → `put_object`, `get_object`, `generate_presigned_url`, `head_object` | `pathlib.Path` read/write; `uploads/` dir under `backend/` |
| **ExtractorPort** | `textract.client.start_document_analysis(...)`, poll `get_document_analysis` with waiter; or `start_document_text_detection` + `get_document_text_detection`. Async via job_id + SNS or simple polling loop (timeout 120s). | `pypdf.PdfReader` → page text; or `pdfplumber.open(pdf_path).pages[n].extract_text()`. |
| **EmbedderPort** | `bedrock-runtime.invoke_model(modelId="amazon.titan-embed-text-v2:0", body=json)` → 1024‑dim float list. Batch in groups of 25. | `sentence‑transformers.SentenceTransformer("BAAI/bge-m3")` → encode(texts) → 1024‑dim. (needs ~2.3 GB download, works on CPU; first‑run cached by uv.) |
| **LlmPort** | `bedrock-runtime.converse(model_id=..., messages=[...], system=[...], inference_config={...})` → streaming text + citations `[n]`. Converse automatically handles tool use / structured output when configured. | **Extractive fallback** — only activated when Bedrock credentials are genuinely absent. After retrieval, if the top‑K chunks are judged to contain the answer surface (via a lightweight keyword + semantic match), the answer is assembled server‑side from those chunks + citations, without calling the LLM. This guarantees TEST 5 (honest "not in archive") and provides a deterministic path when Bedrock is unavailable. The primary path remains Bedrock Converse; the fallback is not a "mock", it is a real, bounded retrieval-to-answer pipeline. |
| **JobRunnerPort** | SQS queue → Lambda function that does Textract‑extract → chunk → embed → index. | FastAPI `BackgroundTasks` + `threading.Semaphore` bounded pool. |

### 6.3 Config‑driven runtime

At service start, each module resolves its dependency via `get_*_impl()`:

```python
if get_llm_impl() == LlmImpl.BEDROCK_CONVERSE:
    llm = BedrockConverseLlm(model_id=os.getenv("BEDROCK_MODEL_ID"))
else:
    llm = ExtractiveLlm(retriever)
```

The **default** (approved by user) is **AWS** — S3, Textract, Bedrock embeddings & Converse, bedrock‑provided Cognito. The **fallback** is all‑local, activated automatically when the env lacks valid AWS credentials (boto3 `Session().get_credentials()` raises). This means:

- If the organizer provides real credentials on day 1 → everything runs real.
- If credentials are delayed or incomplete → the app boots in local‑only mode; all functionality works (summaries from local chunks, answers from extracted passages) and can be swapped to real AWS by a single env change.
- No code path ever fakes an AWS call; the adapter pattern makes the real vs. local choice explicit and auditable.

### 6.4 Environment Variables (complete configuration surface)

All configuration is read from the environment; nothing is hardcoded and no secret is ever shipped to the frontend.

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `DATABASE_URL` | ✅ | — | PostgreSQL connection string (must have `vector` extension available) |
| `JWT_SECRET` | ✅ | — | HS256 signing key (≥32 random bytes) |
| `JWT_ACCESS_TTL_MIN` / `JWT_REFRESH_TTL_DAYS` | — | `30` / `7` | Token lifetimes |
| `AWS_REGION` | ✅ (AWS) | `af-south-1` | Region for all AWS clients |
| `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` / `AWS_SESSION_TOKEN` | ✅ (AWS) | — | Sandbox credentials from the organizer (never committed) |
| `S3_BUCKET_NAME` | ✅ (AWS) | — | Document originals |
| `S3_KMS_KEY_ID` | ✅ (AWS) | — | SSE‑KMS key for originals |
| `BEDROCK_MODEL_ID` | ✅ (AWS) | `anthropic.claude-3-5-sonnet-20241022-v2:0` | Answer generation |
| `BEDROCK_EMBED_MODEL_ID` | ✅ (AWS) | `amazon.titan-embed-text-v2:0` | Embeddings (1024 dims) |
| `STORAGE_IMPL` | — | `s3` | `s3` \| `local` |
| `EXTRACTOR_IMPL` | — | `textract` | `textract` \| `pdfplumber` |
| `EMBEDDER_IMPL` | — | `titan-v2` | `titan-v2` \| `bge-m3` |
| `LLM_IMPL` | — | `bedrock-converse` | `bedrock-converse` \| `extractive` |
| `MIN_SCORE` | — | `0.30` | Abstention threshold (cosine) |
| `TOP_K` | — | `6` | Retrieval depth |
| `MAX_UPLOAD_MB` | — | `50` | Upload size guard |
| `ALLOWED_MIME_TYPES` | — | `application/pdf,image/png,image/jpeg,application/vnd.openxmlformats-officedocument.wordprocessingml.document` | Magic‑byte + MIME validation |
| `CORS_ORIGINS` | — | `http://localhost:3000` | Frontend origin allow‑list |

`.env.example` ships with every key present and blank/placeholder values; `.env` is gitignored.

### 6.5 S3 + SSE‑KMS + Presigned URLs

- **Upload flow**: user → `/api/v1/documents/upload` (multipart, auth‑checked) → backend validates MIME + size → `s3.put_object(Bucket, Key, Body, ServerSideEncryption="aws:kms", SSEKMSKeyId=...)` → `ingestion_jobs` queued → response `202 Accepted` + job ID.
- **Download / preview**: backend first checks `document_permissions` for the requesting user; if authorized, issues `s3.generate_presigned_url("get_object", Params={...}, ExpiresIn=60)`. The URL is returned to the frontend; the browser fetches it directly (S3 serves). No raw S3 key ever appears in frontend JS.
- **Preview**: for PDFs, the backend can render the first page as a PNG (via `pdf2image` local fallback or Textract `START_DOCUMENT_IMAGE` feature) and serve that as a base64 data‑uri (≤2 MB) within the 60‑second TTL; otherwise a "download" button that issues a fresh presigned URL after re‑checking permissions.

---

## 7. Security & Permission Model (the core judging requirement)

### 7.1 Retrieval SQL — the security boundary

The single SQL query that powers every question‑answer uses a **CTE that resolves the user's permitted document set** before any vector work:

```sql
-- given :user_id (uuid), :role (user_role), :qvec (float[] 1024), :top_k (int), :embed_model (text)
WITH permitted AS (
  -- 1. Role‑based + user‑based grants, also admin bypass
  SELECT d.id
  FROM documents d
  WHERE d.status = 'ready'
    AND (
      -- admin sees everything
      EXISTS (
        SELECT 1 FROM users u
        WHERE u.id = :user_id AND u.role = 'admin'
      )
      OR EXISTS (
        -- user‑specific grants
        SELECT 1 FROM document_permissions p
        WHERE p.document_id = d.id
          AND p.grantee_type = 'user'
          AND p.grantee_id = :user_id
          AND p.permission IN ('view','download','manage')
      )
      OR EXISTS (
        -- role‑based grants (e.g. "analyst" can view all analyst‑scoped docs)
        SELECT 1 FROM document_permissions p
        WHERE p.document_id = d.id
          AND p.grantee_type = 'role'
          AND p.grantee_role = :role
          AND p.permission IN ('view','download','manage')
      )
    )
)
SELECT
  c.id, c.document_id, c.text, c.page_start, c.page_end,
  1 - (c.embedding <=> CAST(:qvec AS vector)) AS score,
  d.filename, d.doc_type, d.expiry_date
FROM document_chunks c
JOIN permitted p ON p.id = c.document_id   -- <-- security boundary: only permitted docs join
JOIN documents d ON d.id = c.document_id
WHERE c.embedding_model = :embed_model
ORDER BY c.embedding <=> CAST(:qvec AS vector)
LIMIT :top_k;
```

**Why this works:**

1. **Unauthorised chunks never leave PostgreSQL.** The `permitted` CTE is the sole gate; the outer `JOIN permitted p ON p.id = c.document_id` eliminates any chunk whose document is not in the user's grant set.
2. **The model prompt contains only authorised text.** After this query, the Python app maps each row → extracts `text` → builds the system prompt + context for Bedrock Converse. No chunk_id that passed the SQL filter is omitted; none that failed ever reaches the model.
3. **Defence‑in‑depth application‑level re‑validation.** The Python service iterates the result rows and re‑checks `document_permissions` for each `document_id` + `user_id` before placing the text in the prompt (guards against a future bug where the SQL CTE is accidentally changed). This is a second gate, not the primary one.
4. **`embedding_model = :embed_model`** prevents mixing vector spaces if the embedding provider is swapped mid‑lifecycle. The column records the model name; the query explicitly filters by it.

### 7.2 Abstraction / Honesty guard

- **Score threshold**: after the SQL query, the app checks the top‑K score. If `max_score < MIN_SCORE` (configurable, default cosine 0.30 for Titan; empirically derived), the system **short‑circuits** without calling Bedrock and returns:

  > "The archive does not contain sufficient evidence to answer this question. Would you like me to search for a different phrasing or summarise a specific document instead?"

- **Structured‑output guard**: the system prompt instructs the model:

  > "If the context does not contain the answer, say so explicitly. Output a JSON object with fields `{ answer: string, found: boolean, citations: [integer] }`. If `found` is false, do not include `answer` or `citations`."

  The app parses this JSON; if `found` is false → return the honest‑abstention message above. This makes TEST 5 deterministic (no model‑side hallucination).

- **Citation validation**: every `[n]` marker in the model's answer is mapped to the chunk index `n` from the retrieval result. If `n` is out of range or the corresponding chunk's `document_id` fails the permission re‑check → the citation is dropped from the final answer and a warning is logged.

### 7.3 "Never send unauthorised document content to the model"

The retrieval SQL CTE is the **single source of truth** for what the model sees. The Python code path is:

1. Resolve `:user_id` + `:role` from the JWT session.
2. Execute the `permitted` CTE query.
3. If zero permitted rows → return "The archive does not contain any documents you can access."
4. If rows exist → build the Bedrock Converse system prompt:

   ```
   <system>
   You are a helpful assistant for an enterprise document intelligence platform.
   Answer the user's question using ONLY the provided context below.
   If the context does not contain the answer, say so explicitly.
   Cite each factual claim with [n] referencing the context passage index.
   </system>
   ```
5. Pass `documents_text = "\n\n".join(chunk_texts)` as the ``context`` parameter.
6. Send the request to Bedrock Converse.
7. Parse the response JSON (`found`, `answer`, `citations`).
8. Validate every citation index against the retrieval result set + permission re‑check.
9. Return the answer + citation panel to the user.

If at any step the user lacks permission → the CTE yields zero rows and step 3 fires. This is the **guarantee** the judges test for TEST 4.

### 7.4 Admin‑only operations

- `POST /admin/permissions` — grant/revoke `view|download|manage` per document per user/role.
- `GET /admin/audit` — full audit log, filterable by user, action, resource, date range.
- `POST /admin/reindex` — rebuild HNSW index, re‑embed all chunks (run after batch ingestion).

---

## 8. API Surface (FastAPI, `/api/v1`)

### 8.1 Auth

| Method | Endpoint | Description |
|---|---|---|
| `POST /auth/login` | `{email, password}` → JWT `access_token` + refresh token | Argon2id‑verified; returns `token_type, expires_in, user` |
| `POST /auth/refresh` | `{refresh_token}` → new access token | Rotates refresh token; short TTL (7d) |
| `GET /auth/me` | — | Returns current user: `id, email, role` |

### 8.2 Documents

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| `GET /documents` | — | user | List documents the user can view (filtered by `document_permissions`). Supports `?doc_type=lease&status=ready`. |
| `GET /documents/{id}` | — | user | Document metadata + extracted_metadata + status. |
| `GET /documents/{id}/preview` | — | user | **Secure**: backend re‑checks permission, then returns either (a) first‑page PNG (if available) or (b) a 60‑second presigned S3 URL (as JSON `{download_url: "..."}`) for the browser to fetch. |
| `GET /documents/{id}/download` | — | user | Same as preview — backend checks permission → issues fresh presigned URL → browser downloads original. |
| `POST /documents/upload` | `multipart/form-data` (file) | user | Validates MIME + size (<50 MB per doc). Creates `ingestion_jobs` row (status `queued`). Returns `{job_id}`. |
| `GET /ingestion/jobs/{id}` | — | user | Returns job status + progress. |
| `POST /documents/{id}/reindex` | — | admin | Re‑embed the document's chunks (run if embedding model changes). |
| `POST /documents/{id}/summary` | — | user | Generate / retrieve cached summary (see §9). |

### 8.3 Chat / RAG

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| `POST /chats` | `{title?}` | user | Creates a new conversation; returns `{conversation_id}`. |
| `GET /chats` | — | user | List conversations for the user. |
| `GET /chats/{id}` | — | user | Retrieve conversation + message history (SSE‑streamable). |
| `POST /chats/{id}/messages` | `{content}` | user | Sends a user message; triggers the **RAG pipeline** (retrieve → generate → stream) → returns `{message_id}` + immediate SSE `text/event-stream` response that the frontend opens. |
| `POST /chats/{id}/messages/rewrite` | `{new_content}` | user | LLM‑rewrite the query into a standalone form (optional, cheap, used for follow‑ups). |

### 8.4 Search (library view)

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| `GET /search` | `?q=<text>&doc_type=lease&expiry_before=2027-12-31&limit=20` | user | Hybrid search: (a) vector similarity with permission filter, (b) trigram `pg_trgm` similarity on `text` column for keyword fallback, (c) structured metadata filters (`doc_type`, `expiry_date`). Returns `{results: [{chunk, score, document, excerpt}]}`. |

### 8.5 Admin

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| `GET /admin/users` | — | admin | Table of all users: `id, email, role, is_active, created_at`. |
| `POST /admin/users` | `{email, role, password}` | admin | Create user; password is argon2id‑hashed before storage. |
| `POST /admin/permissions` | `{document_id, grantee_type, grantee_id/role, permission}` | admin | Grant/revoke a permission entry. |
| `GET /admin/audit` | — | admin | Paginated audit log. |
| `GET /admin/stats` | — | admin | Counters: total documents, indexed chunks, active conversations, today's retrieval count. |

### 8.6 SSE Streaming (chat answer delivery)

The `POST /chats/{id}/messages` endpoint returns a **`200 OK`** with `Content-Type: text/event-stream` and a body of newline‑separated JSON events:

```
{"type": "token", "delta": "The "}
{"type": "citation_start", "index": 3}
{"type": "token", "delta": " lease"}
{"type": "citation_end", "index": 3}
{"type": "token", "delta": " expires "}
{"type": "finish", "message_id": "...", "found": true}
```

The frontend accumulates tokens, renders them as they arrive, and inserts citation chips at `citation_start`/`citation_end` events. When `finish` arrives, the citation panel is populated with the resolved document links (re‑checked permission at render time).

---

## 9. Ingestion & RAG Pipeline

### 9.1 Upload → Index Flow (high‑level)

```
User uploads PDF → /api/v1/documents/upload (auth checked)
  │
  ▼
Backend validates MIME / size → stores original in S3 (SSE‑KMS)
  │
  ▼
Creates ingestion_jobs row (status=queued, stage=init)
  │
  ▼
Background task (FastAPI BackgroundTasks / thread‑pool) processes the job:
  │
  ──▶ Extract text
       • If get_extractor_impl() == TEXTRACT: call Textract StartDocumentAnalysis
         (FeatureTypes=[TABLES,FORMS,LAYOUT,QUERIES,SIGNATURES])
         Poll get_document_analysis until SUCCEEDED or timeout 120s.
       • Else (local PdfPlumberAdapter): pypdf + pdfplumber for digital PDFs.
       • Result: raw text string + page mapping.
  │
  ──▶ Chunk text
       • Structure‑aware: detect heading lines (`\d+\.\\s+[A-Z]`, all‑caps centred, PDF‑form font‑size jumps).
       • Chunk size: ~800–1200 tokens, 100‑token overlap.
       • Each chunk carries: `page_start`, `page_end`, `heading_path[]`.
       • Store chunk rows + `embedding_model = :current_model`.
  │
  ──▶ Extract structured metadata (bedrock or local LLM, one‑shot)
       • Prompt: "Extract the following fields from the document: doc_type, parties[], effective_date, expiry_date, term_years, total_value_currency, governing_law, signatory_names."
       • Result stored in `documents.extracted_metadata` jsonb + typed columns (`expiry_date`, `doc_type`).
       • For TEST 1 reliability: the `expiry_date` is guaranteed by the regex pre‑pass + LLM enrichment.
  │
  ──▶ Embed chunks
       • Call `embedder` (Titan V2 or bge‑m3) on each chunk's `text` → 1024‑dim float list.
       • Insert `document_chunks` rows.
  │
  ──▶ Build HNSW index (pgvector)
       • If index does not exist: `CREATE EXTENSION vector;`
       • `CREATE INDEX IF NOT EXISTS ... USING hnsw ...`
       • `SET hnsw.ef_search = 40;` per session.
  │
  ──▶ Update document status
       • `documents.status = 'ready'`, `indexed_at = now()`.
  │
  ──▶ Mark job succeeded.
```

**Failure handling**: each stage writes its error into `ingestion_jobs.error`; the job status becomes `failed`; the admin can re‑run `POST /documents/{id}/reindex` or the user can re‑upload.

### 9.2 Metadata extraction — TEST 1 reliability

The "which lease agreements expire next year?" test depends on **deterministic** `expiry_date` presence, not RAG luck. Pipeline:

1. **Regex pre‑pass** on the extracted text: `r'(?P<expiry>\d{1,2}\s+(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4})'` — captures dates like "31 December 2027".
2. If a regex match is found → store as `documents.expiry_date` (DATE type) and also in `extracted_metadata`.
3. If no regex match (complex layout) → invoke Bedrock LLM with a JSON‑schema prompt to extract `expiry_date`.
4. If LLM also fails → mark `extracted_metadata->>'expiry_date'` as NULL and flag the document for manual review.

Because the synthetic corpus is generated under our control, we ensure every lease doc has a parseable date via step 1 or 2. This makes TEST 1 a **deterministic SQL query** rather than a probabilistic RAG hit. "Next year" is resolved **server-side** against the current date (never by the model, which would have to guess the year):

```sql
-- "next year" = the calendar year after the current one (e.g. 2027 when run in 2026)
SELECT filename, expiry_date
FROM documents
WHERE doc_type = 'lease'
  AND expiry_date >= date_trunc('year', current_date) + interval '1 year'
  AND expiry_date <  date_trunc('year', current_date) + interval '2 years';
```

The RAG answer then **cites** specific lease docs from this SQL set, and the model's answer references them. This hybrid approach (structured metadata + RAG citations) is what makes TEST 1 reliably pass.

### 9.3 RAG retrieval (user request)

When a user sends a message:

1. **Resolve principal**: `:user_id`, `:role` from JWT.
2. **Execute permitted CTE** (SQL from §7.1) → get list of allowed `document_id`s.
3. If zero → return "You don't have access to any documents in the archive."
4. **Build query vector** from the user's question:
   - Use the **selected embedder** (Titan V2 via Bedrock, or bge‑m3 locally) to encode the question text → `:qvec`.
   - (Optional) Expand with query‑rewriting LLM call (cheap, optional; for follow‑ups).
5. **Run the retrieval query** (see §7.1) → rows with `score` and `text`.
6. **Post‑retrieval filter**: Python iterates rows, re‑checks `document_permissions` for each `document_id` (defence in depth). Dropping any that fail (shouldn't happen if the CTE is correct, but safe).
7. **Select top‑K** (default K=6; adjustable). If `max_score < MIN_SCORE` → skip Bedrock call, return honest abstention (TEST 5 path).
8. **Build Bedrock Converse prompt**:
   - System prompt (see §7.2).
   - `context` = concatenation of the `text` fields (ordered by rank).
   - User message = the original question.
9. **Call Bedrock Converse** → streamed response with `[n]` citations.
10. **Parse JSON** (`found`, `answer`, `citations`).
11. **Validate citations**: each `[n]` maps to the chunk at position `n` in the retrieval result. If invalid → drop citation, log warning.
12. **Persist**: `INSERT INTO messages ...`, `INSERT INTO citations ...`, `INSERT INTO retrieval_evidence ...`.
13. **Stream response** back to frontend via SSE (see §8.6).
14. **User sees** answer + citation panel; each citation is a clickable link to the document preview (permission‑checked).

### 9.4 Summarisation (per‑document)

Two paths:

- **Cache path**: `GET /documents/{id}/summary` → check `document_summaries` table. If a summary exists for this `document_id` + `model` → return it immediately.
- **Generate path**: If no cache → invoke Bedrock Converse with a map‑reduce style prompt:

  ```
  <system>
  Summarise the following document pages in 3–5 bullet points.
  Include page ranges for each bullet. Cite [n] references.
  If information is missing, say so.
  </system>
  <user>
  {all chunk texts for this document, ordered by page_start}
  </user>
  ```

  Result stored in `document_summaries` + `summary` field; cached for future requests.

- **Follow‑up summarisation**: user can ask "summarise pages 3‑5 of this contract" → the system filters chunks by `page_start/page_end` and re‑generates a targeted summary.

---

## 10. Design System & UI

### 10.1 Visual Tokens (Tailwind v4 config)

```css
:root {
  --color-charcoal: #171A1D;
  --color-concrete: #F3F1EC;
  --color-steel: #8A9095;
  --color-copper: #B9784B;
  --color-aws-orange: #FF9900;
  --color-aws-slate: #212529;
}
@media (prefers-color-scheme: dark) {
  :root {
    --color-charcoal: #F5F5F0;
    --color-concrete: #1A1A1A;
    --color-steel: #474A51;
    --color-copper: #D4A853;
  }
}
body { background: var(--color-concrete); color: var(--color-charcoal); }
```

### 10.2 UI Layout (key screens)

| Screen | Layout | Key components |
|---|---|---|
| **Dashboard** | Two‑card overview + quick‑ask bar + recent activity | `StatsCard`, `QuickAskInput`, `ActivityFeed` |
| **Assistant workspace** | Split: left = chat pane (SSE‑streaming answer + citation chips); right = Evidence panel (retrieved passages with page refs, permission badges, "open doc" buttons) | `Composer`, `MessageList`, `AnswerBlock`, `CitationChip`, `EvidencePanel`, `FollowUpBar` |
| **Library** | Table of documents with filters (type, status, date range), upload dropzone, status pills | `DocumentTable`, `UploadDropzone`, `StatusPill`, `DocumentFilters` |
| **Document preview** | Top = metadata + extracted fields; Middle = secure preview (PNG first page or download button); Bottom = summary + citations | `MetadataPanel`, `PagePreview`, `SummaryPanel`, `CitationList` |
| **Admin** | Users table + permission matrix + audit log + reindex button | `UserTable`, `PermissionMatrix`, `AuditTable`, `ReindexButton` |

### 10.3 Interaction patterns

- **Citation chips**: when the user clicks `[1]`, the Evidence panel scrolls to that passage and highlights it; a "Open document → page X" badge appears (permission‑checked; disabled if user lacks `download` permission).
- **Follow‑up**: the chat input sends the new question; the system **preserves** the prior retrieval set as "sticky context" (if the new query's vector score is lower, we re‑run retrieval; if higher, we keep the prior set and re‑rank). This makes multi‑turn feel coherent without re‑sending the whole history to the model (though we do send last N turns for context).
- **Abstention**: if the model says it does not know (TEST 5), the answer panel shows a bright‑yellow banner: "The archive does not contain information to answer this question. Try re‑phrasing or selecting a specific document."

### 10.4 Frontend tech stack (as part of the overall stack)

- **Next.js 15+ App Router** — `src/app/` routes as listed above.
- **TypeScript** — end‑to‑end typings from OpenAPI (backend generates schema → `openapi-typescript-codegen` → `src/lib/api.ts` typed client).
- **Tailwind v4** — design tokens as in §10.1; all components live in `src/components/`.
- **React Query** — server‑state caching for documents, jobs, user permissions.
- **SSE client** — `src/lib/sse.ts` tiny wrapper that connects to `/chats/{id}/messages` SSE endpoint, buffers tokens, emits `onToken`, `onCitationStart/End`, `onFinish` callbacks.
- **React Hook Form + Zod** — forms (login, upload, permission grants).
- **Lucide React** — icons.
- **No external UI libraries** beyond Lucide; keep the build lightweight for the 30‑hour clock.

---

## 11. Module Breakdown & Execution Roadmap (30h)

| Phase | Hours | Deliverable | Critical Path |
|---|---|---|---|
| **P0 — Foundations** | 1h | Repo init (`git init`), `pyproject.toml`, `next.config.ts`, env template (`.env.example`), **managed Postgres provision** (Neon/Supabase sign‑up + pgvector enable — **user-assisted**, browser step), **AWS sandbox credential intake** (collect organizer‑provided details, set env vars — **user-assisted**). | ✅ Environment must be runnable by hour 1. |
| **P0 — Data layer** | 2.5h | Alembic + models (`users`, `documents`, `document_chunks`, `document_permissions`, `conversations`, `messages`, `citations`, `retrieval_evidence`, `ingestion_jobs`, `document_summaries`, `audit_logs`). First migration `001_base.sql`. Seed: ~10 synthetic docs (lease, contract, policy, invoice, nda) with known dates/parties + chunks + embeddings (pre‑embedded via script). | ✅ DB + seed must be alive before ingestion runs. |
| **P0 — Auth + RBAC** | 2h | JWT auth flow (`login`, `refresh`, `me`); argon2id hashing; role enum + `document_permissions` CRUD via `POST /admin/permissions`; JWT middleware (`fastapi.security.HTTPBearer`). | ✅ Without auth, nothing else is scoped. |
| **P0 — Ingestion pipeline** | 4h | Upload endpoint + background job + Textract adapter (or local PdfPlumber fallback) → text extraction → structure‑aware chunking → metadata extraction (regex + LLM) → embed → HNSW index → document status → job status API. | ⭐ The **single biggest risk**; if this isn't working by hour 6, we’re in trouble. |
| **P0 — RAG core** | 5h | Retrieval SQL with `permitted` CTE → top‑K → Bedrock Converse generation → SSE streaming → citation validation → abstention guard. Unit tests: permission matrix (4 scenarios: admin‑all, analyst‑some, viewer‑one, no‑access). | ✅ This is the **judge‑critical** module. Must be solid by hour 11. |
| **P0 — Frontend skeleton** | 3.5h | Next.js app skeleton + design tokens + login page + dashboard + assistant workspace layout (split chat + evidence). Minimal styling, just the charcoal/concrete/copper palette + AWS‑orange accents. | ✅ Frontend must be connectable to the backend by hour 15. |
| **P1 — Library & preview** | 2.5h | Document list page + upload dropzone + secure preview/download (presigned URLs + permission re‑check). | — |
| **P1 — Summarisation** | 1.5h | Per‑document summary endpoint + cached fallback + UI “summarise” button. | — |
| **P1 — Admin & audit** | 2.5h | Users CRUD + permission matrix + audit log view + reindex button. | — |
| **P0 — Demo hardening** | 3h | **All 5 scenarios end‑to‑end**: (1) lease expiry query with citations, (2) contract summary, (3) citation click → preview, (4) two‑user different answers (create two users, grant different permissions, ask same question), (5) honest "not in archive". Validation script that asserts each. | ⭐ The **definition of done**; no demo = no pass. |
| **Buffer** | 2.5h | Contingency, polishing README, deployment notes, final run‑through. | — |
| **Total** | **≈27.5h** + **2.5h buffer** = **30h** | | |

**Phase priorities (hard gate):** P0 must deliver the five demo scenarios + security boundary. P1 can be deferred if time runs short; the judges only test the 5 demos.

### 11.1 Module inter‑dependencies (critical path)

```
repo init → DB + seed → Auth → Ingestion → RAG retrieval → Frontend connect → 5 demos
```

If any upstream blocker, downstream cannot proceed. The **ingestion pipeline** is the single point of failure — if Textract/local extraction fails, no documents = no RAG = no demos. That's why the local fallback (PdfPlumber) is essential and why the design stresses `get_extractor_impl()` selection.

### 11.2 Risks & Mitigations (expanded from §11)

| # | Risk | Mitigation |
|---|---|---|
| 1 | **AWS sandbox credentials delayed or incomplete** | Ports + config‑driven fallbacks auto‑activate. The app boots in local‑only mode; ingestion uses PdfPlumber; RAG uses extractive fallback (answer from retrieved passages only). By end of P0, we have a working demo even without AWS. |
| 2 | **pgvector recall drops when ACL filter is very selective** | Empirical test: seed 3 docs → verify recall with/without filter. If < 80% at K=6, add `hnsw.iterative_scan = strict_order` and/or increase `ef_search` to 100. Also fallback: over‑fetch K=10, filter in Python, return top‑6. |
| 3 | **Textract async timeout / quota error** | Poll with exponential backoff, max 3 attempts. If all fail, mark job `failed` and automatically switch to local PdfPlumber for that doc (the extractor impl can be swapped per‑document via config). |
| 4 | **Embedding model quota on Bedrock** | Titan Embeddings V2 is typically high‑quota; but if exceeded, fall back to bge‑m3 locally (both 1024‑dim, same index). |
| 5 | **Bedrock Converse model not available in region** | Config‑driven `BEDROCK_MODEL_ID`; pre‑install a list of fallbacks (`anthropic.claude-3-5-sonnet-20241022-v2:0`, `anthropic.claude-3-haiku-20240307-v1:0`). If none work → extractive fallback (no model call). |
| 6 | **Scope creep in UI** | The 5 demo scenarios are the **definition of done**. Any UI work beyond the 5 core screens is postponed to the 2h buffer. |
| 7 | **Postgres free‑tier connection‑pool exhaustion** | Use `psycopg` with `min_connection_idle=30, max_connections=20`; the demo has ≤5 concurrent users. |
| 8 | **Windows dev friction (no Docker, no Postgres installed)** | Managed Postgres (Neon/Supabase) → single `DATABASE_URL`, no local service needed. All other services (S3, Textract, Bedrock) are cloud‑only; the local fallbacks mean the app runs anywhere. |
| 9 | **Cognito setup eating time** | Self‑managed JWT default (see §3). Cognito adapter is a **documented, optional** swap‑in if the organizer provides a user pool and there's time. The spec explicitly notes this deviation and its rationale. |
| 10 | **Prompt‑inject / hallucination in model answer** | Structured‑output guard + score‑threshold abstention + citation validation make hallucination practically impossible. Audit logs record every retrieval + score for post‑mortem. |

### 11.3 Testing strategy

- **Backend pytest suite**: permission matrix (4 access levels × 3 doc types), retrieval ACL filter (top‑K with/without filter), abstention guard (score < threshold → no model call), metadata extraction correctness (known synthetic corpus), ingestion job lifecycle (queued → running → succeeded/failed).
- **Frontend tests**: Next.js component unit tests (vitest + react‑testing‑library) for citation chip render, EvidencePanel permission badge state, upload form validation.
- **Demo validation script** (run after P0): a small Python script that (a) creates two users, (b) grants different permissions, (c) asks each the 5 test questions, (d) asserts correct answers/citations for each, (e) asserts honest abstention for a random question. This script is the **golden test** the team runs before the live demo.

---

## 12. Design System Tokens (for the UI)

| Token | Light | Dark |
|---|---|---|
| `color-charcoal` | `#171A1D` | `#F5F5F0` |
| `color-concrete` | `#F3F1EC` | `#1A1A1A` |
| `color-steel` | `#8A9095` | `#474A51` |
| `color-copper` | `#B9784B` | `#D4A853` |
| `color-aws-orange` | `#FF9900` | `#FFB347` (a slightly muted tone for dark) |
| `color-white` | `#FFFFFF` | `#FFFFFF` (unchanged) |
| `font-base` | `Inter, system-ui, sans-serif` | same |
| `font-mono` | `JetBrains Mono, SF Mono, monospace` | same |
| `radius-sm` | `0.375rem` | same |
| `radius-md` | `0.5rem` | same |
| `shadow-sm` | `0 1px 2px 0 rgba(0,0,0,0.05)` | `0 1px 2px 0 rgba(0,0,0,0.1)` |
| `transition-fast` | `color 0.15s ease, border-color 0.15s ease` | same |

These tokens live in `frontend/src/styles/globals.css` and are referenced via Tailwind `@apply` or custom utilities. The **hybrid** identity (charcoal/concrete/copper base + AWS‑orange accents on AWS surfaces) is the approved design choice from the user's clarification.

---

## 13. Implementation Gates & Next Steps (after spec review)

1. **User reviews this spec** (the file at `docs/superpowers/specs/2026-11-19-ask-the-archive-design.md`).
2. **If approved** → invoke `superpowers:writing-plans` to produce the hour‑by‑hour implementation plan with per‑task verification checklists.
3. **If changes requested** → edit the spec file, re‑run spec self‑review (check for TBD/TODO, internal consistency, scope), then re‑present for review.
4. **After plan approval** → begin P0 (repo init → DB + seed → auth → ingestion → RAG core).

The spec file is the **single source of truth** for the build; every module, API endpoint, and data‑model decision is documented here, so the implementation can proceed confidently without constant design re‑talk.

---

## 14. Appendix: Synthetic Corpus Seed (for reference)

The seed script (not committed yet) will generate ~10 synthetic documents with realistic civil‑engineering names:

| Name | Type | Expiry | Parties | Key fields |
|---|---|---|---|---|
| `Municipal‑Lease‑2024‑01` | lease | 2027‑12‑31 | City of | `expiry_date=2027‑12‑31`, `parties=["City","Acme Corp"]` |
| `Infrastructure‑Supply‑Contract‑2023` | contract | 2028‑06‑15 | Municipality | `parties=["City","VendorCo"]` |
| `Joint‑Use‑Agreement‑2022` | policy | NULL | N/A | `doc_type=policy` |
| ... | ... | ... | ... | ... |

Each doc is uploaded → Textract/PdfPlumber extracts text → structure‑aware chunking → embeddings (Titan V2) → stored in PG + HNSW. The seed script also populates `document_permissions` so that:

- **User `analyst`** can view all seeded documents.
- **User `viewer`** can view only the policy documents.
- **Admin** can view and manage all.

This seed is what the 5 demo scenarios run against.

---

*End of design specification.*