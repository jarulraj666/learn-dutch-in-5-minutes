import { NextResponse, type NextRequest } from "next/server";

// The Postgres adapter cannot run on the Edge runtime, so middleware only checks
// for the presence of the session cookie. Pages re-validate it with auth().
export function middleware(req: NextRequest) {
  const hasSession =
    req.cookies.has("learn-session-token") ||
    req.cookies.has("__Secure-authjs.session-token") ||
    req.cookies.has("authjs.session-token");

  if (hasSession) return NextResponse.next();

  const signin = new URL("/signin", req.url);
  signin.searchParams.set("callbackUrl", req.nextUrl.pathname);
  return NextResponse.redirect(signin);
}

export const config = {
  matcher: ["/dashboard/:path*", "/flashcards/:path*", "/profile/:path*", "/admin/:path*"],
};
