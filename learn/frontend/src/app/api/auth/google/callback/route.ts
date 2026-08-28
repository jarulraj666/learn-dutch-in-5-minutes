import { NextRequest, NextResponse } from "next/server";

const BASE = process.env.LEARN_API_URL ?? "http://localhost:8001";

export async function GET(req: NextRequest) {
  const code = req.nextUrl.searchParams.get("code");
  const state = req.nextUrl.searchParams.get("state");
  if (!code || !state) return NextResponse.redirect(new URL("/signin?error=oauth", req.url));

  const upstream = new URL(`${BASE}/api/auth/google/callback`);
  upstream.searchParams.set("code", code);
  upstream.searchParams.set("state", state);
  const response = await fetch(upstream, { cache: "no-store" });
  if (!response.ok) return NextResponse.redirect(new URL("/signin?error=oauth", req.url));

  const result = await response.json() as { token: string; return_to: string };
  const redirect = NextResponse.redirect(new URL(result.return_to || "/dashboard", req.url));
  redirect.cookies.set("learn-session-token", result.token, {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax",
    path: "/",
    maxAge: 30 * 24 * 60 * 60,
  });
  return redirect;
}