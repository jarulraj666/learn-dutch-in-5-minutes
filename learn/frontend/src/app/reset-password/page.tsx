"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { FormEvent, Suspense, useState } from "react";

function ResetPasswordContent() {
  const token = useSearchParams().get("token");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    setError(null);
    setMessage(null);
    const endpoint = token ? "/api/auth/password/reset" : "/api/auth/password/request-reset";
    const body = token ? { token, password } : { email };
    const response = await fetch(endpoint, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    const data = await response.json().catch(() => null) as { message?: string; detail?: string } | null;
    if (!response.ok) setError(data?.detail ?? "Could not process this request.");
    else setMessage(token ? "Your password has been reset. You can sign in now." : data?.message ?? "Check your email for recovery instructions.");
    setLoading(false);
  }

  return (
    <div className="card mx-auto max-w-md p-8">
      <h1 className="text-center text-2xl font-bold">{token ? "Choose a new password" : "Reset your password"}</h1>
      <p className="mt-2 text-center text-sm text-slate-600">
        {token ? "Use at least 8 characters." : "Enter your email and we will send recovery instructions."}
      </p>
      <form onSubmit={submit} className="mt-6 space-y-4">
        {!token && <input required type="email" value={email} onChange={(event) => setEmail(event.target.value)} className="input w-full" placeholder="Email address" autoComplete="email" />}
        {token && <input required type="password" value={password} onChange={(event) => setPassword(event.target.value)} className="input w-full" placeholder="New password" minLength={8} maxLength={128} autoComplete="new-password" />}
        {error && <p className="text-sm text-red-600">{error}</p>}
        {message && <p className="text-sm text-emerald-700">{message}</p>}
        <button disabled={loading} className="btn-primary w-full">{loading ? "Please wait…" : token ? "Reset password" : "Send recovery email"}</button>
      </form>
      <Link href="/signin" className="mt-5 block text-center text-sm text-brand-700 hover:underline">Back to sign in</Link>
    </div>
  );
}

export default function ResetPasswordPage() {
  return <Suspense><ResetPasswordContent /></Suspense>;
}