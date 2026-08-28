import { cookies } from "next/headers";

/**
 * FastAPI owns the opaque database session token. It is forwarded to the
 * backend as a bearer token and never exposed to client JS.
 */
export function sessionToken(): string | undefined {
  const jar = cookies();
  return (
    jar.get("learn-session-token")?.value ??
    jar.get("__Secure-authjs.session-token")?.value ??
    jar.get("authjs.session-token")?.value
  );
}
