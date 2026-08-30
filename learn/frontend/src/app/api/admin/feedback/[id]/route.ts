import { NextRequest, NextResponse } from "next/server";
import { sessionToken } from "@/lib/session-token";

const BASE = process.env.LEARN_API_URL ?? "http://localhost:8001";

type Ctx = { params: { id: string } };

// Internal only — never added to the client-facing proxy whitelist. The backend
// still enforces AdminUser on these routes regardless of what this does.
export async function PATCH(req: NextRequest, { params }: Ctx) {
  const token = sessionToken();
  if (!token) {
    return NextResponse.json({ detail: "Sign in required" }, { status: 401 });
  }

  const { action } = (await req.json()) as { action: "publish" | "reject" };
  if (action !== "publish" && action !== "reject") {
    return NextResponse.json({ detail: "Invalid action" }, { status: 400 });
  }

  const res = await fetch(`${BASE}/api/admin/feedback/${params.id}/${action}`, {
    method: "PATCH",
    headers: { Authorization: `Bearer ${token}` },
    cache: "no-store",
  });

  const text = await res.text();
  return new NextResponse(text || null, {
    status: res.status,
    headers: { "Content-Type": res.headers.get("Content-Type") ?? "application/json" },
  });
}
