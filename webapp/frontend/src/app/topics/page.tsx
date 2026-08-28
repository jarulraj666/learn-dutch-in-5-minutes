"use client";
import { useState, useCallback } from "react";
import useSWR from "swr";
import Link from "next/link";
import { apiFetch } from "@/lib/api";
import type { Topic } from "@/lib/types";
import { StatusBadge } from "@/components/StatusBadge";
import { Play, RotateCcw, ExternalLink, Instagram } from "lucide-react";

const fetcher = (url: string) => apiFetch<Topic[]>(url);

const LEVELS = ["A1A2", "B1", "B2"];
const CATEGORIES = ["course_intro", "common_words", "grammar", "vocabulary", "dialogue"];
const STATUSES = ["pending", "generated", "done"];

export default function TopicsPage() {
  const [level, setLevel] = useState("");
  const [category, setCategory] = useState("");
  const [status, setStatus] = useState("");
  const [search, setSearch] = useState("");
  const [running, setRunning] = useState<Set<string>>(new Set());

  const params = new URLSearchParams();
  if (level) params.set("level", level);
  if (category) params.set("category", category);
  if (status) params.set("status", status);
  if (search) params.set("search", search);

  const { data: topics, mutate } = useSWR(`/api/topics?${params}`, fetcher, {
    refreshInterval: 10000,
  });

  const runTopic = useCallback(
    async (topicId: string) => {
      setRunning((s) => new Set(s).add(topicId));
      try {
        const job = await apiFetch<{ job_id: string }>("/api/pipeline/run", {
          method: "POST",
          body: JSON.stringify({ topic_id: topicId, no_upload: true }),
        });
        window.location.href = `/run?job=${job.job_id}`;
      } catch (err) {
        alert(String(err));
        setRunning((s) => {
          const next = new Set(s);
          next.delete(topicId);
          return next;
        });
      }
    },
    []
  );

  const resetStatus = useCallback(async (topicId: string) => {
    if (!confirm(`Reset "${topicId}" to pending?`)) return;
    await apiFetch(`/api/topics/${topicId}/status?status=pending`, { method: "PATCH" });
    mutate();
  }, [mutate]);

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Topics</h1>
        <Link
          href="/run"
          className="bg-sky-600 hover:bg-sky-500 text-white px-4 py-2 rounded-lg text-sm font-medium"
        >
          + Run Pipeline
        </Link>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap gap-3">
        <input
          className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white placeholder-gray-500 w-56"
          placeholder="Search topics…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <Select value={level} onChange={setLevel} options={LEVELS} placeholder="All levels" />
        <Select value={category} onChange={setCategory} options={CATEGORIES} placeholder="All categories" />
        <Select value={status} onChange={setStatus} options={STATUSES} placeholder="All statuses" />
        {(level || category || status || search) && (
          <button
            onClick={() => { setLevel(""); setCategory(""); setStatus(""); setSearch(""); }}
            className="text-xs text-gray-400 hover:text-white px-2"
          >
            Clear filters
          </button>
        )}
      </div>

      {/* Table */}
      <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-800 text-left">
              {["Topic", "Level", "Category", "Status", "Use count", "Last used", "YouTube", "Instagram", "Actions"].map((h) => (
                <th key={h} className="px-4 py-3 text-gray-400 font-medium whitespace-nowrap">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {!topics ? (
              <tr><td colSpan={9} className="px-4 py-8 text-center text-gray-500">Loading…</td></tr>
            ) : topics.length === 0 ? (
              <tr><td colSpan={9} className="px-4 py-8 text-center text-gray-500">No topics found</td></tr>
            ) : (
              topics.map((t) => (
                <tr key={t.id} className="border-b border-gray-800/40 hover:bg-gray-800/30 transition">
                  <td className="px-4 py-3">
                    <Link href={`/topics/${t.id}`} className="text-sky-400 hover:underline font-medium">
                      {t.script_title || t.title_hint}
                    </Link>
                    <div className="text-xs text-gray-500 font-mono mt-0.5">{t.id}</div>
                  </td>
                  <td className="px-4 py-3 text-gray-300">{t.level}</td>
                  <td className="px-4 py-3 text-gray-300">{t.category.replace("_", " ")}</td>
                  <td className="px-4 py-3"><StatusBadge status={t.status} /></td>
                  <td className="px-4 py-3 text-gray-400 text-center">{t.use_count}</td>
                  <td className="px-4 py-3 text-gray-500 text-xs whitespace-nowrap">
                    {t.last_used_at ? new Date(t.last_used_at).toLocaleDateString() : "—"}
                  </td>
                  <td className="px-4 py-3">
                    {t.youtube_video_id ? (
                      <a
                        href={`https://youtube.com/watch?v=${t.youtube_video_id}`}
                        target="_blank" rel="noopener noreferrer"
                        className="flex items-center gap-1 text-red-400 hover:underline text-xs"
                      >
                        <ExternalLink size={12} /> Watch
                      </a>
                    ) : <span className="text-gray-600">—</span>}
                  </td>
                  <td className="px-4 py-3">
                    <Link href={`/topics/${t.id}#instagram`} className="text-pink-400 hover:underline text-xs flex items-center gap-1">
                      <Instagram size={12} /> Reels
                    </Link>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2">
                      <button
                        onClick={() => runTopic(t.id)}
                        disabled={running.has(t.id)}
                        title="Run pipeline"
                        className="text-sky-400 hover:text-sky-300 disabled:opacity-40"
                      >
                        <Play size={15} />
                      </button>
                      <button
                        onClick={() => resetStatus(t.id)}
                        title="Reset to pending"
                        className="text-gray-500 hover:text-yellow-400"
                      >
                        <RotateCcw size={14} />
                      </button>
                    </div>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function Select({
  value, onChange, options, placeholder,
}: {
  value: string;
  onChange: (v: string) => void;
  options: string[];
  placeholder: string;
}) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white"
    >
      <option value="">{placeholder}</option>
      {options.map((o) => (
        <option key={o} value={o}>{o.replace("_", " ")}</option>
      ))}
    </select>
  );
}
