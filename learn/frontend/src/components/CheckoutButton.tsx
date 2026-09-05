"use client";

import { useCallback, useEffect, useState } from "react";
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

  const start = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await callApi<CheckoutResponse>("billing/checkout", {
        method: "POST",
        body: JSON.stringify({ product, section }),
      });
      window.sessionStorage.removeItem("pending-checkout");
      window.location.href = res.checkout_url;
    } catch (e) {
      if (e instanceof Error && e.message.includes("Sign in required")) {
        window.sessionStorage.setItem("pending-checkout", JSON.stringify({ product, section }));
        window.location.href = "/api/auth/google/start?return_to=%2Fpricing%3Fresume_checkout%3D1";
        return;
      }
      setError("Could not start checkout. Please try again.");
      setLoading(false);
    }
  }, [product, section]);

  useEffect(() => {
    if (window.location.search !== "?resume_checkout=1") return;

    try {
      const pending = JSON.parse(window.sessionStorage.getItem("pending-checkout") ?? "null") as {
        product?: Props["product"];
        section?: Props["section"];
      } | null;
      if (pending?.product === product && pending?.section === section) {
        void start();
      }
    } catch {
      window.sessionStorage.removeItem("pending-checkout");
    }
  }, [product, section, start]);

  return (
    <div>
      <button onClick={start} disabled={loading} className={className ?? "btn-primary px-5 py-2 text-sm"}>
        {loading ? "Redirecting…" : label}
      </button>
      {error && <p className="mt-2 text-sm text-red-600">{error}</p>}
    </div>
  );
}
