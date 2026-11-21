"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth";

export default function Home() {
  const { user, loading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (loading) return;
    router.replace(user ? "/dashboard" : "/login");
  }, [loading, user, router]);

  return (
    <div className="grid-field flex min-h-screen items-center justify-center p-6">
      <div className="w-full max-w-sm">
        <div className="panel p-7 shadow-panel">
          <div className="h-1 w-10 rounded-full bg-copper" />
          <h1 className="mt-4 text-[20px] font-semibold tracking-tight">
            Ask the Archive
          </h1>
          <p className="mt-1.5 text-[13px] leading-relaxed text-charcoal/60">
            Signing in to your document intelligence workspace.
          </p>
          <div className="mt-5 space-y-2">
            <div className="skeleton h-3 w-2/3 rounded" />
            <div className="skeleton h-3 w-1/2 rounded" />
          </div>
        </div>
      </div>
    </div>
  );
}
