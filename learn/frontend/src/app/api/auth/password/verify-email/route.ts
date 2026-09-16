import { NextRequest, NextResponse } from "next/server";

const BASE = process.env.LEARN_API_URL ?? "http://localhost:8001";

export async function POST(req: NextRequest) {
  const token = req.nextUrl.searchParams.get("token") ?? "";
  const response = await fetch(`${BASE}/api/auth/password/verify-email?token=${encodeURIComponent(token)}`, {
    method: "POST",
    cache: "no-store",
  });
  const text = await response.text();
  return new NextResponse(text, {
    status: response.status,
    headers: { "Content-Type": "application/json" },
  });
}
