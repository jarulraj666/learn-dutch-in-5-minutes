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

type PipelineRun = {
  job_id: string;
  started_at: string;
  args: string[];
};

const SECTIONS = ["reading", "listening", "writing", "speaking", "knm"];
const STAGES = ["draft", "content_generated", "media_generated", "exported"];

const fetcher = (url: string) => apiFetch<MockExamJob[]>(url);

export default function MockExamsPage() {
  const [section, setSection] = useState("");
  const [examNumber, setExamNumber] = useState(1);
  const [pipelineRun, setPipelineRun] = useState<PipelineRun | null>(null);
  const params = new URLSearchParams();
  if (section) params.set("section", section);

  const { data: jobs, mutate } = useSWR(`/api/mock-exams?${params}`, fetcher, {
    refreshInterval: 5000,
  });

  const counts = STAGES.reduce<Record<string, number>>((acc, s) => {
    acc[s] = jobs?.filter((j) => j.status === s).length ?? 0;
    return acc;
  }, {});

  const runStage = async (stage: string, sec?: string, examNumber?: number, publish = false) => {
    try {
      const run = await apiFetch<PipelineRun>("/api/mock-exams/run", {
        method: "POST",
        body: JSON.stringify({ stage, section: sec, exam_number: examNumber, publish }),
      });
      setPipelineRun(run);
      mutate();
    } catch (error) {
      window.alert(String(error));
    }
  };

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">A2 Mock Exams</h1>
          <p className="mt-1 text-sm text-gray-400">Admin management: generate, process, and publish practice exams.</p>
        </div>
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

      <p className="text-sm text-gray-400">
        Generate one numbered exam or generate all five exams in the selected category. Existing exams remain in the list.
      </p>
      {pipelineRun && (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-sky-700/50 bg-sky-900/20 px-4 py-3 text-sm">
          <div>
            <p className="font-medium text-sky-200">Pipeline run started</p>
            <p className="mt-1 font-mono text-xs text-sky-400">{pipelineRun.args.slice(2).join(" ")}</p>
          </div>
          <Link
            href={`/run?job=${pipelineRun.job_id}`}
            className="rounded-lg bg-sky-600 px-3 py-2 font-medium text-white hover:bg-sky-500"
          >
            View live pipeline run
          </Link>
        </div>
      )}
      <div className="flex flex-wrap items-end gap-2">
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
        <label className="text-xs text-gray-400">
          Specific exam number
          <input
            type="number"
            min={1}
            max={99}
            value={examNumber}
            onChange={(e) => setExamNumber(Number(e.target.value))}
            className="ml-2 w-20 bg-gray-800 border border-gray-700 rounded px-2 py-1.5 text-sm text-white"
          />
        </label>
        <button
          onClick={() => runStage("content", section, examNumber)}
          disabled={!section || examNumber < 1 || examNumber > 99}
          className="bg-emerald-600 hover:bg-emerald-500 disabled:cursor-not-allowed disabled:opacity-50 text-white px-3 py-1.5 rounded text-sm"
        >
          Generate Exam #{examNumber || ""}
        </button>
        <button
          onClick={() => runStage("content", section || undefined)}
          className="bg-sky-600 hover:bg-sky-500 text-white px-3 py-1.5 rounded text-sm"
        >
          {section ? `Generate all 5 ${section} exams` : "Generate all 5 exams in every category"}
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
                  onClick={() => runStage("production_sync", j.section, j.exam_number)}
                  className="text-xs text-sky-400 hover:underline"
                >
                  Export & publish
                </button>
                <button
                  onClick={() => runStage("export", j.section, j.exam_number, true)}
                  className="text-xs text-amber-400 hover:underline"
                >
                  Export & publish locally
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
