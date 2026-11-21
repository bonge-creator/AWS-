"use client";

import { useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { AuditEntry, Conversation, StoredMessage } from "@/lib/types";
import { PageHeader } from "@/components/ui";

export default function ActivityPage() {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";
  const [audit, setAudit] = useState<AuditEntry[] | null>(null);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [messages, setMessages] = useState<StoredMessage[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.conversations().then(setConversations).catch(() => setConversations([]));
    if (isAdmin) {
      api
        .adminAudit()
        .then(setAudit)
        .catch((e) => setError(e.message));
    }
  }, [isAdmin]);

  useEffect(() => {
    if (!selected) return;
    api.messages(selected).then(setMessages).catch(() => setMessages([]));
  }, [selected]);

  return (
    <div className="grid-field min-h-screen">
      <div className="mx-auto max-w-6xl px-6 py-8">
        <PageHeader
          eyebrow="Activity"
          title={isAdmin ? "Audit trail" : "Your activity"}
          description={
            isAdmin
              ? "Every authentication, permission change, download and answer attempt is recorded with the actor, the resource and the outcome."
              : "Your past conversations with the archive, in order."
          }
        />

        {error && (
          <div className="mt-4 rounded-lg border border-[#B3261E]/25 bg-[#B3261E]/6 px-3.5 py-2.5 text-[12px] text-[#B3261E]">
            {error}
          </div>
        )}

        {isAdmin ? (
          <div className="mt-6 overflow-hidden rounded-xl border border-charcoal/10 bg-white">
            <table className="w-full text-left">
              <thead>
                <tr className="border-b border-charcoal/10 bg-charcoal/[0.02]">
                  <th className="label px-4 py-2.5 font-semibold">When</th>
                  <th className="label px-4 py-2.5 font-semibold">Action</th>
                  <th className="label px-4 py-2.5 font-semibold">Resource</th>
                  <th className="label px-4 py-2.5 font-semibold">Actor</th>
                  <th className="label px-4 py-2.5 font-semibold">IP</th>
                </tr>
              </thead>
              <tbody>
                {(audit ?? []).map((a) => (
                  <tr
                    key={a.id}
                    className="border-b border-charcoal/5 last:border-0 hover:bg-charcoal/[0.02]"
                  >
                    <td className="px-4 py-2.5 font-mono text-[11px] text-charcoal/60">
                      {a.created_at?.slice(0, 19).replace("T", " ")}
                    </td>
                    <td className="px-4 py-2.5">
                      <span className="chip bg-charcoal/6 text-charcoal/70">
                        {a.action}
                      </span>
                    </td>
                    <td className="px-4 py-2.5 text-[12px] text-charcoal/65">
                      {a.resource_type ?? "—"}
                      {a.resource_id ? ` · ${a.resource_id.slice(0, 8)}` : ""}
                    </td>
                    <td className="px-4 py-2.5 font-mono text-[11px] text-charcoal/55">
                      {a.actor_user_id?.slice(0, 8) ?? "system"}
                    </td>
                    <td className="px-4 py-2.5 font-mono text-[11px] text-steel">
                      {a.ip ?? "—"}
                    </td>
                  </tr>
                ))}
                {!audit && (
                  <tr>
                    <td colSpan={5} className="px-4 py-8 text-center text-[12px] text-steel">
                      Loading audit trail…
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="mt-6 grid gap-4 lg:grid-cols-[280px_1fr]">
            <div className="panel overflow-hidden shadow-panel">
              <p className="label border-b border-charcoal/8 px-4 py-2.5">
                Conversations
              </p>
              <div className="max-h-[60vh] overflow-y-auto">
                {conversations.map((c) => (
                  <button
                    key={c.id}
                    onClick={() => setSelected(c.id)}
                    className={`block w-full border-b border-charcoal/5 px-4 py-2.5 text-left transition-colors last:border-0 hover:bg-charcoal/[0.03] ${
                      selected === c.id ? "bg-copper/[0.07]" : ""
                    }`}
                  >
                    <p className="truncate text-[12px] font-medium">
                      {c.title || "Untitled conversation"}
                    </p>
                    <p className="font-mono text-[10px] text-steel">
                      {c.created_at?.slice(0, 16).replace("T", " ")}
                    </p>
                  </button>
                ))}
                {!conversations.length && (
                  <p className="px-4 py-6 text-center text-[12px] text-steel">
                    No conversations yet.
                  </p>
                )}
              </div>
            </div>

            <div className="panel p-5 shadow-panel">
              {selected ? (
                <div className="space-y-3">
                  {messages.map((m) => (
                    <div key={m.id}>
                      <p className="label">{m.role}</p>
                      <p className="mt-1 whitespace-pre-wrap text-[13px] leading-relaxed text-charcoal/80">
                        {m.content}
                      </p>
                      {m.answer_found === false && (
                        <span className="chip mt-1 bg-aws/15 text-[#8a5a00]">
                          no answer found
                        </span>
                      )}
                    </div>
                  ))}
                  {!messages.length && (
                    <p className="text-[12px] text-steel">No messages.</p>
                  )}
                </div>
              ) : (
                <p className="py-10 text-center text-[12px] text-steel">
                  Select a conversation to review it.
                </p>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
