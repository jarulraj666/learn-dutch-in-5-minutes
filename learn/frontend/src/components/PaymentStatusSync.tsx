"use client";

import { useEffect } from "react";
import { callApi } from "@/lib/format";

export function PaymentStatusSync() {
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const sessionId = params.get("checkout_session_id");
    if (params.get("checkout") !== "pending" || !sessionId) return;

    void callApi<{ status: string }>(
      `billing/checkout/confirm?session_id=${encodeURIComponent(sessionId)}`,
      { method: "POST" },
    )
      .then((result) => {
        if (result.status === "paid") window.location.replace("/pricing");
      })
      .catch(() => {
        // The webhook may still be processing; leave the pending message visible.
      });
  }, []);

  return null;
}
