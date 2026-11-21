# Ask the Archive

AI-powered enterprise document intelligence. Upload a contract, lease, policy or
invoice; ask questions in plain language; get answers that cite the page of the
original document — and an honest "the archive does not contain that" when it
doesn't.

Built for the TDW × AWS Innovation Challenge (19–20 November 2026).

---

## The one idea

Most document chatbots fail in the same way: they answer confidently from
whatever they can find, including text the user was never allowed to read. This
system is built the other way round.

**Permissions are resolved in SQL, before the model is called.** A `permitted`
CTE joins into the pgvector cosine query, so a document the caller cannot read
is never returned to the application layer — it cannot reach the prompt, the
citations, or the screen. A second check in Python re-validates every candidate
before it is allowed into the prompt, so a future mistake in the query cannot
silently leak content either.

Everything else in the system follows from that principle: an answer you cannot
trace is not worth showing, and an answer that would have required content you
may not see is better left unanswered.

---

## Architecture

```
┌──────────────┐   /api/v1 (rewritten, same-origin)   ┌────────────────────┐
│  Next.js 14  │ ────────────────────────────────────▶ │  FastAPI backend   │
│  React + TS  │                                      │                    │
└──────────────┘                                      │  auth · documents  │
        ▲                                             │  retrieval · QA    │
        │  citations ────────────────────────────────▶ │  permissions       │
        │                                             └─────────┬──────────┘
        │                                                       │
        │                              ┌────────────────────────┼──────────────────┐
        │                              ▼                        ▼                  ▼
        │                      ┌───────────────┐      ┌────────────────┐  ┌─────────────┐
        │                      │ PostgreSQL    │      │ local storage  │  │ Bedrock     │
        │                      │ Neon + pgvector│      │ backend/uploads│  │ Nova Lite   │
        │                      │ 1024-dim vec  │      │                │  │ (generation)│
        │                      └───────────────┘      └────────────────┘  └─────────────┘
        │                              ▲
        │                              │  local CPU embedding
        │                      ┌───────────────┐
        └──────────────────────│  BAAI/bge-m3  │
                               │  1024-dim     │
                               └───────────────┘
```

### Why the permission boundary lives in SQL

A filter applied in Python after retrieval is one refactor away from being
wrong. Filtering in the query means the unauthorised row never enters the
process:

```sql
WITH permitted AS (
    SELECT d.id AS document_id FROM documents d WHERE d.uploaded_by = :user_id
    UNION
    SELECT dp.document_id FROM document_permissions dp
    WHERE dp.permission IN ('view','download','manage')
      AND ( (dp.grantee_type='user' AND dp.grantee_user_id=:user_id)
            OR (dp.grantee_type='role' AND dp.grantee_role=:role) )
)
SELECT ... FROM document_chunks c
JOIN documents d ON d.id = c.document_id
JOIN permitted p ON p.document_id = c.document_id   -- ← the boundary
WHERE c.embedding_model = :model
ORDER BY c.embedding <=> CAST(:qvec AS vector)
LIMIT :top_k
```

### Why some answers are computed, not generated

"Lease agreements expiring next year" is answered from the `expiry_date`
column by a deterministic query, never by asking a model to read dates out of
prose. The expiry date itself is extracted by a rule-based pass that will only
accept a date that appears in the text attached to an expiry keyword — a model
may refine the result, but it can never invent one.

The consequence is that the demo answer is exact, not approximately right.

---

## Running it

### Prerequisites

- Python 3.11+ · Node 20+
- A PostgreSQL database with the `vector` extension (Neon works; the schema is
  created by Alembic)

### Backend

```bash
cd backend
python -m venv .venv && ./.venv/Scripts/python -m pip install -e ".[dev]"
cp .env.example .env        # then fill it in — see below
./.venv/Scripts/python -m alembic upgrade head
./.venv/Scripts/python -m uvicorn app.main:app --reload --port 8000
```

`backend/.env` is where every credential lives. It is git-ignored and must
never be committed, never echoed, and never read by the frontend.

### Frontend

```bash
cd frontend
npm install
npm run dev                 # http://localhost:3000
```

The browser talks only to the backend through a same-origin rewrite. It never
holds an AWS key, a database URL, or any other secret.

