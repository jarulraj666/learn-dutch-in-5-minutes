import { NextResponse } from "next/server";

const BASE = process.env.LEARN_API_URL ?? "http://localhost:8001";

export async function POST(req: Request) {
  const response = await fetch(`${BASE}/api/auth/password/reset`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: await req.text(),
    cache: "no-store",
  });
  const text = await response.text();
  return new NextResponse(text, {
    status: response.status,
    headers: { "Content-Type": "application/json" },
  });
}
