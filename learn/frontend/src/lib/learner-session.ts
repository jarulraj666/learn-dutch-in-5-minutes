import { sessionToken } from "@/lib/session-token";

const BASE = process.env.LEARN_API_URL ?? "http://localhost:8001";

export type LearnerSession = {
  user: {
    id: string;
    name: string | null;
    email: string | null;
    image: string | null;
    role?: string;
    is_admin?: boolean;
  };
};

export async function learnerSession(): Promise<LearnerSession | null> {
  const token = sessionToken();
  if (!token) return null;
  const response = await fetch(`${BASE}/api/auth/session`, {
    headers: { Authorization: `Bearer ${token}` },
    cache: "no-store",
  });
  if (!response.ok) return null;
  return response.json();
}