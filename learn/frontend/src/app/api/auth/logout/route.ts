import { NextResponse } from "next/server";
import { sessionToken } from "@/lib/session-token";

const BASE = process.env.LEARN_API_URL ?? "http://localhost:8001";

export async function POST(req: Request) {
  const token = sessionToken();
  if (token) {
    await fetch(`${BASE}/api/auth/logout`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
      cache: "no-store",
    });
  }
  const response = NextResponse.redirect(new URL("/", req.url));
  response.cookies.delete("learn-session-token");
  return response;
}