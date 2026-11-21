"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth";
import { AppShell } from "@/components/ui";

function Gate({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!loading && !user) router.replace("/login");
  }, [loading, user, router]);

  if (loading) {
    return (
      <div className="grid-field flex min-h-screen items-center justify-center">
        <div className="flex items-center gap-3 text-steel">
          <span className="h-4 w-4 animate-spin rounded-full border-2 border-charcoal/20 border-t-copper" />
          <span className="text-[12px]">Loading workspace…</span>
        </div>
      </div>
    );
  }
  if (!user) return null;
  return <AppShell>{children}</AppShell>;
}

export default function WorkspaceLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <Gate>{children}</Gate>;
}
