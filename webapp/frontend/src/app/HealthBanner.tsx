"use client";
import { useEffect, useState } from "react";
import { apiFetch } from "@/lib/api";
import { AlertTriangle, CheckCircle } from "lucide-react";

interface Check {
  ok: boolean;
  hint?: string;
  action?: string | null;
  path?: string;
}

export function HealthBanner() {
  const [checks, setChecks] = useState<Record<string, Check> | null>(null);

  useEffect(() => {
    apiFetch<{ ok: boolean; checks: Record<string, Check> }>("/api/health")
      .then((r) => setChecks(r.checks))
      .catch(() => {});
  }, []);

  if (!checks) return null;

  const failed = Object.entries(checks).filter(([, v]) => !v.ok);
  if (failed.length === 0) {
    return (
      <div className="flex items-center gap-2 bg-green-900/20 border border-green-700/30 rounded-lg px-4 py-2.5 text-sm text-green-300">
        <CheckCircle size={15} />
        All systems ready
      </div>
    );
  }

  return (
    <div className="bg-yellow-900/20 border border-yellow-700/30 rounded-lg px-4 py-3 text-sm">
      <div className="flex items-center gap-2 text-yellow-300 font-medium mb-2">
        <AlertTriangle size={15} />
        {failed.length} configuration issue{failed.length > 1 ? "s" : ""} detected
      </div>
      <ul className="space-y-1">
        {failed.map(([name, check]) => (
          <li key={name} className="text-yellow-200/80 text-xs flex items-start gap-1.5">
            <span className="text-yellow-500 mt-0.5">•</span>
            <span>
              <strong>{name.replace(/_/g, " ")}</strong>
              {check.hint && <> — set <code className="bg-black/30 px-1 rounded">{check.hint}</code></>}
              {check.action === "reauthorize" && (
                <> — <a href="/config" className="underline text-yellow-300">re-authorize YouTube OAuth</a></>
              )}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
