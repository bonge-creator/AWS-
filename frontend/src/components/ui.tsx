"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useAuth } from "@/lib/auth";

export function Wordmark({ compact = false }: { compact?: boolean }) {
  return (
    <Link href="/dashboard" className="flex items-center gap-2.5 shrink-0">
      <span className="relative grid h-8 w-8 place-items-center rounded-lg bg-charcoal">
        <span className="absolute inset-0 rounded-lg ring-1 ring-inset ring-white/10" />
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
      {!compact && (
        <span className="leading-tight">
          <span className="block text-[13px] font-semibold tracking-tight">
            Ask the Archive
          </span>
          <span className="label block text-[9px]">Document intelligence</span>
        </span>
      )}
    </Link>
  );
}

const NAV = [
  { href: "/dashboard", label: "Overview" },
  { href: "/ask", label: "Assistant" },
  { href: "/library", label: "Library" },
  { href: "/activity", label: "Activity" },
];

export function AppShell({ children }: { children: React.ReactNode }) {
  const { user, logout } = useAuth();
  const pathname = usePathname();

  return (
    <div className="flex min-h-screen">
      <aside className="hidden w-[232px] shrink-0 flex-col border-r border-charcoal/10 bg-white md:flex">
        <div className="flex h-16 items-center border-b border-charcoal/10 px-5">
          <Wordmark />
        </div>

        <nav className="flex-1 space-y-1 px-3 py-4">
          {NAV.map((item) => {
            const active = pathname.startsWith(item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                className={`flex items-center gap-2.5 rounded-lg px-3 py-2 text-[13px] font-medium transition-colors ${
                  active
                    ? "bg-charcoal text-white"
                    : "text-charcoal/70 hover:bg-charcoal/5 hover:text-charcoal"
                }`}
              >
                {item.label}
                {item.href === "/library" && (
                  <span className="ml-auto text-[10px] text-steel">⌘K</span>
                )}
              </Link>
            );
          })}
          {user?.role === "admin" && (
            <>
              <div className="rule my-3" />
              <Link
                href="/admin"
                className={`flex items-center gap-2.5 rounded-lg px-3 py-2 text-[13px] font-medium transition-colors ${
                  pathname.startsWith("/admin")
                    ? "bg-charcoal text-white"
                    : "text-charcoal/70 hover:bg-charcoal/5 hover:text-charcoal"
                }`}
              >
                Administration
              </Link>
            </>
          )}
        </nav>

        <div className="border-t border-charcoal/10 p-3">
          <div className="flex items-center gap-2.5 rounded-lg px-2 py-2">
            <span className="grid h-8 w-8 shrink-0 place-items-center rounded-full bg-copper/15 text-[11px] font-bold text-copper">
              {(user?.display_name || "?")
                .split(" ")
                .map((p) => p[0])
                .slice(0, 2)
                .join("")
                .toUpperCase()}
            </span>
            <div className="min-w-0 flex-1 leading-tight">
              <p className="truncate text-[12px] font-semibold">
                {user?.display_name}
              </p>
              <p className="label text-[9px]">{user?.role}</p>
            </div>
            <button
              onClick={logout}
              title="Sign out"
              className="rounded-md p-1.5 text-steel transition-colors hover:bg-charcoal/5 hover:text-charcoal"
            >
              <svg
                viewBox="0 0 24 24"
                className="h-4 w-4"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.8"
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
                <path d="m16 17 5-5-5-5M21 12H9" />
              </svg>
            </button>
          </div>
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-16 items-center justify-between border-b border-charcoal/10 bg-white/80 px-4 backdrop-blur md:hidden">
          <Wordmark />
          <span className="label">{user?.role}</span>
        </header>
        <main className="min-w-0 flex-1">{children}</main>
      </div>
    </div>
  );
}

export function PageHeader({
  eyebrow,
  title,
  description,
  actions,
}: {
  eyebrow?: string;
  title: string;
  description?: string;
  actions?: React.ReactNode;
}) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-4">
      <div>
        {eyebrow && <p className="label mb-1.5">{eyebrow}</p>}
        <h1 className="text-[22px] font-semibold tracking-tight">{title}</h1>
        {description && (
          <p className="mt-1 max-w-2xl text-[13px] leading-relaxed text-charcoal/60">
            {description}
          </p>
        )}
      </div>
      {actions && <div className="flex items-center gap-2">{actions}</div>}
    </div>
  );
}

export function DocTypeChip({ type }: { type: string | null }) {
  const palette: Record<string, string> = {
    lease: "bg-copper/12 text-copper",
    contract: "bg-charcoal/8 text-charcoal/75",
    policy: "bg-[#2F6F4F]/12 text-[#2F6F4F]",
    invoice: "bg-aws/15 text-[#8a5a00]",
    nda: "bg-[#6B4E9B]/12 text-[#5A3F86]",
    report: "bg-steel/18 text-charcoal/65",
    other: "bg-charcoal/6 text-steel",
  };
  return (
    <span className={`chip ${palette[type ?? "other"] ?? palette.other}`}>
      {(type ?? "other").toUpperCase()}
    </span>
  );
}

export function StatusDot({ status }: { status: string }) {
  const map: Record<string, string> = {
    ready: "bg-[#2F6F4F]",
    indexed: "bg-[#2F6F4F]",
    uploaded: "bg-aws",
    processing: "bg-aws animate-pulse",
    failed: "bg-[#B3261E]",
  };
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className={`h-1.5 w-1.5 rounded-full ${map[status] ?? "bg-steel"}`} />
      <span className="text-[11px] text-charcoal/55">{status}</span>
    </span>
  );
}
