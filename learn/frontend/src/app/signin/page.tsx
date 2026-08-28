"use client";

import { useSearchParams } from "next/navigation";
import { Suspense } from "react";

function SignInCard() {
  const callbackUrl = useSearchParams().get("callbackUrl") ?? "/dashboard";

  return (
    <div className="card mx-auto max-w-sm p-8 text-center">
      <h1 className="text-2xl font-bold">Sign in</h1>
      <p className="mt-2 text-sm text-slate-600">
        Sign in to track your progress, take quizzes and earn your certificate. It is free.
      </p>
      <button
        onClick={() => { window.location.href = `/api/auth/google/start?return_to=${encodeURIComponent(callbackUrl)}`; }}
        className="btn-primary mt-6 w-full"
      >
        Continue with Google
      </button>
      <p className="mt-4 text-xs text-slate-400">
        More sign-in options are coming soon.
      </p>
    </div>
  );
}

export default function SignInPage() {
  return (
    <Suspense>
      <SignInCard />
    </Suspense>
  );
}
