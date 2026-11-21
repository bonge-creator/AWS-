"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { DocumentList, SearchResult } from "@/lib/types";
import { DocTypeChip, PageHeader, StatusDot } from "@/components/ui";

interface Health {
  status?: string;
  providers?: Record<string, string>;
  [k: string]: unknown;
}

const SUGGESTIONS = [
  "Which lease agreements expire next year?",
  "Summarise the Kestrel facilities contract.",
  "What is our data retention period?",
];

export default function DashboardPage() {
  const { user } = useAuth();
  const [docs, setDocs] = useState<DocumentList | null>(null);
  const [health, setHealth] = useState<Health | null>(null);
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<SearchResult | null>(null);
  const [searching, setSearching] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.documents().then(setDocs).catch((e) => setError(e.message));
    api.health().then(setHealth).catch(() => setHealth(null));
  }, []);

  async function runSearch(e: React.FormEvent) {
    e.preventDefault();
    const q = query.trim();
    if (q.length < 2) return;
    setSearching(true);
    setError(null);
    try {
      setHits(await api.search(q, 6));
    } catch (err: any) {
      setError(err.message);
      setHits(null);
    } finally {
      setSearching(false);
    }
  }

  const items = docs?.items ?? [];
  const ready = items.filter((d) => d.status === "ready" || d.status === "indexed");
  const expiring = ready
    .filter((d) => d.expiry_date)
    .sort((a, b) => (a.expiry_date! < b.expiry_date! ? -1 : 1));

  return (
    <div className="grid-field min-h-screen">
      <div className="mx-auto max-w-6xl px-6 py-8">
        <PageHeader
          eyebrow="Overview"
          title={`Good to see you, ${user?.display_name?.split(" ")[0]}`}
          description="Everything below is scoped to the documents your account is permitted to read. Retrieval filters on that permission boundary before any passage reaches the model."
        />

        {/* Metrics */}
        <div className="mt-6 grid gap-3 sm:grid-cols-3">
          <Metric
            label="Documents in scope"
            value={docs ? String(docs.total) : "—"}
            hint={`${ready.length} indexed and searchable`}
          />
          <Metric
            label="With expiry dates"
            value={expiring.length ? String(expiring.length) : "—"}
            hint="Classified deterministically from source text"
          />
          <Metric
            label="Generation model"
            value={
              (health?.providers?.llm as string | undefined)?.replace(
                "bedrock-converse:",
                "",
              ) ?? "—"
            }
            hint={
              (health?.providers?.embedder as string | undefined) ??
              "embeddings loaded locally"
            }
          />
        </div>

        {/* Search */}
        <div className="panel mt-5 p-5 shadow-panel">
          <p className="label mb-2.5">Search the archive</p>
          <form onSubmit={runSearch} className="flex gap-2">
            <input
              className="input"
              placeholder="Semantic search across permitted documents…"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
            <button className="btn btn-primary" disabled={searching}>
              {searching ? "Searching…" : "Search"}
            </button>
          </form>

          {error && (
            <p className="mt-3 text-[12px] text-[#B3261E]">{error}</p>
          )}

          {hits && (
            <div className="mt-4 space-y-2">
              <p className="label">
                {hits.count} result{hits.count === 1 ? "" : "s"} for “{hits.query}”
              </p>
              {hits.hits.map((h) => (
                <Link
                  key={h.chunk_id}
                  href={`/library/${h.document_id}`}
                  className="block rounded-lg border border-charcoal/10 p-3 transition-colors hover:border-copper/45 hover:bg-copper/[0.04]"
                >
                  <div className="flex items-center justify-between gap-3">
                    <span className="truncate text-[12px] font-semibold">
                      {h.filename}
                    </span>
                    <span className="font-mono text-[10px] text-steel">
                      p.{h.page_start}–{h.page_end} · {h.score.toFixed(3)}
                    </span>
                  </div>
                  <p className="mt-1 line-clamp-2 text-[12px] leading-relaxed text-charcoal/65">
                    {h.excerpt}
                  </p>
                </Link>
              ))}
              {hits.count === 0 && (
                <p className="text-[12px] text-steel">
                  Nothing in your permitted scope matched that query.
                </p>
              )}
            </div>
          )}

          {!hits && (
            <div className="mt-4 flex flex-wrap gap-2">
              {SUGGESTIONS.map((s) => (
                <Link
                  key={s}
                  href={`/ask?q=${encodeURIComponent(s)}`}
                  className="chip bg-charcoal/5 text-charcoal/70 transition-colors hover:bg-copper/12 hover:text-copper"
                >
                  {s}
                </Link>
              ))}
            </div>
          )}
        </div>

        {/* Recent documents */}
        <div className="mt-8">
          <div className="flex items-end justify-between">
            <p className="label">Recently indexed</p>
            <Link href="/library" className="text-[12px] font-medium text-copper hover:underline">
              View all →
            </Link>
          </div>
          <div className="mt-2.5 overflow-hidden rounded-xl border border-charcoal/10 bg-white">
            <table className="w-full text-left">
              <thead>
                <tr className="border-b border-charcoal/10 bg-charcoal/[0.02]">
                  <th className="label px-4 py-2.5 font-semibold">Document</th>
                  <th className="label px-4 py-2.5 font-semibold">Type</th>
                  <th className="label px-4 py-2.5 font-semibold">Expiry</th>
                  <th className="label px-4 py-2.5 font-semibold">Status</th>
                </tr>
              </thead>
              <tbody>
                {items.slice(0, 8).map((d) => (
                  <tr
                    key={d.id}
                    className="border-b border-charcoal/5 last:border-0 transition-colors hover:bg-charcoal/[0.02]"
                  >
                    <td className="px-4 py-2.5">
                      <Link
                        href={`/library/${d.id}`}
                        className="text-[13px] font-medium hover:text-copper"
                      >
                        {d.title || d.filename}
                      </Link>
                      <p className="text-[11px] text-steel">{d.filename}</p>
                    </td>
                    <td className="px-4 py-2.5">
                      <DocTypeChip type={d.doc_type} />
                    </td>
                    <td className="px-4 py-2.5 font-mono text-[11px] text-charcoal/65">
                      {d.expiry_date ?? "—"}
                    </td>
                    <td className="px-4 py-2.5">
                      <StatusDot status={d.status} />
                    </td>
                  </tr>
                ))}
                {!items.length && (
                  <tr>
                    <td colSpan={4} className="px-4 py-8 text-center text-[12px] text-steel">
                      {docs ? "No documents are visible to your account yet." : "Loading…"}
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}

function Metric({
  label,
  value,
  hint,
}: {
  label: string;
  value: string;
  hint: string;
}) {
  return (
    <div className="panel p-4 shadow-panel">
      <p className="label">{label}</p>
      <p className="mt-1.5 font-mono text-[24px] font-semibold tracking-tight">
        {value}
      </p>
      <p className="mt-0.5 truncate text-[11px] text-steel">{hint}</p>
    </div>
  );
}
