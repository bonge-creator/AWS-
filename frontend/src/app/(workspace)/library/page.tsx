"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { api, ApiError } from "@/lib/api";
import type { ArchiveDocument, DocumentList } from "@/lib/types";
import { DocTypeChip, PageHeader, StatusDot } from "@/components/ui";

const TYPE_FILTERS = [
  "all",
  "lease",
  "contract",
  "policy",
  "invoice",
  "nda",
  "report",
  "other",
];

export default function LibraryPage() {
  const [data, setData] = useState<DocumentList | null>(null);
  const [filter, setFilter] = useState("all");
  const [query, setQuery] = useState("");
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    api.documents().then(setData).catch((e) => setUploadError(e.message));
  }, []);

  const items = data?.items ?? [];
  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return items.filter((d) => {
      if (filter !== "all" && d.doc_type !== filter) return false;
      if (!q) return true;
      return (
        d.filename.toLowerCase().includes(q) ||
        (d.title ?? "").toLowerCase().includes(q)
      );
    });
  }, [items, filter, query]);

  async function onUpload(file: File) {
    setUploading(true);
    setUploadError(null);
    setNotice(null);
    try {
      const doc = await api.upload(file);
      setNotice(`Uploaded ${doc.filename}. Extraction and indexing have started.`);
      // Poll until the document finishes ingesting.
      await watch(doc.id);
      setData(await api.documents());
    } catch (err) {
      setUploadError(
        err instanceof ApiError ? err.message : "Upload failed. Check the file type.",
      );
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  }

  async function watch(id: string) {
    for (let i = 0; i < 30; i += 1) {
      await new Promise((r) => setTimeout(r, 1500));
      try {
        const d = await api.document(id);
        if (d.status === "ready" || d.status === "indexed" || d.status === "failed") {
          return;
        }
      } catch {
        return;
      }
    }
  }

  return (
    <div className="grid-field min-h-screen">
      <div className="mx-auto max-w-6xl px-6 py-8">
        <PageHeader
          eyebrow="Library"
          title="Document library"
          description="Only documents your account may read are listed. Uploads are validated, extracted, classified and indexed before they become searchable."
          actions={
            <>
              <input
                ref={fileRef}
                type="file"
                accept=".pdf,.docx,.xlsx,.csv,.txt,.rtf,.html,.png,.jpg,.jpeg,.tiff,.bmp"
                className="hidden"
                onChange={(e) => {
                  const f = e.target.files?.[0];
                  if (f) onUpload(f);
                }}
              />
              <button
                className="btn btn-primary"
                disabled={uploading}
                onClick={() => fileRef.current?.click()}
              >
                {uploading ? "Processing…" : "Upload document"}
              </button>
            </>
          }
        />

        {(uploadError || notice) && (
          <div
            className={`mt-4 rounded-lg border px-3.5 py-2.5 text-[12px] ${
              uploadError
                ? "border-[#B3261E]/25 bg-[#B3261E]/6 text-[#B3261E]"
                : "border-[#2F6F4F]/25 bg-[#2F6F4F]/6 text-[#2F6F4F]"
            }`}
          >
            {uploadError || notice}
          </div>
        )}

        {/* Controls */}
        <div className="mt-5 flex flex-wrap items-center gap-2">
          <input
            className="input max-w-xs"
            placeholder="Filter by name…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
          <div className="flex flex-wrap gap-1.5">
            {TYPE_FILTERS.map((t) => (
              <button
                key={t}
                onClick={() => setFilter(t)}
                className={`chip capitalize transition-colors ${
                  filter === t
                    ? "bg-charcoal text-white"
                    : "bg-charcoal/5 text-charcoal/65 hover:bg-charcoal/10"
                }`}
              >
                {t}
              </button>
            ))}
          </div>
          <span className="ml-auto text-[11px] text-steel">
            {filtered.length} of {data?.total ?? 0} documents
          </span>
        </div>

        {/* Grid */}
        <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {filtered.map((d) => (
            <DocCard key={d.id} doc={d} />
          ))}
          {!filtered.length && data && (
            <p className="col-span-full py-10 text-center text-[13px] text-steel">
              Nothing matches that filter.
            </p>
          )}
        </div>
      </div>
    </div>
  );
}

function DocCard({ doc }: { doc: ArchiveDocument }) {
  return (
    <Link
      href={`/library/${doc.id}`}
      className="panel group flex flex-col p-4 shadow-panel transition-all hover:-translate-y-0.5 hover:shadow-lift"
    >
      <div className="flex items-start justify-between gap-3">
        <DocTypeChip type={doc.doc_type} />
        <StatusDot status={doc.status} />
      </div>
      <h3 className="mt-3 line-clamp-2 text-[14px] font-semibold leading-snug group-hover:text-copper">
        {doc.title || doc.filename}
      </h3>
      <p className="mt-0.5 truncate text-[11px] text-steel">{doc.filename}</p>

      <div className="mt-3 grid grid-cols-2 gap-2 border-t border-charcoal/8 pt-3">
        <div>
          <p className="label text-[9px]">Expires</p>
          <p className="mt-0.5 font-mono text-[11px] text-charcoal/70">
            {doc.expiry_date ?? "—"}
          </p>
        </div>
        <div>
          <p className="label text-[9px]">Pages</p>
          <p className="mt-0.5 font-mono text-[11px] text-charcoal/70">
            {doc.page_count ?? "—"}
          </p>
        </div>
      </div>
    </Link>
  );
}
