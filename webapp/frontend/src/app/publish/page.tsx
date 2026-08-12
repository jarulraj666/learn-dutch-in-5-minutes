"use client";
import { useState } from "react";
import useSWR from "swr";
import { apiFetch } from "@/lib/api";
import type { PublishJob } from "@/lib/types";
import { ExternalLink } from "lucide-react";

const fetcher = (url: string) => apiFetch<PublishJob[]>(url);

function StatusBadge({ status }: { status: string }) {
  const map: Record<string, string> = {
    pending: "bg-yellow-500/20 text-yellow-300",
    published: "bg-green-500/20 text-green-300",
    failed: "bg-red-500/20 text-red-300",
    scheduled: "bg-blue-500/20 text-blue-300",
  };
  return (
    <span className={`inline-block px-2 py-0.5 rounded text-xs font-medium ${map[status] ?? "bg-gray-700 text-gray-300"}`}>
      {status}
    </span>
  );
}

export default function PublishPage() {
  const [filter, setFilter] = useState("");
  const { data: jobs, mutate } = useSWR(`/api/publish/queue${filter ? `?status=${filter}` : ""}`, fetcher, {
    refreshInterval: 15000,
  });

  const [dryRunOutput, setDryRunOutput] = useState("");
  const [executing, setExecuting] = useState(false);

  const dryRun = async () => {
    const r = await apiFetch<{ stdout: string; stderr: string }>("/api/publish/dry-run", { method: "POST" });
    setDryRunOutput((r.stdout || "") + (r.stderr ? `\n[stderr]\n${r.stderr}` : ""));
  };

  const execute = async () => {
    if (!confirm("Upload all pending jobs to YouTube now?")) return;
    setExecuting(true);
    try {
      const r = await apiFetch<{ stdout: string; stderr: string }>("/api/publish/execute", { method: "POST" });
      setDryRunOutput((r.stdout || "") + (r.stderr ? `\n[stderr]\n${r.stderr}` : ""));
      mutate();
    } finally {
      setExecuting(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Publish Queue</h1>
        <div className="flex gap-2">
          <button
            onClick={dryRun}
            className="border border-gray-600 text-gray-300 hover:text-white px-4 py-2 rounded-lg text-sm"
          >
            Dry Run
          </button>
          <button
            onClick={execute}
            disabled={executing}
            className="bg-red-700 hover:bg-red-600 text-white px-4 py-2 rounded-lg text-sm font-medium disabled:opacity-50"
          >
            {executing ? "Uploading…" : "Execute Uploads"}
          </button>
        </div>
      </div>

      {/* Status filter */}
      <div className="flex gap-2">
        {["", "pending", "scheduled", "published", "failed"].map((s) => (
          <button
            key={s}
            onClick={() => setFilter(s)}
            className={`px-3 py-1.5 rounded-lg text-sm border transition ${
              filter === s ? "border-sky-600 bg-sky-900/30 text-sky-300" : "border-gray-700 text-gray-400 hover:border-gray-600"
            }`}
          >
            {s || "All"}
          </button>
        ))}
      </div>

      {/* Table */}
      <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-800 text-left">
              {["Title", "Level", "Category", "Playlist", "Scheduled", "Status", "YouTube", "Published"].map((h) => (
                <th key={h} className="px-4 py-3 text-gray-400 font-medium whitespace-nowrap">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {!jobs ? (
              <tr><td colSpan={8} className="px-4 py-8 text-center text-gray-500">Loading…</td></tr>
            ) : jobs.length === 0 ? (
              <tr><td colSpan={8} className="px-4 py-8 text-center text-gray-500">No jobs found</td></tr>
            ) : (
              jobs.map((job) => (
                <tr key={job.id} className="border-b border-gray-800/40 hover:bg-gray-800/20">
                  <td className="px-4 py-3 text-gray-200 max-w-xs truncate">
                    {job.script_title || job.title_hint}
                  </td>
                  <td className="px-4 py-3 text-gray-400">{job.level}</td>
                  <td className="px-4 py-3 text-gray-400">{job.category?.replace("_", " ")}</td>
                  <td className="px-4 py-3 text-gray-500 text-xs truncate max-w-[12rem]">{job.playlist_name || "—"}</td>
                  <td className="px-4 py-3 text-gray-400 text-xs whitespace-nowrap">
                    {job.scheduled_at ? new Date(job.scheduled_at).toLocaleString() : "—"}
                  </td>
                  <td className="px-4 py-3"><StatusBadge status={job.status} /></td>
                  <td className="px-4 py-3">
                    {job.youtube_video_id ? (
                      <a
                        href={`https://youtube.com/watch?v=${job.youtube_video_id}`}
                        target="_blank" rel="noopener noreferrer"
                        className="flex items-center gap-1 text-red-400 hover:underline text-xs"
                      >
                        <ExternalLink size={12} /> Watch
                      </a>
                    ) : <span className="text-gray-600">—</span>}
                  </td>
                  <td className="px-4 py-3 text-gray-500 text-xs">
                    {job.published_at ? new Date(job.published_at).toLocaleDateString() : "—"}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Dry run output */}
      {dryRunOutput && (
        <div className="bg-gray-950 border border-gray-800 rounded-xl p-4">
          <h3 className="text-sm font-semibold text-gray-400 mb-2">Output</h3>
          <pre className="text-xs text-gray-300 whitespace-pre-wrap font-mono">{dryRunOutput}</pre>
        </div>
      )}
    </div>
  );
}
