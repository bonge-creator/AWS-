"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth";
import { ApiError } from "@/lib/api";

const DEMO_ACCOUNTS = [
  {
    email: "analyst@archivedemo.example.com",
    role: "analyst",
    note: "Leases & contracts",
  },
  {
    email: "viewer@archivedemo.example.com",
    role: "viewer",
    note: "Policies & leases",
  },
  {
    email: "admin@archivedemo.example.com",
    role: "admin",
    note: "Full archive",
  },
];

export default function LoginPage() {
  const { login, user, loading } = useAuth();
  const router = useRouter();
  const [email, setEmail] = useState("analyst@archivedemo.example.com");
  const [password, setPassword] = useState("Archive!2026");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (!loading && user) {
    router.replace("/dashboard");
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await login(email.trim(), password);
      router.replace("/dashboard");
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : "Could not reach the archive service. Is the backend running?",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="grid-field flex min-h-screen items-center justify-center p-6">
      <div className="w-full max-w-4xl grid overflow-hidden rounded-2xl border border-charcoal/10 bg-white shadow-lift md:grid-cols-[1.05fr_1fr]">
        {/* Left: identity + posture */}
        <div className="relative hidden flex-col justify-between bg-charcoal p-10 text-white md:flex">
          <div className="absolute inset-0 grid-field opacity-[0.16]" />
          <div className="relative">
            <div className="flex items-center gap-2.5">
              <span className="grid h-8 w-8 place-items-center rounded-lg bg-white/10">
                <svg
                  viewBox="0 0 24 24"
                  className="h-4 w-4"
                  fill="none"
                  stroke="#FF9900"
                  strokeWidth="2"
                  strokeLinecap="round"
                >
                  <path d="M4 5h7l2 3h7v11H4z" />
                  <path d="M8 12h6" />
                </svg>
              </span>
              <span className="text-[13px] font-semibold tracking-tight">
                Ask the Archive
              </span>
            </div>

            <h1 className="mt-14 max-w-[13ch] text-[30px] font-semibold leading-[1.15] tracking-tight">
              Your documents, answerable.
            </h1>
            <p className="mt-4 max-w-[42ch] text-[13px] leading-relaxed text-white/60">
              Semantic retrieval across every contract, lease and policy you are
              cleared to read — with citations that open the original page and
              an honest "not in the archive" when the answer isn&apos;t there.
            </p>
          </div>

          <div className="relative space-y-2.5">
            {[
              ["Retrieval", "Permissions enforced before the model sees a passage"],
              ["Citations", "Every claim traced to a page in the original"],
              ["Abstention", "No answer is better than a fabricated one"],
            ].map(([k, v]) => (
              <div key={k} className="flex items-start gap-3">
                <span className="mt-[6px] h-1 w-1 shrink-0 rounded-full bg-aws" />
                <p className="text-[12px] leading-relaxed text-white/55">
                  <span className="font-semibold text-white/85">{k}</span> — {v}
                </p>
              </div>
            ))}
          </div>
        </div>

        {/* Right: form */}
        <div className="p-8 sm:p-10">
          <p className="label">Sign in</p>
          <h2 className="mt-2 text-[19px] font-semibold tracking-tight">
            Access the workspace
          </h2>

          <form onSubmit={submit} className="mt-7 space-y-4">
            <div>
              <label className="label mb-1.5 block" htmlFor="email">
                Work email
              </label>
              <input
                id="email"
                type="email"
                autoComplete="username"
                required
                className="input"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
            </div>
            <div>
              <label className="label mb-1.5 block" htmlFor="password">
                Password
              </label>
              <input
                id="password"
                type="password"
                autoComplete="current-password"
                required
                className="input"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </div>

            {error && (
              <div className="rounded-lg border border-[#B3261E]/25 bg-[#B3261E]/6 px-3 py-2.5 text-[12px] leading-relaxed text-[#B3261E]">
                {error}
              </div>
            )}

            <button type="submit" disabled={busy} className="btn btn-primary w-full">
              {busy ? "Authenticating…" : "Sign in"}
            </button>
          </form>

          <div className="rule my-6" />

          <p className="label mb-2.5">Demo accounts</p>
          <div className="space-y-1.5">
            {DEMO_ACCOUNTS.map((a) => (
              <button
                key={a.email}
                type="button"
                onClick={() => {
                  setEmail(a.email);
                  setPassword("Archive!2026");
                }}
                className="flex w-full items-center justify-between rounded-lg border border-charcoal/10 px-3 py-2 text-left transition-colors hover:border-copper/45 hover:bg-copper/5"
              >
                <span>
                  <span className="block text-[12px] font-medium">{a.email}</span>
                  <span className="block text-[11px] text-charcoal/50">
                    {a.note}
                  </span>
                </span>
                <span className="chip bg-charcoal/6 text-charcoal/60">
                  {a.role}
                </span>
              </button>
            ))}
          </div>
          <p className="mt-3 text-[11px] text-steel">
            Shared demo password: <span className="font-mono">Archive!2026</span>
          </p>
        </div>
      </div>
    </div>
  );
}
