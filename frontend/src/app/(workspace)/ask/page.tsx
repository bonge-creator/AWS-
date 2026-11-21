"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { api, streamAnswer } from "@/lib/api";
import type { Citation, Passage } from "@/lib/types";

interface Turn {
  id: string;
  question: string;
  answer: string;
  passages: Passage[];
  citations: Citation[];
  found: boolean | null;
  intent: string;
  model: string;
  streaming: boolean;
  error?: string;
}

export default function AskPage() {
  const params = useSearchParams();
  const [question, setQuestion] = useState(params.get("q") ?? "");
  const [turns, setTurns] = useState<Turn[]>([]);
  const [busy, setBusy] = useState(false);
  const bottom = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: "smooth" });
  }, [turns]);

  async function ask(q: string) {
    const trimmed = q.trim();
    if (!trimmed || busy) return;
    setBusy(true);
    setQuestion("");

    const turn: Turn = {
      id: `${Date.now()}`,
      question: trimmed,
      answer: "",
      passages: [],
      citations: [],
      found: null,
      intent: "",
      model: "",
      streaming: true,
    };
    setTurns((t) => [...t, turn]);

    // The transcript renders from `turns`, so every streaming callback patches
    // that same list — patching a separate `active` copy would leave the
    // rendered turn stuck at an empty answer (skeletons forever).
    const patch = (updater: (t: Turn) => Turn) =>
      setTurns((all) => all.map((t) => (t.id === turn.id ? updater(t) : t)));

    await streamAnswer(trimmed, {
      onEvidence: (p) =>
        patch((cur) => ({
          ...cur,
          intent: p.intent,
          found: p.found,
          passages: p.passages ?? [],
        })),
      onDelta: (text) =>
        patch((cur) => ({ ...cur, answer: cur.answer + text })),
      onCitations: (cites) =>
        patch((cur) => ({ ...cur, citations: cites ?? [] })),
      onDone: (payload) => {
        patch((cur) => ({
          ...cur,
          found: Boolean(payload?.found),
          streaming: false,
        }));
        setBusy(false);
      },
      onError: (message) => {
        patch((cur) => ({ ...cur, error: message, streaming: false }));
        setBusy(false);
      },
    });
    setBusy(false);
  }

  return (
    <div className="flex min-h-screen flex-col">
      <div className="mx-auto flex w-full max-w-6xl flex-1 flex-col px-6 py-7">
        <header className="mb-5">
          <p className="label">Assistant</p>
          <h1 className="mt-1 text-[21px] font-semibold tracking-tight">
            Ask the archive
          </h1>
          <p className="mt-1 text-[13px] text-charcoal/60">
            Answers are grounded in retrieved passages. Citations open the
            original document.
          </p>
        </header>

        {/* Transcript */}
        <div className="flex-1 space-y-6">
          {turns.length === 0 && (
            <div className="panel p-6 shadow-panel">
              <p className="label mb-3">Try one of these</p>
              <div className="space-y-2">
                {[
                  "Which lease agreements expire next year?",
                  "Summarise the Kestrel facilities contract.",
                  "What are our data retention obligations?",
                  "Who are the parties to the Ridgeline supply agreement?",
                ].map((s) => (
                  <button
                    key={s}
                    onClick={() => ask(s)}
                    className="group flex w-full items-center justify-between rounded-lg border border-charcoal/10 px-3.5 py-2.5 text-left text-[13px] transition-colors hover:border-copper/45 hover:bg-copper/[0.05]"
                  >
                    {s}
                    <span className="text-steel transition-colors group-hover:text-copper">
                      →
                    </span>
                  </button>
                ))}
              </div>
              <p className="mt-4 border-t border-charcoal/8 pt-3 text-[11px] leading-relaxed text-steel">
                Retrieval is filtered by your document permissions before the
                model is called, so a question may legitimately have no answer
                for your role.
              </p>
            </div>
          )}

          {turns.map((t) => (
            <div key={t.id} className="animate-rise space-y-3">
              <div className="flex items-start gap-2.5">
                <span className="mt-0.5 grid h-6 w-6 shrink-0 place-items-center rounded-md bg-charcoal text-white">
                  <span className="text-[10px] font-bold">
                    {(t.question[0] ?? "?").toUpperCase()}
                  </span>
                </span>
                <p className="pt-1 text-[14px] font-medium">{t.question}</p>
              </div>

              <div className="pl-[34px]">
                {t.error ? (
                  <div className="rounded-lg border border-[#B3261E]/25 bg-[#B3261E]/6 px-3.5 py-3 text-[13px] text-[#B3261E]">
                    {t.error}
                  </div>
                ) : (
                  <>
                    <AnswerBody turn={t} />
                    {t.passages.length > 0 && <EvidencePanel passages={t.passages} />}
                    {t.citations.length > 0 && <CitationPanel citations={t.citations} />}
                  </>
                )}
              </div>
            </div>
          ))}
          <div ref={bottom} />
        </div>

        {/* Composer */}
        <div className="sticky bottom-0 mt-6 bg-gradient-to-t from-concrete via-concrete to-transparent pb-4 pt-3">
          <form
            onSubmit={(e) => {
              e.preventDefault();
              ask(question);
            }}
            className="panel flex items-end gap-2 p-2 shadow-lift"
          >
            <textarea
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  ask(question);
                }
              }}
              rows={1}
              placeholder="Ask a question about the archive…"
              className="max-h-40 flex-1 resize-none border-0 bg-transparent px-3 py-2.5 text-[14px] outline-none placeholder:text-steel"
            />
            <button
              type="submit"
              disabled={busy || !question.trim()}
              className="btn btn-accent"
            >
              {busy ? "Thinking" : "Ask"}
            </button>
          </form>
          <p className="mt-2 text-center text-[11px] text-steel">
            Enter to send · Shift + Enter for a new line
          </p>
        </div>
      </div>
    </div>
  );
}