### Seed the demo archive

```bash
cd backend
./.venv/Scripts/python -m scripts.seed
```

Generates 11 realistic PDFs, extracts and classifies them, embeds them with
bge-m3, and applies the role-based permission matrix.

| Email | Password | Role | Can read |
|---|---|---|---|
| `admin@archivedemo.example.com` | `Archive!2026` | admin | everything, including the NDA |
| `analyst@archivedemo.example.com` | `Archive!2026` | analyst | leases, contracts, invoice, survey, MOU |
| `viewer@archivedemo.example.com` | `Archive!2026` | viewer | the two policies, two leases, the survey |

The NDA (`aurora-mutual-nda.pdf`) is deliberately admin-only, and
`northgate-warehouse-lease.pdf` is analyst-only — these are what make the
permission test meaningful.

---

## The five demo tests

| # | Test | How it is satisfied |
|---|---|---|
| 1 | Lease agreements expiring next year | Deterministic query over `expiry_date`, scoped by the same ACL. Two leases expire in 2027; one in 2026. |
| 2 | Summary of a selected contract | Map-reduce summarisation over the document's own chunks, cached in `document_summaries`. |
| 3 | Citation opens the original document | Every citation carries `document_id` + page range; the UI opens the extracted text of that page in the document view. |
| 4 | Two users, same question, different answers | The retrieval CTE filters by role before ranking. Ask as `analyst` and `viewer` and the answers differ — and neither leaks the other's documents. |
| 5 | Honest "I don't know" | A similarity floor (`MIN_SCORE`) plus a `NO_ANSWER` sentinel plus citation-index validation. If the archive does not contain it, the system says so. |

---

## Security posture

| Constraint | How it is met |
|---|---|
| Enforce permissions before retrieval | `permitted` CTE joined into the pgvector query; `filter_by_permission` re-checks in Python. |
| Never send unauthorised content to the model | Unauthorised rows never leave the database. The prompt is built only from already-filtered chunks. |
| Prevent cross-user leakage | Every read path — list, preview, download, summary, retrieval, metadata query — resolves through `app/modules/documents/permissions.py`. |
| Protect originals and secure previews | Downloads re-check the `download` capability; the local backend serves originals only through an authenticated, permission-checked route. |
| Least-privilege IAM | The IAM user is scoped to the actions the app performs; see the deviations below for what the sandbox actually permitted. |
| Never expose credentials in the frontend | All secrets live in `backend/.env`. The frontend has only a base URL. |
| Validate uploads and requests | MIME type allow-list, size cap, non-empty check, Pydantic request schemas, and role/permission validation on every mutating route. |

Passwords are hashed with argon2id. Access tokens are short-lived HS256 JWTs;
the frontend keeps them in memory only and exchanges a stored refresh token
for a new one on demand. Every login, permission change, download and answer
attempt is written to `audit_logs`.

---

## AWS sandbox deviations — stated plainly

The brief asks for an AWS-native system. The sandbox provided for this build
has service policies that block several of those services. Rather than mock
them, the affected capabilities were moved to real local implementations and
are listed here with the exact reason.

| Capability | Intended | What actually happened | What we run instead |
|---|---|---|---|
| Textract | `TextractExtractorAdapter` | Explicit IAM deny on every Textract call | **pdfplumber** (local). The adapter exists and is selected by `EXTRACTOR_IMPL=textract` if the policy is ever opened. |
| S3 | `S3StorageAdapter` | `s3:CreateBucket` denied by SCP | **Local storage** (`backend/uploads/`). The adapter exists; `STORAGE_IMPL=s3` switches to it. |
| KMS | `kms:CreateKey` | Denied by SCP | No customer-managed key. S3 uses SSE-S3; nothing else encrypts with KMS. |
| Titan Text Embeddings V2 | 1024-dim embeddings | Throttled on every attempt, including retries 8–40s apart | **BAAI/bge-m3**, local, 1024-dim — the same dimensionality as Titan V2, so the `vector(1024)` schema and HNSW index are unchanged. |
| Claude (3.5 Sonnet / 5 / Haiku 4.5) | Generation | Model not available to this account (`list_foundation_models` returns no Anthropic models) | **Amazon Nova Lite** (`us.amazon.nova-lite-v1:0`) via Bedrock Converse, with a fallback chain (`us.amazon.nova-micro-v1:0`, `meta.llama3-1-8b-instruct-v1:0`, `mistral.mistral-7b-instruct-v0:2`). |

