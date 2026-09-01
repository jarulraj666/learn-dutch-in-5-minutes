"use client";
import { useState } from "react";
import useSWR from "swr";
import Link from "next/link";
import { apiFetch } from "@/lib/api";
import { StatusBadge } from "@/components/StatusBadge";

type MockExamJob = {
  id: string;
  section: string;
  exam_number: number;
  level: string;
  status: string;
  exported_at: string | null;
  created_at: string;
  updated_at: string | null;
};

const SECTIONS = ["reading", "listening", "writing", "speaking", "knm"];
const STAGES = ["draft", "content_generated", "media_generated", "exported"];

const fetcher = (url: string) => apiFetch<MockExamJob[]>(url);

export default function MockExamsPage() {
  const [section, setSection] = useState("");
  const params = new URLSearchParams();
  if (section) params.set("section", section);

  const { data: jobs, mutate } = useSWR(`/api/mock-exams?${params}`, fetcher, {
    refreshInterval: 5000,
  });

  const counts = STAGES.reduce<Record<string, number>>((acc, s) => {
    acc[s] = jobs?.filter((j) => j.status === s).length ?? 0;
    return acc;
  }, {});

  const runStage = async (stage: string, sec?: string, examNumber?: number) => {
    await apiFetch("/api/mock-exams/run", {
      method: "POST",
      body: JSON.stringify({ stage, section: sec, exam_number: examNumber }),
    });
    mutate();
  };

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">A2 Mock Exams</h1>
        <div className="flex gap-2">
          {STAGES.map((s) => (
            <div key={s} className="bg-gray-800 rounded px-3 py-1.5 text-xs">
              <span className="text-gray-400">{s.replace("_", " ")}: </span>
              <span className="font-semibold text-white">{counts[s]}</span>
              <span className="text-gray-500"> / 25</span>
            </div>
          ))}
        </div>
      </div>

      <div className="flex items-center gap-2">
        <select
          value={section}
          onChange={(e) => setSection(e.target.value)}
          className="bg-gray-800 border border-gray-700 rounded px-2 py-1.5 text-sm"
        >
          <option value="">All sections</option>
          {SECTIONS.map((s) => (
            <option key={s} value={s}>{s}</option>
          ))}
        </select>
        <button
          onClick={() => runStage("content", section || undefined)}
          className="bg-sky-600 hover:bg-sky-500 text-white px-3 py-1.5 rounded text-sm"
        >
          Generate Content{section ? ` (${section})` : " (all 25)"}
        </button>
      </div>

      <table className="w-full text-sm">
        <thead className="text-gray-400 text-left border-b border-gray-800">
          <tr>
            <th className="py-2">Exam</th>
            <th>Section</th>
            <th>#</th>
            <th>Status</th>
            <th>Exported</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {(jobs ?? []).map((j) => (
            <tr key={j.id} className="border-b border-gray-800/50 hover:bg-gray-800/30">
              <td className="py-2">
                <Link href={`/mock-exams/${j.id}`} className="text-sky-400 hover:underline">
                  {j.id}
                </Link>
              </td>
              <td>{j.section}</td>
              <td>{j.exam_number}</td>
              <td><StatusBadge status={j.status} /></td>
              <td className="text-gray-400">{j.exported_at ?? "—"}</td>
              <td className="flex gap-2 py-2">
                <button
                  onClick={() => runStage("content", j.section, j.exam_number)}
                  className="text-xs text-sky-400 hover:underline"
                >
                  Content
                </button>
                <button
                  onClick={() => runStage("media", j.section, j.exam_number)}
                  className="text-xs text-sky-400 hover:underline"
                >
                  Media
                </button>
                <button
                  onClick={() => runStage("export", j.section, j.exam_number)}
                  className="text-xs text-sky-400 hover:underline"
                >
                  Export
                </button>
              </td>
            </tr>
          ))}
          {jobs && jobs.length === 0 && (
            <tr>
              <td colSpan={6} className="py-6 text-center text-gray-500">
                No mock exams generated yet. Click &quot;Generate Content&quot; to start.
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
