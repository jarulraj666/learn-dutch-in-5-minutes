import { NextResponse } from "next/server";

const BASE = process.env.LEARN_API_URL ?? "http://localhost:8001";

export async function POST(req: Request) {
  const body = await req.text();
  const response = await fetch(`${BASE}/api/auth/password/signup`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body,
    cache: "no-store",
  });
  const text = await response.text();
  if (!response.ok) return new NextResponse(text, { status: response.status, headers: { "Content-Type": "application/json" } });

  const result = JSON.parse(text) as { token: string };
  const next = NextResponse.json({ ok: true });
  next.cookies.set("learn-session-token", result.token, {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax",
    path: "/",
    maxAge: 30 * 24 * 60 * 60,
  });
  return next;
}
