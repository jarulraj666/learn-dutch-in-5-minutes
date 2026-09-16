"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";

function VerifyEmailContent() {
  const token = useSearchParams().get("token") ?? "";
  const [state, setState] = useState<"loading" | "success" | "error">("loading");

  useEffect(() => {
    if (!token) {
      setState("error");
      return;
    }
    void fetch(`/api/auth/password/verify-email?token=${encodeURIComponent(token)}`, { method: "POST" })
      .then((response) => setState(response.ok ? "success" : "error"))
      .catch(() => setState("error"));
  }, [token]);

  return (
    <div className="card mx-auto max-w-md p-8 text-center">
      <h1 className="text-2xl font-bold">{state === "success" ? "Email verified" : state === "loading" ? "Verifying your email" : "Verification link expired"}</h1>
      <p className="mt-3 text-sm text-slate-600">
        {state === "success" ? "Your account is ready. You can sign in now." : state === "loading" ? "Please wait a moment." : "Request a new account or reset link if needed."}
      </p>
      {state !== "loading" && <Link href="/signin" className="btn-primary mt-6">Go to sign in</Link>}
    </div>
  );
}

export default function VerifyEmailPage() {
  return <Suspense><VerifyEmailContent /></Suspense>;
}