Everything Bedrock-dependent is real and credentialed — the code really calls
Bedrock Converse and really streams. The embeddings are local because Titan's
quota on this account is exhausted; they are not faked.

### The Bedrock daily allowance

The build account carries an account-wide **daily token allowance** on
Bedrock on-demand inference. Once it is spent, every Converse call — on
every model the account can reach — is refused with
`ThrottlingException: Too many tokens per day`. This was verified rather than
assumed:

- `maxTokens=1` is still refused, so it is the allowance and not the request
  size;
- `us.amazon.nova-micro-v1:0` is refused identically;
- `meta.llama3-1-8b-instruct-v1:0` raises a `ValidationException` because it
  needs a regional inference-profile id, and
  `us.meta.llama3-2-11b-instruct-v1:0` is end-of-life;
- `bedrock:ListFoundationModels` shows no Anthropic model this account may use.

An allowance that is spent for the day does not clear by waiting, so the
adapter does not spend a minute retrying it. `BedrockConverseLlmAdapter`:

1. creates its client with `max_attempts=1`, so botocore's adaptive backoff
   does not burn 80 seconds on an error that cannot clear;
2. retries with exponential backoff only the burst throttle
   ("too many requests"), which does clear in seconds;
3. on a daily-allowance refusal, walks the model chain and tries the next
   model rather than the same one again;
4. reports **which** model answered in `LlmResponse.model`, so a degraded
   answer is never presented as a full-strength one.

When no model in the chain can answer, `FallbackLlmAdapter` answers
extractively from the retrieved passages and tags the response
`model="extractive-fallback"`. The answer is then composed from sentences
that genuinely occur in the permitted documents, with `[n]` markers pointing
at the passage each sentence came from, and it abstains when no sentence
supports an answer. It is a weaker answer than a model gives — and it is
labelled as one, in the API response, in the database, and in the UI.

If the allowance is restored, no code change is required: the same adapter
answers with Nova Lite. Likewise, restoring Titan's quota needs
`EMBEDDER_IMPL=bge-m3` → `titan` plus a re-ingest, and nothing else. The
model id is stored per chunk (`document_chunks.embedding_model`), so
embeddings from different models never mix in the same similarity search.

### Degradation is explicit

If Bedrock throttles or denies a generation call, the system does not pretend.
`FallbackLlmAdapter` catches the error, falls back to extractive answering, and
tags the response `model="extractive-fallback"`. A degraded answer is labelled
as degraded rather than passed off as a model's — in the API response, in the
`summaries.model` column, and in the UI.

---

## Layout

```
backend/
  app/
    core/          config, security, dependencies, errors
    db/            engine, session, models, Alembic migration
    modules/
      auth/        login, refresh, me
      documents/   upload, list, preview, download, permissions
      ingestion/   extraction → chunking → classification → embedding
      retrieval/   permission-scoped pgvector search
      chat/        question planning, answering, SSE streaming
      summaries/   map-reduce summarisation
      admin/       users, audit trail, stats
    ports/         storage / extractor / embedder / llm interfaces + AWS & local adapters
    shared/        audit helper
  scripts/         seed_corpus.py (PDF generation), seed.py
  tests/           metadata, chunking, chat planning, permission matrix
frontend/
  src/app/         login, dashboard, assistant, library, document, admin, activity
  src/lib/         api client, auth context, types
  src/components/  shared UI
```

The `ports/` directory is the seam: every external capability (object storage,
text extraction, embeddings, generation) is an interface with a real AWS
implementation and a real local implementation. The application code never
knows which is active.

---

## Tests

```bash
cd backend && ./.venv/Scripts/python -m pytest -q
```

- `test_metadata.py` — document typing, expiry extraction, date formats
- `test_chunking.py` — page-aware chunk boundaries
- `test_chat_planning.py` — deterministic routing of expiry questions
- `test_permissions.py` — the ACL, against a real PostgreSQL database

The permission tests run against the real database rather than a mock, because
the thing being tested *is* the SQL.
