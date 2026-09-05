import { NextRequest, NextResponse } from "next/server";
import { sessionToken } from "@/lib/session-token";

const BASE = process.env.LEARN_API_URL ?? "http://localhost:8001";

// Internal only — never added to the client-facing proxy whitelist. The backend
// still enforces AdminUser regardless of what this does.
export async function POST(req: NextRequest) {
  const token = sessionToken();
  if (!token) {
    return NextResponse.json({ detail: "Sign in required" }, { status: 401 });
  }

  const body = await req.text();
  const res = await fetch(`${BASE}/api/admin/mock-exams/generate`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
    body,
    cache: "no-store",
  });

  const text = await res.text();
  return new NextResponse(text || null, {
    status: res.status,
    headers: { "Content-Type": res.headers.get("Content-Type") ?? "application/json" },
  });
}
