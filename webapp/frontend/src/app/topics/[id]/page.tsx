"use client";
import { useState, useCallback } from "react";
import useSWR from "swr";
import Link from "next/link";
import { apiFetch } from "@/lib/api";
import type { TopicDetail } from "@/lib/types";
import { StatusBadge } from "@/components/StatusBadge";
import {
  ExternalLink, Play, RotateCcw, FileText, Music, Video,
  Image as ImageIcon, Subtitles, Instagram,
} from "lucide-react";

const fetcher = (url: string) => apiFetch<TopicDetail>(url);

const STAGES = [
  { n: 1, label: "Script" },
  { n: 2, label: "Image" },
  { n: 3, label: "Audio" },
  { n: 4, label: "Subtitles" },
  { n: 5, label: "Audio QA" },
  { n: 6, label: "Subtitle QA" },
  { n: 7, label: "Render" },
  { n: 8, label: "Upload YouTube" },
  { n: 9, label: "Upload Captions" },
];

type TabKey = "overview" | "script" | "media" | "pipeline" | "youtube" | "instagram";

export default function TopicDetailPage({ params }: { params: { id: string } }) {
  const { data: topic, mutate } = useSWR(`/api/topics/${params.id}`, fetcher, {
    refreshInterval: 15000,
  });
  const [tab, setTab] = useState<TabKey>("overview");
  const [selectedStages, setSelectedStages] = useState<Set<number>>(new Set());
  const [launching, setLaunching] = useState(false);

  const toggleStage = (n: number) =>
    setSelectedStages((s) => {
      const next = new Set(s);
      next.has(n) ? next.delete(n) : next.add(n);
      return next;
    });

  const runStages = useCallback(async () => {
    if (!topic?.media.artifact || selectedStages.size === 0) return;
    setLaunching(true);
    try {
      const job = await apiFetch<{ job_id: string }>("/api/pipeline/run-stages", {
        method: "POST",
        body: JSON.stringify({
          artifact_path: topic.media.artifact,
          stages: [...selectedStages].sort(),
        }),
      });
      window.location.href = `/run?job=${job.job_id}`;
    } catch (err) {
      alert(String(err));
    } finally {
      setLaunching(false);
    }
  }, [topic, selectedStages]);

  const runFull = useCallback(async () => {
    if (!topic) return;
    setLaunching(true);
    try {
      const job = await apiFetch<{ job_id: string }>("/api/pipeline/run", {
        method: "POST",
        body: JSON.stringify({ topic_id: topic.id, no_upload: true }),
      });
      window.location.href = `/run?job=${job.job_id}`;
    } catch (err) {
      alert(String(err));
      setLaunching(false);
    }
  }, [topic]);

  const resetStatus = useCallback(async () => {
    if (!topic || !confirm("Reset to pending?")) return;
    await apiFetch(`/api/topics/${topic.id}/status?status=pending`, { method: "PATCH" });
    mutate();
  }, [topic, mutate]);

  if (!topic) return <div className="text-gray-400 text-sm">Loading…</div>;

  const TABS: { key: TabKey; label: string }[] = [
    { key: "overview", label: "Overview" },
    { key: "script", label: "Script" },
    { key: "media", label: "Media" },
    { key: "pipeline", label: "Pipeline" },
    { key: "youtube", label: "YouTube" },
    { key: "instagram", label: "Instagram" },
  ];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <Link href="/topics" className="text-xs text-gray-500 hover:text-gray-300">← Topics</Link>
          <h1 className="text-xl font-bold mt-1">{topic.script_title || topic.title_hint}</h1>
          <div className="flex items-center gap-3 mt-2 text-sm text-gray-400">
            <span>{topic.level}</span>
            <span>·</span>
            <span>{topic.category.replace("_", " ")}</span>
            <span>·</span>
            <code className="text-xs bg-gray-800 px-1.5 py-0.5 rounded">{topic.id}</code>
            <StatusBadge status={topic.status} />
          </div>
        </div>
        <div className="flex gap-2 shrink-0">
          <button
            onClick={resetStatus}
            className="flex items-center gap-1.5 text-sm text-gray-400 hover:text-yellow-400 border border-gray-700 px-3 py-1.5 rounded-lg"
          >
            <RotateCcw size={14} /> Reset
          </button>
          <button
            onClick={runFull}
            disabled={launching}
            className="flex items-center gap-1.5 text-sm bg-sky-600 hover:bg-sky-500 text-white px-3 py-1.5 rounded-lg disabled:opacity-50"
          >
            <Play size={14} /> Run Full Pipeline
          </button>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 border-b border-gray-800">
        {TABS.map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={`px-4 py-2 text-sm font-medium border-b-2 transition -mb-px ${
              tab === t.key
                ? "border-sky-500 text-sky-400"
                : "border-transparent text-gray-400 hover:text-white"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* Tab content */}
      {tab === "overview" && <OverviewTab topic={topic} />}
      {tab === "script" && <ScriptTab topic={topic} />}
      {tab === "media" && <MediaTab topic={topic} />}
      {tab === "pipeline" && (
        <PipelineTab
          topic={topic}
          selectedStages={selectedStages}
          toggleStage={toggleStage}
          runStages={runStages}
          launching={launching}
        />
      )}
      {tab === "youtube" && <YoutubeTab topic={topic} />}
      {tab === "instagram" && <InstagramTab topic={topic} mutate={mutate} />}
    </div>
  );
}

// ---------- Tab components ----------

function OverviewTab({ topic }: { topic: TopicDetail }) {
  const rows = [
    ["Topic ID", topic.id],
    ["Track", topic.track],
    ["Level", topic.level],
    ["Category", topic.category],
    ["Status", <StatusBadge key="s" status={topic.status} />],
    ["Use count", String(topic.use_count)],
    ["Last used", topic.last_used_at || "—"],
    ["Playlist", topic.playlist_name || "—"],
    ["Published at", topic.published_at || "—"],
  ] as const;

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
      <table className="w-full text-sm">
        <tbody>
          {rows.map(([label, value]) => (
            <tr key={label} className="border-b border-gray-800/40">
              <td className="px-4 py-3 text-gray-400 w-40 font-medium">{label}</td>
              <td className="px-4 py-3 text-gray-100">{value}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ScriptTab({ topic }: { topic: TopicDetail }) {
  const script = topic.script as any;
  if (!script) return <p className="text-gray-500">No script generated yet.</p>;

  const dialogue: Array<{ Speaker1?: string; Speaker2?: string } | { speaker: string; line: string }> =
    script.dialogue || script.script || [];

  return (
    <div className="space-y-6">
      {/* Dialogue */}
      <section>
        <h3 className="text-sm font-semibold text-gray-400 uppercase tracking-wide mb-3">Dialogue</h3>
        <div className="space-y-2">
          {dialogue.map((line: any, i: number) => {
            const speaker = line.speaker || Object.keys(line)[0];
            const text = line.line || line[speaker];
            const isLeft = speaker === "Speaker1";
            return (
              <div key={i} className={`flex gap-3 ${isLeft ? "" : "flex-row-reverse"}`}>
                <div className={`text-xs px-1.5 py-0.5 rounded self-start mt-1 ${isLeft ? "bg-sky-800 text-sky-200" : "bg-purple-800 text-purple-200"}`}>
                  {speaker}
                </div>
                <div className={`bg-gray-800 rounded-xl px-4 py-2.5 text-sm max-w-lg ${isLeft ? "rounded-tl-sm" : "rounded-tr-sm"}`}>
                  {text}
                </div>
              </div>
            );
          })}
        </div>
      </section>

      {/* Grammar notes */}
      {script.grammar_notes?.length > 0 && (
        <section>
          <h3 className="text-sm font-semibold text-gray-400 uppercase tracking-wide mb-3">Grammar Notes</h3>
          {script.grammar_notes.map((g: any, i: number) => (
            <div key={i} className="bg-gray-800/50 border border-gray-700 rounded-lg px-4 py-3 mb-2">
              <div className="font-medium text-white text-sm">{g.title}</div>
              <div className="text-gray-400 text-sm mt-1">{g.explanation}</div>
            </div>
          ))}
        </section>
      )}

      {/* Quiz */}
      {script.quiz?.length > 0 && (
        <section>
          <h3 className="text-sm font-semibold text-gray-400 uppercase tracking-wide mb-3">Quiz ({script.quiz.length} questions)</h3>
          {script.quiz.map((q: any, i: number) => (
            <div key={i} className="bg-gray-800/50 border border-gray-700 rounded-lg px-4 py-3 mb-2 text-sm">
              <div className="text-white font-medium">{i + 1}. {q.question}</div>
              <div className="text-green-400 mt-1">Answer: {q.answer}</div>
              {q.explanation && <div className="text-gray-500 mt-0.5">{q.explanation}</div>}
            </div>
          ))}
        </section>
      )}
    </div>
  );
}

function MediaTab({ topic }: { topic: TopicDetail }) {
  const m = topic.media;
  return (
    <div className="space-y-6">
      {/* Audio */}
      <section>
        <h3 className="text-sm font-semibold text-gray-400 uppercase tracking-wide mb-3 flex items-center gap-2"><Music size={14} /> Audio</h3>
        {m.audio ? (
          <audio controls src={`/api/media/audio?path=${encodeURIComponent(m.audio)}`} className="w-full" />
        ) : <p className="text-gray-500 text-sm">No audio generated yet.</p>}
      </section>

      {/* Video */}
      <section>
        <h3 className="text-sm font-semibold text-gray-400 uppercase tracking-wide mb-3 flex items-center gap-2"><Video size={14} /> Video</h3>
        {m.video ? (
          <video controls src={`/api/media/video?path=${encodeURIComponent(m.video)}`} className="w-full rounded-xl max-h-96" />
        ) : <p className="text-gray-500 text-sm">No video rendered yet.</p>}
      </section>

      {/* Images */}
      <section>
        <h3 className="text-sm font-semibold text-gray-400 uppercase tracking-wide mb-3 flex items-center gap-2"><ImageIcon size={14} /> Scene Images</h3>
        {m.images.length > 0 ? (
          <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
            {m.images.map((img, i) => (
              <img key={i} src={`/api/media/image?path=${encodeURIComponent(img)}`} alt={`Scene ${i + 1}`} className="rounded-lg border border-gray-700 object-cover aspect-video" />
            ))}
          </div>
        ) : <p className="text-gray-500 text-sm">No images generated yet.</p>}
      </section>

      {/* Subtitles */}
      <section>
        <h3 className="text-sm font-semibold text-gray-400 uppercase tracking-wide mb-3 flex items-center gap-2"><FileText size={14} /> Subtitles</h3>
        <div className="flex gap-3 flex-wrap">
          {m.subtitles.srt_en && (
            <a href={`/api/media/subtitle?path=${encodeURIComponent(m.subtitles.srt_en)}`} target="_blank" rel="noopener noreferrer" className="text-xs text-sky-400 hover:underline border border-sky-700/40 px-3 py-1.5 rounded-lg">
              📄 English SRT
            </a>
          )}
          {m.subtitles.srt_nl && (
            <a href={`/api/media/subtitle?path=${encodeURIComponent(m.subtitles.srt_nl)}`} target="_blank" rel="noopener noreferrer" className="text-xs text-sky-400 hover:underline border border-sky-700/40 px-3 py-1.5 rounded-lg">
              📄 Dutch SRT
            </a>
          )}
          {m.subtitles.ass && (
            <a href={`/api/media/subtitle?path=${encodeURIComponent(m.subtitles.ass)}`} target="_blank" rel="noopener noreferrer" className="text-xs text-sky-400 hover:underline border border-sky-700/40 px-3 py-1.5 rounded-lg">
              🎨 Karaoke ASS
            </a>
          )}
          {!m.subtitles.srt_en && !m.subtitles.srt_nl && !m.subtitles.ass && (
            <p className="text-gray-500 text-sm">No subtitles generated yet.</p>
          )}
        </div>
      </section>

      {/* Checkpoint warning */}
      {m.checkpoint && (
        <div className="bg-yellow-900/20 border border-yellow-700/30 rounded-lg px-4 py-3 text-sm text-yellow-300">
          ⚠ Interrupted run checkpoint found: <code className="text-xs">{m.checkpoint}</code>
          <br />
          <Link href={`/run`} className="underline text-xs mt-1 block">Resume via Run Pipeline → Resume checkpoint</Link>
        </div>
      )}
    </div>
  );
}

function PipelineTab({
  topic, selectedStages, toggleStage, runStages, launching,
}: {
  topic: TopicDetail;
  selectedStages: Set<number>;
  toggleStage: (n: number) => void;
  runStages: () => void;
  launching: boolean;
}) {
  const m = topic.media;
  const stageStatus = (n: number) => {
    if (n === 1) return m.artifact ? "done" : "missing";
    if (n === 2) return m.images.length > 0 ? "done" : "missing";
    if (n === 3) return m.audio ? "done" : "missing";
    if (n === 4) return m.subtitles.ass ? "done" : "missing";
    if (n === 7) return m.video ? "done" : "missing";
    if (n === 8) return topic.youtube_video_id ? "done" : "missing";
    return "unknown";
  };

  return (
    <div className="space-y-5">
      <p className="text-sm text-gray-400">Select stages to re-run, then click Run Selected Stages.</p>
      <div className="grid grid-cols-3 gap-3">
        {STAGES.map((s) => {
          const st = stageStatus(s.n);
          return (
            <button
              key={s.n}
              onClick={() => toggleStage(s.n)}
              className={`flex items-center gap-2 px-4 py-3 rounded-xl border text-sm transition ${
                selectedStages.has(s.n)
                  ? "border-sky-500 bg-sky-900/30 text-sky-200"
                  : "border-gray-700 bg-gray-800/30 text-gray-300 hover:border-gray-600"
              }`}
            >
              <span className={`w-2 h-2 rounded-full ${st === "done" ? "bg-green-500" : "bg-gray-600"}`} />
              {s.n}. {s.label}
            </button>
          );
        })}
      </div>
      {m.artifact && (
        <div>
          <button
            onClick={runStages}
            disabled={selectedStages.size === 0 || launching}
            className="bg-sky-600 hover:bg-sky-500 text-white px-4 py-2 rounded-lg text-sm font-medium disabled:opacity-40"
          >
            {launching ? "Starting…" : `Run ${selectedStages.size} stage(s)`}
          </button>
        </div>
      )}
      {!m.artifact && (
        <p className="text-yellow-400 text-sm">No artifact found — run the full pipeline first.</p>
      )}
    </div>
  );
}

function YoutubeTab({ topic }: { topic: TopicDetail }) {
  if (!topic.youtube_video_id) {
    return (
      <div className="text-gray-400 text-sm space-y-3">
        <p>This topic has not been uploaded to YouTube yet.</p>
        <p>Use the Pipeline tab to run stage 8 (Upload YouTube).</p>
      </div>
    );
  }
  const url = `https://youtube.com/watch?v=${topic.youtube_video_id}`;
  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <a href={url} target="_blank" rel="noopener noreferrer" className="flex items-center gap-2 text-red-400 hover:underline font-medium">
          <ExternalLink size={14} /> Watch on YouTube
        </a>
        <span className="text-gray-500 text-xs font-mono">{topic.youtube_video_id}</span>
      </div>
      <div className="aspect-video max-w-2xl">
        <iframe
          src={`https://www.youtube.com/embed/${topic.youtube_video_id}`}
          className="w-full h-full rounded-xl border border-gray-700"
          allowFullScreen
        />
      </div>
      <div className="text-sm text-gray-400 space-y-1">
        <div>Playlist: {topic.playlist_name || "—"}</div>
        <div>Scheduled: {topic.scheduled_at || "—"}</div>
        <div>Published: {topic.published_at || "—"}</div>
      </div>
    </div>
  );
}

function InstagramTab({ topic, mutate }: { topic: TopicDetail; mutate: () => void }) {
  const shorts = topic.media.shorts;
  const [publishing, setPublishing] = useState<string | null>(null);

  const publishDraft = async (containerId: string) => {
    if (!confirm(`Publish draft container ${containerId}?`)) return;
    setPublishing(containerId);
    try {
      const r = await apiFetch<any>(
        `/api/publish/instagram/${topic.id}/publish-draft?container_id=${containerId}`,
        { method: "POST" }
      );
      if (r.error) throw new Error(r.error.message);
      mutate();
    } catch (err) {
      alert(String(err));
    } finally {
      setPublishing(null);
    }
  };

  if (shorts.length === 0) {
    return (
      <div className="text-gray-400 text-sm space-y-3">
        <p>No Instagram Reels / Shorts found for this topic.</p>
        <p>Run the pipeline with the Render stage to generate scene shorts first.</p>
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
      {shorts.map((s, i) => (
        <div key={i} className="bg-gray-900 border border-gray-800 rounded-xl p-4 space-y-3">
          <div className="text-sm font-medium text-white">{s.scene || `Scene ${i + 1}`}</div>
          {s.description && <div className="text-xs text-gray-400">{s.description}</div>}

          {s.video_file && (
            <video
              src={`/api/media/video?path=${encodeURIComponent(s.video_file)}`}
              controls
              className="w-full rounded-lg max-h-64 bg-black"
            />
          )}

          <div className="flex items-center gap-2 flex-wrap">
            {s.permalink ? (
              <a href={s.permalink} target="_blank" rel="noopener noreferrer" className="flex items-center gap-1 text-pink-400 hover:underline text-xs">
                <Instagram size={12} /> View Reel
              </a>
            ) : s.container_id && s.draft ? (
              <button
                onClick={() => publishDraft(s.container_id!)}
                disabled={publishing === s.container_id}
                className="text-xs bg-pink-700 hover:bg-pink-600 text-white px-3 py-1.5 rounded-lg disabled:opacity-50"
              >
                {publishing === s.container_id ? "Publishing…" : "Publish Draft"}
              </button>
            ) : (
              <span className="text-xs text-gray-500">Not uploaded yet</span>
            )}

            {s.reel_id && <span className="text-xs text-gray-500 font-mono">ID: {s.reel_id}</span>}
            {s.draft && <span className="text-xs bg-yellow-800/40 text-yellow-300 px-2 py-0.5 rounded border border-yellow-700/30">Draft</span>}
          </div>
        </div>
      ))}
    </div>
  );
}
