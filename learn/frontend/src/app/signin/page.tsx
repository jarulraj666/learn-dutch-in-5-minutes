"use client";

import { FormEvent, Suspense, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";

function SignInCard() {
  const searchParams = useSearchParams();
  const callbackUrl = searchParams.get("callbackUrl") ?? "/dashboard";
  const signupCompleted = searchParams.get("signup") === "complete";
  const [mode, setMode] = useState<"login" | "signup">("login");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [verificationUrl, setVerificationUrl] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    setError(null);
    setNotice(null);
    setVerificationUrl(null);
    try {
      const endpoint = mode === "login" ? "/api/auth/password/login" : "/api/auth/password/signup";
      const response = await fetch(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password, ...(mode === "signup" ? { name } : {}) }),
      });
      const result = await response.json().catch(() => null) as { detail?: string; signup_completed?: boolean } | null;
      if (!response.ok) {
        setError(result?.detail ?? "Could not sign in. Please try again.");
        return;
      }
      if (mode === "signup" && result?.signup_completed) {
        window.location.assign("/signin?signup=complete");
        return;
      }
      window.location.assign(callbackUrl);
    } catch {
      setError("The request timed out. Check the email settings and try again.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="card mx-auto max-w-sm p-8">
      <h1 className="text-center text-2xl font-bold">{mode === "login" ? "Sign in" : "Create your account"}</h1>
      <p className="mt-2 text-sm text-slate-600">
        {mode === "login" ? "Continue learning and track your progress." : "Save your progress, exam results and certificates."}
      </p>
      {signupCompleted && (
        <p className="mt-4 rounded-lg bg-emerald-50 px-3 py-2 text-sm text-emerald-700">
          Signup completed. Please sign in with your email and password.
        </p>
      )}
      <form onSubmit={submit} className="mt-6 space-y-4">
        {mode === "signup" && (
          <label className="block text-left text-sm font-medium text-slate-700">
            Name
            <input required value={name} onChange={(event) => setName(event.target.value)} className="input mt-1 w-full" maxLength={100} />
          </label>
        )}
        <label className="block text-left text-sm font-medium text-slate-700">
          Email
          <input required type="email" value={email} onChange={(event) => setEmail(event.target.value)} className="input mt-1 w-full" autoComplete="email" maxLength={254} />
        </label>
        <label className="block text-left text-sm font-medium text-slate-700">
          Password
          <input required type="password" value={password} onChange={(event) => setPassword(event.target.value)} className="input mt-1 w-full" autoComplete={mode === "login" ? "current-password" : "new-password"} minLength={mode === "login" ? 1 : 8} maxLength={128} />
        </label>
        {error && <p className="text-sm text-red-600">{error}</p>}
        {notice && (
          <div className="text-sm text-emerald-700">
            <p>{notice}</p>
            {verificationUrl && (
              <a href={verificationUrl} className="mt-2 inline-block font-semibold underline">
                Open verification link (local development)
              </a>
            )}
          </div>
        )}
        <button disabled={loading} className="btn-primary w-full">
          {loading ? "Please wait…" : mode === "login" ? "Sign in" : "Create account"}
        </button>
      </form>
      {mode === "login" && (
        <Link href="/reset-password" className="mt-4 block text-center text-sm text-brand-700 hover:underline">
          Forgot password?
        </Link>
      )}
      <div className="my-6 flex items-center gap-3 text-xs text-slate-400">
        <span className="h-px flex-1 bg-slate-200" />or<span className="h-px flex-1 bg-slate-200" />
      </div>
      <button onClick={() => { window.location.href = `/api/auth/google/start?return_to=${encodeURIComponent(callbackUrl)}`; }} className="btn-secondary w-full">
        Continue with Google
      </button>
      <button type="button" onClick={() => { setMode(mode === "login" ? "signup" : "login"); setError(null); setNotice(null); setVerificationUrl(null); }} className="mt-5 w-full text-sm font-semibold text-brand-700 hover:underline">
        {mode === "login" ? "Create an account" : "I already have an account"}
      </button>
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
