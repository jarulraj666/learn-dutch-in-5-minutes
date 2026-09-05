"use client";

import Link from "next/link";
import Image from "next/image";
import { usePathname } from "next/navigation";
import { useState } from "react";
import clsx from "clsx";
import { BookOpen, ClipboardCheck, LayoutDashboard, Layers, Mail, MessageSquareText, Menu, ShieldCheck, User, X, ChevronDown } from "lucide-react";

type NavItem = {
  href: string;
  label: string;
  icon: typeof BookOpen;
  match?: string;
};

const NAV_GROUPS: { label: string; items: NavItem[] }[] = [
  {
    label: "Learn",
    items: [
      { href: "/courses", label: "Courses", icon: BookOpen },
      { href: "/dashboard", label: "My learning", icon: LayoutDashboard },
      { href: "/flashcards", label: "Flashcards", icon: Layers },
    ],
  },
  {
    label: "Practice",
    items: [
      { href: "/mock-exams/reading", label: "Inburgering Exams", icon: ClipboardCheck, match: "/mock-exams" },
    ],
  },
  {
    label: "More",
    items: [
      { href: "/feedback", label: "Feedback", icon: MessageSquareText },
      { href: "/contact", label: "Contact", icon: Mail },
    ],
  },
];

const ADMIN_ITEM: NavItem = { href: "/admin", label: "Admin", icon: ShieldCheck };

type Props = {
  user: { name: string | null; email: string | null; image: string | null; role: string; isAdmin: boolean } | null;
};

export function SiteHeader({ user }: Props) {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const [openGroup, setOpenGroup] = useState<string | null>(null);
  const navGroups: { label: string; items: NavItem[] }[] = user?.isAdmin
    ? [...NAV_GROUPS, { label: "Admin", items: [ADMIN_ITEM] }]
    : NAV_GROUPS;

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
          <span className="text-gradient text-lg">Learn Dutch In 5 Minutes</span>
        </Link>

        <nav className="ml-auto hidden items-center gap-1 md:flex">
          {navGroups.map((group) => {
            const active = group.items.some(({ href, match }) => pathname.startsWith(match ?? href));
            const isOpen = openGroup === group.label;
            return (
              <div key={group.label} className="group relative">
                <button
                  type="button"
                  aria-expanded={isOpen}
                  onClick={() => setOpenGroup(isOpen ? null : group.label)}
                  className={clsx(
                  "flex cursor-pointer list-none items-center gap-1 rounded-full px-4 py-2 text-sm font-medium transition [&::-webkit-details-marker]:hidden",
                  active ? "bg-brand-50 text-brand-700" : "text-slate-600 hover:bg-slate-100",
                  )}
                >
                  {group.label}
                  <ChevronDown size={15} className={clsx("transition", isOpen && "rotate-180")} />
                </button>
                {isOpen && <div className="absolute right-0 top-full z-50 mt-2 min-w-48 rounded-xl border border-slate-200 bg-white p-2 shadow-lg">
                  {group.items.map(({ href, label, icon: Icon, match }) => (
                    <Link
                      key={href}
                      href={href}
                      onClick={() => setOpenGroup(null)}
                      className={clsx(
                        "flex items-center gap-2 rounded-lg px-3 py-2 text-sm transition",
                        pathname.startsWith(match ?? href)
                          ? "bg-brand-50 font-semibold text-brand-700"
                          : "text-slate-600 hover:bg-slate-100",
                      )}
                    >
                      <Icon size={16} />
                      {label}
                    </Link>
                  ))}
                </div>}
              </div>
            );
          })}
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
          {navGroups.map((group) => (
            <div key={group.label} className="border-b border-slate-100 py-2 last:border-b-0">
              <p className="px-3 pb-1 text-xs font-semibold uppercase tracking-wide text-slate-400">{group.label}</p>
              {group.items.map(({ href, label, icon: Icon }) => (
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
            </div>
          ))}
        </nav>
      )}
    </header>
  );
}
