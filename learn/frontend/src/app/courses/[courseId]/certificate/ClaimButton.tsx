"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { callApi } from "@/lib/format";
import type { Certificate } from "@/lib/types";

export function ClaimButton({ courseId, eligible }: { courseId: string; eligible: boolean }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!eligible) {
    return (
      <p className="text-sm text-slate-500">
        Complete every lesson and pass every quiz to unlock your certificate.
      </p>
    );
  }

  async function claim() {
    setBusy(true);
    setError(null);
    try {
      const certificate = await callApi<Certificate>(`courses/${courseId}/certificate`, {
        method: "POST",
      });
      router.push(`/certificates/${certificate.serial}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not issue the certificate");
      setBusy(false);
    }
  }

  return (
    <div>
      <button onClick={claim} disabled={busy} className="btn-primary">
        {busy ? "Issuing…" : "Claim my certificate"}
      </button>
      {error && <p className="mt-2 text-sm text-rose-600">{error}</p>}
    </div>
  );
}
