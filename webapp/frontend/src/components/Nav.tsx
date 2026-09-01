"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import clsx from "clsx";
import { LayoutDashboard, List, Play, Upload, Settings, GraduationCap } from "lucide-react";

const LINKS = [
  { href: "/", label: "Dashboard", icon: LayoutDashboard },
  { href: "/topics", label: "Topics", icon: List },
  { href: "/run", label: "Run Pipeline", icon: Play },
  { href: "/publish", label: "Publish Queue", icon: Upload },
  { href: "/mock-exams", label: "Mock Exams", icon: GraduationCap },
  { href: "/config", label: "Config", icon: Settings },
];

export function Nav() {
  const path = usePathname();
  return (
    <header className="bg-gray-900 border-b border-gray-800 sticky top-0 z-30">
      <div className="container mx-auto px-4 max-w-7xl flex items-center gap-1 h-14">
        <span className="font-bold text-white mr-4 text-sm tracking-wide">🇳🇱 Dutch Videos</span>
        {LINKS.map(({ href, label, icon: Icon }) => (
          <Link
            key={href}
            href={href}
            className={clsx(
              "flex items-center gap-1.5 px-3 py-1.5 rounded text-sm transition-colors",
              path === href || (href !== "/" && path.startsWith(href))
                ? "bg-sky-600 text-white"
                : "text-gray-400 hover:text-white hover:bg-gray-800"
            )}
          >
            <Icon size={15} />
            {label}
          </Link>
        ))}
      </div>
    </header>
  );
}
