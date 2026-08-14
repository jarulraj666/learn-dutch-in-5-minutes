"use client";
import { useState, useEffect, useRef, useCallback, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import useSWR from "swr";
import { apiFetch, API_URL } from "@/lib/api";
import type { PipelineJob } from "@/lib/types";

const fetcher = (url: string) => apiFetch<PipelineJob>(url);

function RunPageInner() {
  const searchParams = useSearchParams();
  const initialJobId = searchParams.get("job");
  const parallelJobId = searchParams.get("parallel"); // second parallel job

  // Form state
  const [level, setLevel] = useState("A1A2");
  const [category, setCategory] = useState("dialogue");
  const [topicId, setTopicId] = useState("");
  const [count, setCount] = useState(1);
  const [noUpload, setNoUpload] = useState(true);
  const [scriptOnly, setScriptOnly] = useState(false);
  const [resumeCheckpoint, setResumeCheckpoint] = useState("");

  // Job tracking
  const [jobId, setJobId] = useState<string | null>(initialJobId);
  const [logs, setLogs] = useState<string[]>([]);
  const [streaming, setStreaming] = useState(false);
  const logEndRef = useRef<HTMLDivElement>(null);
  const esRef = useRef<EventSource | null>(null);

  const { data: job, mutate: mutateJob } = useSWR(
    jobId ? `/api/pipeline/jobs/${jobId}` : null,
    fetcher,
    { refreshInterval: jobId ? 3000 : 0 }
  );

  const { data: allJobs, mutate: mutateAll } = useSWR("/api/pipeline/jobs", (url: string) =>
    apiFetch<PipelineJob[]>(url), { refreshInterval: 5000 }
  );

  // Reconnect SSE when jobId changes
  useEffect(() => {
    if (!jobId) return;
    setLogs([]);
    setStreaming(true);

    const es = new EventSource(`${API_URL}/api/pipeline/logs/${jobId}`);
    esRef.current = es;

    es.onmessage = (e) => {
      const line: string = e.data;
      setLogs((prev) => [...prev, line]);
      if (line.startsWith("__STATUS__")) {
        es.close();
        setStreaming(false);
        mutateJob();
        mutateAll();
      }
    };
    es.onerror = () => {
      es.close();
      setStreaming(false);
    };
    return () => {
      es.close();
    };
  }, [jobId]);

  // Auto-scroll
  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [logs]);

  const startRun = useCallback(async () => {
    try {
      const payload: Record<string, unknown> = { no_upload: noUpload, script_only: scriptOnly };
      if (topicId) {
        payload.topic_id = topicId;
      } else {
        payload.level = level;
        payload.category = category;
        payload.count = count;
      }
      if (resumeCheckpoint) {
        payload.resume_checkpoint = resumeCheckpoint;
      }

      const job = await apiFetch<{ job_id: string }>("/api/pipeline/run", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      setJobId(job.job_id);
    } catch (err) {
      alert(String(err));
    }
  }, [level, category, topicId, count, noUpload, scriptOnly, resumeCheckpoint]);

  const abort = useCallback(async () => {
    if (!jobId || !confirm("Abort the running job?")) return;
    await apiFetch(`/api/pipeline/abort/${jobId}`, { method: "POST" });
    mutateJob();
  }, [jobId, mutateJob]);

  const statusColor = {
    running: "text-blue-400",
    done: "text-green-400",
    failed: "text-red-400",
    aborted: "text-yellow-400",
  };

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Run Pipeline</h1>

      <div className="grid md:grid-cols-2 gap-6">
        {/* Form */}
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-5 space-y-4">
          <h2 className="font-semibold text-white">Configure Run</h2>

          <div>
            <label className="text-xs text-gray-400 uppercase tracking-wide block mb-1">Topic ID (optional)</label>
            <input
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white placeholder-gray-500"
              placeholder="e.g. weather_chat (leave blank to auto-select)"
              value={topicId}
              onChange={(e) => setTopicId(e.target.value)}
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs text-gray-400 uppercase tracking-wide block mb-1">Level</label>
              <select
                value={level}
                onChange={(e) => setLevel(e.target.value)}
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white"
              >
                {["A1A2", "B1", "B2"].map((l) => <option key={l}>{l}</option>)}
              </select>
            </div>
            <div>
              <label className="text-xs text-gray-400 uppercase tracking-wide block mb-1">Category</label>
              <select
                value={category}
                onChange={(e) => setCategory(e.target.value)}
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white"
              >
                {["common_words", "grammar", "vocabulary", "dialogue"].map((c) => (
                  <option key={c} value={c}>{c.replace("_", " ")}</option>
                ))}
              </select>
            </div>
          </div>

          <div>
            <label className="text-xs text-gray-400 uppercase tracking-wide block mb-1">Count</label>
            <input
              type="number" min={1} max={20}
              value={count}
              onChange={(e) => setCount(Number(e.target.value))}
              className="w-24 bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white"
            />
          </div>

          <div className="space-y-2">
            <label className="flex items-center gap-2 text-sm cursor-pointer">
              <input type="checkbox" checked={noUpload} onChange={(e) => setNoUpload(e.target.checked)} className="rounded" />
              <span className="text-gray-300">Skip YouTube upload (--no-upload)</span>
            </label>
            <label className="flex items-center gap-2 text-sm cursor-pointer">
              <input type="checkbox" checked={scriptOnly} onChange={(e) => setScriptOnly(e.target.checked)} className="rounded" />
              <span className="text-gray-300">Script only (no audio/image/render)</span>
            </label>
          </div>

          <div>
            <label className="text-xs text-gray-400 uppercase tracking-wide block mb-1">Resume from artifact (optional)</label>
            <input
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white placeholder-gray-500 font-mono text-xs"
              placeholder="output/A1A2/dialogue/episode_topic_slug.json"
              value={resumeCheckpoint}
              onChange={(e) => setResumeCheckpoint(e.target.value)}
            />
          </div>

          <button
            onClick={startRun}
            disabled={streaming}
            className="w-full bg-sky-600 hover:bg-sky-500 text-white py-2.5 rounded-lg font-medium disabled:opacity-50"
          >
            {streaming ? "Running…" : "▶ Start Pipeline"}
          </button>
        </div>

        {/* Recent jobs */}
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-5 space-y-3">
          <h2 className="font-semibold text-white">Recent Jobs</h2>
          {allJobs?.length === 0 && <p className="text-gray-500 text-sm">No jobs yet.</p>}
          {allJobs?.map((j) => (
            <button
              key={j.job_id}
              onClick={() => setJobId(j.job_id)}
              className={`w-full text-left px-3 py-2.5 rounded-lg border text-sm transition ${
                j.job_id === jobId
                  ? "border-sky-600 bg-sky-900/20"
                  : "border-gray-700 hover:border-gray-600"
              }`}
            >
              <div className="flex justify-between items-center">
                <span className={`font-medium ${statusColor[j.status as keyof typeof statusColor] ?? "text-gray-300"}`}>
                  {j.status}
                </span>
                <span className="text-xs text-gray-500">{j.started_at.replace("T", " ").replace("Z", "")}</span>
              </div>
              <div className="text-xs text-gray-500 mt-0.5 font-mono truncate">{j.args.slice(2).join(" ")}</div>
            </button>
          ))}
        </div>
      </div>

      {/* Log pane(s) */}
      <div className={parallelJobId ? "grid grid-cols-2 gap-4" : ""}>
      {jobId && (
        <div className="bg-gray-950 border border-gray-800 rounded-xl overflow-hidden">
          <div className="flex items-center justify-between px-4 py-2.5 border-b border-gray-800">
            <div className="flex items-center gap-3">
              <span className="text-sm font-medium text-gray-300">
                {parallelJobId ? "Job A — Render Video" : `Job ${jobId}`}
              </span>
              {job && (
                <span className={`text-xs font-medium ${statusColor[job.status as keyof typeof statusColor] ?? "text-gray-400"}`}>
                  {job.status}
                  {job.exit_code !== null && ` (exit ${job.exit_code})`}
                </span>
              )}
              {streaming && (
                <span className="flex items-center gap-1 text-xs text-blue-400">
                  <span className="w-1.5 h-1.5 bg-blue-400 rounded-full animate-pulse" />
                  live
                </span>
              )}
            </div>
            {streaming && (
              <button onClick={abort} className="text-xs text-red-400 hover:text-red-300 border border-red-800 px-2.5 py-1 rounded">
                Abort
              </button>
            )}
          </div>
          <div className="h-96 overflow-y-auto p-4 space-y-0.5">
            {logs.filter((l) => !l.startsWith("__STATUS__")).map((l, i) => (
              <div key={i} className="log-line text-gray-300">{l}</div>
            ))}
            <div ref={logEndRef} />
          </div>
        </div>
      )}
      {parallelJobId && <ParallelJobPane jobId={parallelJobId} label="Job B — Render Shorts" />}
      </div>
    </div>
  );
}

