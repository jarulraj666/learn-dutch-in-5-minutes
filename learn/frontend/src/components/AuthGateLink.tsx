"use client";

import { useState } from "react";
import Link from "next/link";
import { X } from "lucide-react";

type Props = {
  href: string;
  loggedIn: boolean;
  className?: string;
  children: React.ReactNode;
};

/** Renders a normal link when signed in; otherwise prompts sign-in, then continues to `href`. */
export function AuthGateLink({ href, loggedIn, className, children }: Props) {
  const [open, setOpen] = useState(false);

  if (loggedIn) {
    return (
      <Link href={href} className={className}>
        {children}
      </Link>
    );
  }

  return (
    <>
      <button type="button" onClick={() => setOpen(true)} className={className}>
        {children}
      </button>
      {open && (
        <div
          className="fixed inset-0 z-50 grid place-items-center bg-slate-900/50 px-4"
          onClick={() => setOpen(false)}
        >
          <div className="card w-full max-w-sm p-6 text-center" onClick={(e) => e.stopPropagation()}>
            <button
              type="button"
              aria-label="Close"
              onClick={() => setOpen(false)}
              className="ml-auto block text-slate-400 hover:text-slate-600"
            >
              <X size={18} />
            </button>
            <h2 className="text-lg font-semibold">Sign in to start this exam</h2>
            <p className="mt-2 text-sm text-slate-600">
              Sign in with Google to take practice exams and track your results — it&apos;s free.
            </p>
            <button
              type="button"
              onClick={() => {
                window.location.href = `/api/auth/google/start?return_to=${encodeURIComponent(href)}`;
              }}
              className="btn-primary mt-6 w-full px-5 py-2 text-sm"
            >
              Continue with Google
            </button>
          </div>
        </div>
      )}
    </>
  );
}
