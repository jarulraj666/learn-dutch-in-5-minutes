"use client";

import Link from "next/link";
import Image from "next/image";
import { usePathname } from "next/navigation";
import { useState } from "react";
import clsx from "clsx";
import { BookOpen, LayoutDashboard, Layers, MessageSquareText, Menu, ShieldCheck, User, X } from "lucide-react";

const NAV = [
  { href: "/courses", label: "Courses", icon: BookOpen },
  { href: "/dashboard", label: "My learning", icon: LayoutDashboard },
  { href: "/flashcards", label: "Flashcards", icon: Layers },
  { href: "/feedback", label: "Feedback", icon: MessageSquareText },
];

type Props = {
  user: { name: string | null; email: string | null; image: string | null; role: string; isAdmin: boolean } | null;
};

export function SiteHeader({ user }: Props) {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const navItems = user?.isAdmin
    ? [...NAV, { href: "/admin", label: "Admin", icon: ShieldCheck }]
    : NAV;

  async function signOut() {
    await fetch("/api/auth/logout", { method: "POST" });
    window.location.assign("/");
  }

  return (
    <header className="sticky top-0 z-40 border-b border-slate-200 bg-white/90 backdrop-blur">
      <div className="mx-auto flex max-w-7xl items-center gap-6 px-4 py-3">
        <Link href="/" className="flex items-center gap-2 font-bold">
          <Image
            src="/logo.png"
            alt="Learn Dutch in 5 Minutes"
            width={36}
            height={36}
            priority
            className="rounded-full"
          />
          <span className="text-gradient text-lg">Learn Dutch</span>
        </Link>

        <nav className="ml-auto hidden items-center gap-1 md:flex">
          {navItems.map(({ href, label, icon: Icon }) => (
            <Link
              key={href}
              href={href}
              className={clsx(
                "flex items-center gap-2 rounded-full px-4 py-2 text-sm font-medium transition",
                pathname.startsWith(href)
                  ? "bg-brand-50 text-brand-700"
                  : "text-slate-600 hover:bg-slate-100",
              )}
            >
              <Icon size={16} />
              {label}
            </Link>
          ))}
        </nav>

        <div className="ml-auto flex items-center gap-2 md:ml-0">
          {user ? (
            <div className="flex items-center gap-2">
              <Link
                href="/profile"
                className="flex items-center gap-2 rounded-full border border-slate-200 py-1 pl-1 pr-3 text-sm hover:border-brand-300"
              >
                {user.image ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img src={user.image} alt="" className="h-7 w-7 rounded-full" />
                ) : (
                  <span className="grid h-7 w-7 place-items-center rounded-full bg-brand-100 text-brand-700">
                    <User size={14} />
                  </span>
                )}
                <span className="hidden max-w-[10rem] truncate sm:inline">
                  {user.name ?? user.email}
                </span>
              </Link>
              <button
                onClick={signOut}
                className="hidden text-sm text-slate-500 hover:text-slate-800 sm:block"
              >
                Sign out
              </button>
            </div>
          ) : (
            <button onClick={() => { window.location.href = "/api/auth/google/start?return_to=/dashboard"; }} className="btn-primary px-5 py-2 text-sm">
              Sign in with Google
            </button>
          )}

          <button
            className="md:hidden"
            onClick={() => setOpen((v) => !v)}
            aria-label="Toggle navigation"
          >
            {open ? <X size={22} /> : <Menu size={22} />}
          </button>
        </div>
      </div>

      {open && (
        <nav className="border-t border-slate-200 bg-white px-4 py-2 md:hidden">
          {navItems.map(({ href, label, icon: Icon }) => (
            <Link
              key={href}
              href={href}
              onClick={() => setOpen(false)}
              className="flex items-center gap-2 rounded-lg px-3 py-2 text-sm text-slate-700 hover:bg-slate-100"
            >
              <Icon size={16} />
              {label}
            </Link>
          ))}
        </nav>
      )}
    </header>
  );
}
