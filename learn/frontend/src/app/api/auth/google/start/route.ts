import { NextRequest, NextResponse } from "next/server";

const BASE = process.env.LEARN_API_URL ?? "http://localhost:8001";

export function GET(req: NextRequest) {
  const returnTo = req.nextUrl.searchParams.get("return_to") ?? "/dashboard";
  const url = new URL(`${BASE}/api/auth/google/start`);
  url.searchParams.set("return_to", returnTo.startsWith("/") && !returnTo.startsWith("//") ? returnTo : "/dashboard");
  return NextResponse.redirect(url);
}