"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams, useSearchParams } from "next/navigation";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { ArchiveDocument, Permission, Summary } from "@/lib/types";
import { DocTypeChip, StatusDot } from "@/components/ui";

interface PreviewPage {
  chunk_index: number;
  page_start: number;
  page_end: number;
  text: string;
}

interface Preview {
  id: string;
  filename: string;
  doc_type: string | null;
  expiry_date: string | null;
  status: string;
  pages: PreviewPage[];
}

export default function DocumentPage() {
  const { id } = useParams<{ id: string }>();
  const params = useSearchParams();
  const { user } = useAuth();
  const focusPage = Number(params.get("page") ?? 0);

  const [doc, setDoc] = useState<ArchiveDocument | null>(null);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [summarising, setSummarising] = useState(false);
  const [perms, setPerms] = useState<Permission[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [downloadMsg, setDownloadMsg] = useState<string | null>(null);

  useEffect(() => {
    if (!id) return;
    api.document(id).then(setDoc).catch((e) => setError(e.message));
    api
      .permissions(id)
      .then(setPerms)
      .catch(() => setPerms([]));
    api
      .preview(id)
      .then(setPreview)
      .catch((e) => setError(e.message));

    api
      .summary(id)
      .then(setSummary)
      .catch(() => setSummary(null));
  }, [id]);

  async function doSummary() {
    setSummarising(true);
    try {
      setSummary(await api.createSummary(id));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Summary failed.");
    } finally {
      setSummarising(false);
    }
  }

  async function doDownload() {
    setDownloadMsg(null);
    try {
      await api.downloadBlob(id, doc?.filename ?? "document.pdf");
    } catch (err) {
      setDownloadMsg(
        err instanceof ApiError
          ? err.message
          : "You do not have download permission for this document.",
      );
    }
  }

  const canManage = user?.role === "admin";

  return (
    <div className="grid-field min-h-screen">
      <div className="mx-auto max-w-6xl px-6 py-8">
        <Link
          href="/library"
          className="text-[12px] font-medium text-charcoal/55 hover:text-copper"
        >
          ← Back to library
        </Link>

        {error && (
          <div className="mt-4 rounded-lg border border-[#B3261E]/25 bg-[#B3261E]/6 px-3.5 py-3 text-[13px] text-[#B3261E]">
            {error}
          </div>
        )}

        <div className="mt-4 grid gap-5 lg:grid-cols-[1fr_320px]">
          {/* Document body */}
          <div className="min-w-0">
            <div className="panel p-5 shadow-panel">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <DocTypeChip type={doc?.doc_type ?? null} />
                    {doc && <StatusDot status={doc.status} />}
                  </div>
                  <h1 className="mt-2 text-[19px] font-semibold tracking-tight">
                    {doc?.title || doc?.filename || "Document"}
                  </h1>
                  <p className="mt-0.5 text-[12px] text-steel">{doc?.filename}</p>
                </div>
                <button className="btn btn-ghost" onClick={doDownload}>
                  Download original
                </button>
              </div>

              {downloadMsg && (
                <p className="mt-3 rounded-lg border border-aws/40 bg-aws/[0.08] px-3 py-2 text-[12px] text-[#8a5a00]">
                  {downloadMsg}
                </p>
              )}

              <div className="rule my-4" />

              {/* Pages */}
              <div className="space-y-4">
                {preview?.pages.map((p) => {
                  const focused =
                    focusPage &&
                    focusPage >= p.page_start &&
                    focusPage <= p.page_end;
                  return (
                    <section
                      key={p.chunk_index}
                      className={`rounded-lg border px-4 py-3.5 transition-colors ${
                        focused
                          ? "border-copper/55 bg-copper/[0.05]"
                          : "border-charcoal/8 bg-white"
                      }`}
                    >
                      <div className="mb-2 flex items-center justify-between">
                        <p className="label">
                          Page {p.page_start}
                          {p.page_end !== p.page_start ? `–${p.page_end}` : ""}
                        </p>
                        {focused && (
                          <span className="chip bg-copper/15 text-copper">
                            cited passage
                          </span>
                        )}
                      </div>
                      <pre className="whitespace-pre-wrap font-sans text-[13px] leading-relaxed text-charcoal/80">
                        {p.text}
                      </pre>
                    </section>
                  );
                })}
                {!preview && !error && (
                  <div className="space-y-2">
                    <div className="skeleton h-24 rounded-lg" />
                    <div className="skeleton h-24 rounded-lg" />
                  </div>
                )}
              </div>
            </div>
          </div>

          {/* Side rail */}
          <aside className="space-y-4">
            <div className="panel p-4 shadow-panel">
              <p className="label">Summary</p>
              {summary ? (
                <>
                  <SummaryText text={summary.summary} />
                  <p className="mt-2 font-mono text-[10px] text-steel">
                    {summary.model} · {summary.prompt_version}
                  </p>
                </>
              ) : (
                <>
                  <p className="mt-2 text-[12px] leading-relaxed text-charcoal/55">
                    No summary has been generated for this document yet.
                  </p>
                  <button
                    className="btn btn-primary mt-3 w-full"
                    disabled={summarising}
                    onClick={doSummary}
                  >
                    {summarising ? "Summarising…" : "Generate summary"}
                  </button>
                </>
              )}
            </div>

            <div className="panel p-4 shadow-panel">
              <p className="label">Metadata</p>
              <dl className="mt-2 space-y-1.5 text-[12px]">
                <Row k="Expiry date" v={doc?.expiry_date ?? "—"} mono />
                <Row k="Pages" v={doc?.page_count ?? "—"} mono />
                <Row k="Size" v={doc ? formatBytes(doc.byte_size) : "—"} mono />
                <Row
                  k="Confidence"
                  v={
                    doc?.classification_confidence != null
                      ? doc.classification_confidence.toFixed(2)
                      : "—"
                  }
                  mono
                />
                <Row
                  k="Indexed"
                  v={doc?.indexed_at ? doc.indexed_at.slice(0, 19).replace("T", " ") : "—"}
                  mono
                />
              </dl>
            </div>

            <div className="panel p-4 shadow-panel">
              <p className="label">Who can read this</p>
              {perms.length ? (
                <ul className="mt-2 space-y-1.5">
                  {perms.map((p) => (
                    <li
                      key={p.id}
                      className="flex items-center justify-between text-[12px]"
                    >
                      <span className="text-charcoal/80">
                        {p.grantee_type === "role"
                          ? `Role: ${p.grantee_role}`
                          : `User: ${p.grantee_user_id?.slice(0, 8)}`}
                      </span>
                      <span className="chip bg-charcoal/6 text-charcoal/60">
                        {p.permission}
                      </span>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="mt-2 text-[12px] text-steel">
                  {canManage
                    ? "No explicit grants — visible to the uploader and admins only."
                    : "You have access through a role grant or as the uploader."}
                </p>
              )}
            </div>
          </aside>
        </div>
      </div>
    </div>
  );
}

function Row({
  k,
  v,
  mono,
}: {
  k: string;
  v: string | number;
  mono?: boolean;
}) {
  return (
    <div className="flex items-center justify-between gap-3">
      <dt className="text-charcoal/55">{k}</dt>
      <dd className={mono ? "font-mono text-[11px]" : "text-[12px]"}>{v}</dd>
    </div>
  );
}

function formatBytes(n: number) {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}

function SummaryText({ text }: { text: string }) {
  return (
    <div className="mt-2 space-y-1 text-[12px] leading-relaxed text-charcoal/75">
      {text.split("\n").map((line, i) => {
        const m = line.match(/^\s*(?:[-•*])\s+(.*)$/);
        if (m) {
          return (
            <p key={i} className="flex gap-2">
              <span className="text-copper">•</span>
              <span>{m[1]}</span>
            </p>
          );
        }
        return line.trim() ? <p key={i}>{line}</p> : null;
      })}
    </div>
  );
}
