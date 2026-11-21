import type { Metadata } from "next";
import { AuthProvider } from "@/lib/auth";
import "../styles/globals.css";

export const metadata: Metadata = {
  title: "Ask the Archive",
  description: "Enterprise document intelligence with permission-aware retrieval.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-concrete font-sans text-charcoal antialiased">
        <AuthProvider>{children}</AuthProvider>
      </body>
    </html>
  );
}