function ParallelJobPane({ jobId, label }: { jobId: string; label: string }) {
  const [logs, setLogs] = useState<string[]>([]);
  const [streaming, setStreaming] = useState(true);
  const logEndRef = useRef<HTMLDivElement>(null);
  const { data: job } = useSWR(`/api/pipeline/jobs/${jobId}`, (url: string) =>
    apiFetch<PipelineJob>(url), { refreshInterval: 3000 }
  );
  const statusColor: Record<string, string> = {
    running: "text-blue-400", done: "text-green-400", failed: "text-red-400", aborted: "text-yellow-400",
  };
  useEffect(() => {
    const es = new EventSource(`${API_URL}/api/pipeline/logs/${jobId}`);
    es.onmessage = (e) => {
      const line: string = e.data;
      if (line.startsWith("__STATUS__")) { setStreaming(false); es.close(); return; }
      setLogs((prev) => [...prev, line]);
    };
    es.onerror = () => { setStreaming(false); es.close(); };
    return () => es.close();
  }, [jobId]);
  useEffect(() => { logEndRef.current?.scrollIntoView({ behavior: "smooth" }); }, [logs]);
  return (
    <div className="bg-gray-950 border border-gray-800 rounded-xl overflow-hidden">
      <div className="flex items-center gap-3 px-4 py-2.5 border-b border-gray-800">
        <span className="text-sm font-medium text-gray-300">{label}</span>
        {job && (
          <span className={`text-xs font-medium ${statusColor[job.status] ?? "text-gray-400"}`}>
            {job.status}{job.exit_code !== null && ` (exit ${job.exit_code})`}
          </span>
        )}
        {streaming && (
          <span className="flex items-center gap-1 text-xs text-blue-400">
            <span className="w-1.5 h-1.5 bg-blue-400 rounded-full animate-pulse" /> live
          </span>
        )}
      </div>
      <div className="h-96 overflow-y-auto p-4 space-y-0.5">
        {logs.filter((l) => !l.startsWith("__STATUS__")).map((l, i) => (
          <div key={i} className="log-line text-gray-300">{l}</div>
        ))}
        <div ref={logEndRef} />
      </div>
    </div>
  );
}

export default function RunPage() {
  return (
    <Suspense>
      <RunPageInner />
    </Suspense>
  );
}
