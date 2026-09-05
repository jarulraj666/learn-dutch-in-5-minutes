"use client";

import { useState } from "react";
import { callApi } from "@/lib/format";
import type { CheckoutResponse, MockExamSection } from "@/lib/types";

type Props = {
  product: "section" | "full";
  section?: MockExamSection;
  label: string;
  className?: string;
};

/** Starts a Mollie checkout and redirects the browser to the hosted payment page. */
export function CheckoutButton({ product, section, label, className }: Props) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function start() {
    setLoading(true);
    setError(null);
    try {
      const res = await callApi<CheckoutResponse>("billing/checkout", {
        method: "POST",
        body: JSON.stringify({ product, section }),
      });
      window.location.href = res.checkout_url;
    } catch (e) {
      if (e instanceof Error && e.message.includes("Sign in required")) {
        window.location.href = "/api/auth/google/start?return_to=/pricing";
        return;
      }
      setError("Could not start checkout. Please try again.");
      setLoading(false);
    }
  }

  return (
    <div>
      <button onClick={start} disabled={loading} className={className ?? "btn-primary px-5 py-2 text-sm"}>
        {loading ? "Redirecting…" : label}
      </button>
      {error && <p className="mt-2 text-sm text-red-600">{error}</p>}
    </div>
  );
}