function AnswerBody({ turn }: { turn: Turn }) {
  if (!turn.answer) {
    return (
      <div className="space-y-2">
        <div className="skeleton h-3 w-1/3 rounded" />
        <div className="skeleton h-3 w-11/12 rounded" />
        <div className="skeleton h-3 w-2/3 rounded" />
      </div>
    );
  }

  const abstained =
    turn.found === false ||
    /do(?:es)? not (?:appear|contain)|no information|not in the archive|insufficient/i.test(
      turn.answer,
    );

  return (
    <div>
      <div
        className={`rounded-xl border px-4 py-3.5 text-[14px] leading-relaxed ${
          abstained
            ? "border-aws/40 bg-aws/[0.07]"
            : "border-charcoal/10 bg-white"
        }`}
      >
        {abstained && (
          <p className="label mb-1.5 text-[#8a5a00]">Not answered in the archive</p>
        )}
        <p className="whitespace-pre-wrap text-charcoal/90">{turn.answer}</p>
      </div>

      {turn.intent && (
        <p className="mt-1.5 flex items-center gap-2 font-mono text-[10px] text-steel">
          <span className="rounded bg-charcoal/6 px-1.5 py-0.5">intent:{turn.intent}</span>
          {turn.model && (
            <span className="rounded bg-charcoal/6 px-1.5 py-0.5">
              model:{turn.model}
            </span>
          )}
        </p>
      )}
    </div>
  );
}

function EvidencePanel({ passages }: { passages: Passage[] }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="mt-2.5">
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex items-center gap-1.5 text-[11px] font-medium text-charcoal/60 hover:text-charcoal"
      >
        <span
          className={`transition-transform ${open ? "rotate-90" : ""}`}
        >
          ▶
        </span>
        {passages.length} retrieved passage{passages.length === 1 ? "" : "s"}
        <span className="font-normal text-steel">
          — the only content the model was given
        </span>
      </button>
      {open && (
        <div className="mt-2 space-y-1.5">
          {passages.map((p) => (
            <div
              key={`${p.document_id}-${p.index}`}
              className="rounded-lg border border-charcoal/8 bg-charcoal/[0.02] px-3 py-2"
            >
              <div className="flex items-center justify-between gap-3">
                <Link
                  href={`/library/${p.document_id}`}
                  className="truncate text-[11px] font-semibold hover:text-copper"
                >
                  [{p.index}] {p.filename}
                </Link>
                <span className="font-mono text-[10px] text-steel">
                  p.{p.page_start}
                  {p.page_end !== p.page_start ? `–${p.page_end}` : ""}
                  {typeof p.score === "number" ? ` · ${p.score.toFixed(3)}` : ""}
                </span>
              </div>
              {p.quote && (
                <p className="mt-1 line-clamp-3 text-[11px] leading-relaxed text-charcoal/60">
                  {p.quote}
                </p>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function CitationPanel({ citations }: { citations: Citation[] }) {
  return (
    <div className="mt-3">
      <p className="label mb-1.5">Citations</p>
      <div className="space-y-1.5">
        {citations.map((c) => (
          <Link
            key={`${c.document_id}-${c.index}`}
            href={`/library/${c.document_id}?page=${c.page_start}`}
            className="group flex gap-2.5 rounded-lg border border-charcoal/10 bg-white px-3 py-2.5 transition-colors hover:border-copper/45"
          >
            <span className="mt-0.5 grid h-5 w-5 shrink-0 place-items-center rounded bg-copper/12 font-mono text-[10px] font-bold text-copper">
              {c.index}
            </span>
            <span className="min-w-0 flex-1">
              <span className="flex items-center justify-between gap-3">
                <span className="truncate text-[12px] font-semibold group-hover:text-copper">
                  {c.filename}
                </span>
                <span className="shrink-0 font-mono text-[10px] text-steel">
                  p.{c.page_start}
                  {c.page_end !== c.page_start ? `–${c.page_end}` : ""}
                </span>
              </span>
              <span className="mt-0.5 block line-clamp-2 text-[11px] leading-relaxed text-charcoal/60">
                “{c.quote}”
              </span>
            </span>
          </Link>
        ))}
      </div>
    </div>
  );
}
