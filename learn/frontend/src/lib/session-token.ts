import { cookies } from "next/headers";

/**
 * Auth.js stores the opaque database session token in this cookie. It is
 * forwarded to the backend as a bearer token and never exposed to client JS.
 */
export function sessionToken(): string | undefined {
  const jar = cookies();
  return (
    jar.get("__Secure-authjs.session-token")?.value ??
    jar.get("authjs.session-token")?.value
  );
}
