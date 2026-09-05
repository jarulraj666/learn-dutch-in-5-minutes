"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

const SECTIONS = ["reading", "listening", "writing", "speaking", "knm"] as const;
const STAGES = ["content", "media", "question_audio", "export", "production_sync"] as const;

/** Kicks off pipeline.tools.generate_and_export_mock_exams in the background; stages must be run in order. */
export function GenerateExamForm() {
  const router = useRouter();
  const [section, setSection] = useState<(typeof SECTIONS)[number]>("reading");
  const [examNumber, setExamNumber] = useState(1);
  const [stage, setStage] = useState<(typeof STAGES)[number]>("content");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setMessage(null);
    try {
      const res = await fetch("/api/admin/mock-exams/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ section, exam_number: examNumber, stage }),
      });
      const data = await res.json();
      setMessage(res.ok ? data.message : data.detail ?? "Something went wrong.");
      if (res.ok) router.refresh();
    } catch {
      setMessage("Could not reach the server.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="card flex flex-wrap items-end gap-4 p-5">
      <label className="text-sm">
        <span className="block font-semibold text-slate-700">Section</span>
        <select
          value={section}
          onChange={(e) => setSection(e.target.value as (typeof SECTIONS)[number])}
          className="mt-1 rounded-lg border border-slate-200 px-3 py-2 text-sm"
        >
          {SECTIONS.map((s) => (
            <option key={s} value={s}>{s}</option>
          ))}
        </select>
      </label>
      <label className="text-sm">
        <span className="block font-semibold text-slate-700">Exam number</span>
        <input
          type="number"
          min={1}
          max={99}
          value={examNumber}
          onChange={(e) => setExamNumber(Number(e.target.value))}
          className="mt-1 w-24 rounded-lg border border-slate-200 px-3 py-2 text-sm"
        />
      </label>
      <label className="text-sm">
        <span className="block font-semibold text-slate-700">Stage</span>
        <select
          value={stage}
          onChange={(e) => setStage(e.target.value as (typeof STAGES)[number])}
          className="mt-1 rounded-lg border border-slate-200 px-3 py-2 text-sm"
        >
          {STAGES.map((s) => (
            <option key={s} value={s}>{s}</option>
          ))}
        </select>
      </label>
      <button type="submit" disabled={busy} className="btn-primary px-5 py-2 text-sm disabled:opacity-50">
        {busy ? "Starting…" : "Generate"}
      </button>
      {message && <p className="w-full text-sm text-slate-600">{message}</p>}
    </form>
  );
}
