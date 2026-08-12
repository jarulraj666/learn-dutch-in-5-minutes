// Server-side: call the FastAPI backend directly (absolute URL).
// Client-side: use relative path so Next.js rewrites proxy to the backend.
const SERVER_API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

function baseUrl() {
  return typeof window === "undefined" ? SERVER_API : "";
}

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const url = `${baseUrl()}${path}`;
  const res = await fetch(url, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`API error ${res.status}: ${text}`);
  }
  return res.json();
}

export const API_URL = SERVER_API;
