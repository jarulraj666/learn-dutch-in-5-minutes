"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

const KEY = "ld5m.cookie-consent";

/** Required because the lesson player loads the YouTube IFrame API, which sets cookies. */
export function CookieNotice() {
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    setVisible(localStorage.getItem(KEY) !== "accepted");
  }, []);

  if (!visible) return null;

  return (
    <div className="fixed inset-x-0 bottom-0 z-50 border-t border-slate-200 bg-white p-4 shadow-lg">
      <div className="mx-auto flex max-w-5xl flex-col gap-3 text-sm text-slate-600 sm:flex-row sm:items-center">
        <p className="flex-1">
          We use essential cookies to keep you signed in and to track your lesson progress.
          Lesson videos are embedded from YouTube, which sets its own cookies. See our{" "}
          <Link href="/privacy" className="font-medium text-brand-700 underline">
            privacy policy
          </Link>
          .
        </p>
        <button
          className="btn-primary px-5 py-2 text-sm"
          onClick={() => {
            localStorage.setItem(KEY, "accepted");
            setVisible(false);
          }}
        >
          Got it
        </button>
      </div>
    </div>
  );
}
