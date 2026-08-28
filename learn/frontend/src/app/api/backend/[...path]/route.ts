import { NextRequest, NextResponse } from "next/server";
import { sessionToken } from "@/lib/session-token";

const BASE = process.env.LEARN_API_URL ?? "http://localhost:8001";

// Only these client-callable endpoints are proxied. Anything else is rejected,
// so a compromised client cannot reach admin routes through this handler.
const ALLOWED: RegExp[] = [
  /^progress$/,
  /^lessons\/[\w.-]+\/quiz\/submit$/,
  /^lessons\/[\w.-]+\/quiz\/attempts$/,
  /^flashcards\/due$/,
  /^flashcards\/review$/,
  /^me\/settings$/,
  /^courses\/[\w.-]+\/certificate$/,
];

function resolve(segments: string[]): string | null {
  const path = segments.join("/");
  if (path.includes("..")) return null;
  return ALLOWED.some((re) => re.test(path)) ? path : null;
}

async function forward(req: NextRequest, segments: string[]) {
  const path = resolve(segments);
  if (!path) {
    return NextResponse.json({ detail: "Not found" }, { status: 404 });
  }

  const token = sessionToken();
  if (!token) {
    return NextResponse.json({ detail: "Sign in required" }, { status: 401 });
  }

  const headers = new Headers({
    Authorization: `Bearer ${token}`,
    "Content-Type": "application/json",
  });

  const body = req.method === "GET" ? undefined : await req.text();
  const url = `${BASE}/api/${path}${req.nextUrl.search}`;
  const res = await fetch(url, { method: req.method, headers, body, cache: "no-store" });

  const text = await res.text();
  return new NextResponse(text || null, {
    status: res.status,
    headers: { "Content-Type": res.headers.get("Content-Type") ?? "application/json" },
  });
}

type Ctx = { params: { path: string[] } };

export async function GET(req: NextRequest, { params }: Ctx) {
  return forward(req, params.path);
}

export async function POST(req: NextRequest, { params }: Ctx) {
  return forward(req, params.path);
}

export async function PATCH(req: NextRequest, { params }: Ctx) {
  return forward(req, params.path);
}
