import type { Metadata } from "next";
import Link from "next/link";
import { learnerSession } from "@/lib/learner-session";
import { SiteHeader } from "@/components/SiteHeader";
import { CookieNotice } from "@/components/CookieNotice";
import "./globals.css";

export const metadata: Metadata = {
  title: "Learn Dutch in 5 Minutes",
  description:
    "Short, structured Dutch video lessons with vocabulary, grammar notes, transcripts and quizzes. Free.",
  metadataBase: new URL(process.env.NEXTAUTH_URL ?? "https://learndutchin5minutes.nl"),
};

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  const session = await learnerSession();

  return (
    <html lang="en">
      <body className="min-h-screen">
        <SiteHeader
            user={
              session?.user
                ? {
                    name: session.user.name ?? null,
                    email: session.user.email ?? null,
                    image: session.user.image ?? null,
                    role: session.user.role ?? "learner",
                  }
                : null
            }
          />
          <main className="mx-auto min-h-[70vh] w-full max-w-7xl px-4 py-8">{children}</main>
          <footer className="border-t border-slate-200 bg-white">
            <div className="mx-auto flex max-w-7xl flex-col gap-4 px-4 py-8 text-sm text-slate-500 sm:flex-row sm:items-center sm:justify-between">
              <p>© {new Date().getFullYear()} Learn Dutch in 5 Minutes</p>
              <nav className="flex gap-6">
                <Link href="/privacy" className="hover:text-brand-700">Privacy</Link>
                <Link href="/terms" className="hover:text-brand-700">Terms</Link>
                <a href="mailto:info@learndutchin5minutes.nl" className="hover:text-brand-700">
                  Contact
                </a>
              </nav>
            </div>
          </footer>
          <CookieNotice />
      </body>
    </html>
  );
}
