"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

export function MockExamActions({ id, status }: { id: string; status: string }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);

  async function act(action: "publish" | "unpublish") {
    setBusy(true);
    try {
      await fetch(`/api/admin/mock-exams/${id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action }),
      });
      router.refresh();
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex gap-2">
      <button
        onClick={() => act("publish")}
        disabled={busy || status === "published"}
        className="rounded-full bg-emerald-50 px-3 py-1 text-xs font-semibold text-emerald-700 disabled:opacity-40"
      >
        Publish
      </button>
      <button
        onClick={() => act("unpublish")}
        disabled={busy || status === "draft"}
        className="rounded-full bg-rose-50 px-3 py-1 text-xs font-semibold text-rose-700 disabled:opacity-40"
      >
        Unpublish
      </button>
    </div>
  );
}
