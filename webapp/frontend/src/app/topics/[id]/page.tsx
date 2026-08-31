"use client";
import { useState, useCallback, useRef, useEffect, useMemo } from "react";
import useSWR from "swr";
import Link from "next/link";
import { apiFetch } from "@/lib/api";
import { formatNL, nlInputToUtcIso } from "@/lib/timezone";
import type { TopicDetail } from "@/lib/types";
import { StatusBadge } from "@/components/StatusBadge";
import {
  ExternalLink, Play, RotateCcw, FileText, Music, Video,
  Image as ImageIcon, Subtitles, Instagram, Upload, Copy, ChevronDown, ChevronUp, RefreshCw,
} from "lucide-react";
import type { SceneImageInfo } from "@/lib/types";

const fetcher = (url: string) => apiFetch<TopicDetail>(url);

// ── Scene Image Card ────────────────────────────────────────────────────────
function SceneImageCard({ scene, topicId, onUploaded, cacheBust }: { scene: SceneImageInfo; topicId: string; onUploaded: () => void; cacheBust: number }) {
  const [showPrompt16, setShowPrompt16] = useState(false);
  const [showPrompt9, setShowPrompt9] = useState(false);
  const [uploading16, setUploading16] = useState(false);
  const [uploading9, setUploading9] = useState(false);
  const [bust16, setBust16] = useState(cacheBust);
  const [bust9, setBust9] = useState(cacheBust);
  const ref16 = useRef<HTMLInputElement>(null);
  const ref9 = useRef<HTMLInputElement>(null);

  const upload = async (file: File, format: "16x9" | "9x16") => {
    const setter = format === "16x9" ? setUploading16 : setUploading9;
    setter(true);
    try {
      const fd = new FormData();
      fd.append("topic_id", topicId);
      fd.append("scene_num", String(scene.scene));
      fd.append("format", format);
      fd.append("file", file);
      await fetch("/api/media/upload-scene-image", { method: "POST", body: fd });
      if (format === "16x9") setBust16(Date.now()); else setBust9(Date.now());
      onUploaded();
    } finally {
      setter(false);
    }
  };

  const ImagePanel = ({ path, format, cacheBust, uploading, inputRef, prompt, showPrompt, onTogglePrompt }: {
    path: string | null; format: "16x9" | "9x16"; cacheBust: number; uploading: boolean;
    inputRef: React.RefObject<HTMLInputElement>; prompt: string;
    showPrompt: boolean; onTogglePrompt: () => void;
  }) => (
    <div className="flex flex-col gap-1.5">
      <span className="text-xs text-gray-500 font-medium">{format === "16x9" ? "16:9 Main" : "9:16 Shorts"}</span>
      <div
        className={`relative rounded-lg border-2 overflow-hidden cursor-pointer group ${path ? "border-gray-700" : "border-dashed border-gray-600 hover:border-sky-500"} ${format === "9x16" ? "aspect-[9/16] max-h-64" : "aspect-video"}`}
        onClick={() => inputRef.current?.click()}
        title="Click to upload image"
      >
        {path ? (
          <img src={`/api/media/image?path=${encodeURIComponent(path)}&v=${cacheBust}`} alt={`Scene ${scene.scene} ${format}`} className={`w-full h-full ${format === "9x16" ? "object-contain" : "object-cover"}`} />
        ) : (
          <div className="w-full h-full flex items-center justify-center bg-gray-800/50">
            <Upload size={20} className="text-gray-500 group-hover:text-sky-400" />
          </div>
        )}
        {uploading && <div className="absolute inset-0 bg-black/60 flex items-center justify-center"><span className="text-xs text-white">Uploading…</span></div>}
        {path && <div className="absolute inset-0 bg-black/0 group-hover:bg-black/40 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity"><Upload size={16} className="text-white" /></div>}
      </div>
      <input ref={inputRef} type="file" accept="image/png,image/jpeg,image/webp" className="hidden"
        onChange={(e) => { const f = e.target.files?.[0]; if (f) upload(f, format); e.target.value = ""; }} />
      <button onClick={onTogglePrompt} className="flex items-center gap-1 text-xs text-gray-400 hover:text-gray-200 transition-colors mt-0.5">
        {showPrompt ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
        {showPrompt ? "Hide prompt" : "Show prompt"}
      </button>
      {showPrompt && (
        <div className="relative">
          <pre className="text-xs text-gray-400 bg-gray-900/60 rounded-lg p-3 whitespace-pre-wrap break-words max-h-40 overflow-y-auto border border-gray-700/40">{prompt}</pre>
          <button onClick={() => navigator.clipboard.writeText(prompt)} className="absolute top-2 right-2 p-1 rounded bg-gray-700 hover:bg-gray-600 text-gray-300 hover:text-white" title="Copy prompt"><Copy size={12} /></button>
        </div>
      )}
    </div>
  );

  return (
    <div className="bg-gray-800/40 border border-gray-700/50 rounded-xl p-4 space-y-3">
      <div className="flex items-start justify-between gap-2">
        <div>
          <span className="text-xs font-semibold text-sky-400 uppercase">Scene {scene.scene}</span>
          <p className="text-sm text-gray-200 mt-0.5">{scene.description}</p>
          {scene.trigger && <p className="text-xs text-gray-500 mt-0.5 italic">"{scene.trigger}"</p>}
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <ImagePanel path={scene.image_16x9} format="16x9" cacheBust={bust16} uploading={uploading16} inputRef={ref16}
          prompt={scene.prompt} showPrompt={showPrompt16} onTogglePrompt={() => setShowPrompt16(v => !v)} />
        <ImagePanel path={scene.image_9x16} format="9x16" cacheBust={bust9} uploading={uploading9} inputRef={ref9}
          prompt={scene.prompt_9x16} showPrompt={showPrompt9} onTogglePrompt={() => setShowPrompt9(v => !v)} />
      </div>
    </div>
  );
}
// ────────────────────────────────────────────────────────────────────────────

const STAGES = [
  { n: 1,  d: 1,  label: "Script (AI regenerate)" },
  { n: 18, d: 2,  label: "Generate Quiz" },
  { n: 2,  d: 3,  label: "Expression Tags" },
  { n: 3,  d: 4,  label: "16:9 Image" },
  { n: 10, d: 5,  label: "9:16 Image" },
  { n: 4,  d: 6,  label: "Audio" },
  { n: 5,  d: 7,  label: "Subtitles" },
  { n: 6,  d: 8,  label: "Audio QA" },
  { n: 7,  d: 9,  label: "Subtitle QA" },
  { n: 8,  d: 10, label: "Render Video" },
  { n: 11, d: 11, label: "Render Shorts" },
  { n: 9,  d: 12, label: "Upload YouTube" },
  { n: 12, d: 13, label: "Upload Shorts (YT)" },
  { n: 13, d: 14, label: "Upload Instagram" },
  { n: 14, d: 15, label: "Upload TikTok" },
  { n: 15, d: 16, label: "Upload Facebook" },
  { n: 16, d: 17, label: "Upload Captions" },
];

type TabKey = "overview" | "script" | "media" | "pipeline" | "youtube" | "reels" | "instagram" | "tiktok" | "facebook";

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
    if (!topic || selectedStages.size === 0) return;
    setLaunching(true);
    try {
      let job: { job_id: string };
      if (!topic.media.artifact) {
        // No artifact yet — bootstrap with script stage via full pipeline run
        job = await apiFetch<{ job_id: string }>("/api/pipeline/run", {
          method: "POST",
          body: JSON.stringify({ topic_id: topic.id, script_only: true }),
        });
      } else {
        // Numeric sort — JS default .sort() is lexicographic ("10" < "4")
        const sorted = [...selectedStages].sort((a, b) => a - b);

        // Stages 7 (Render Video) and 10 (Render Shorts) are independent of
        // each other — both need subtitles (4) but not each other.
        // When both renders are selected: run subtitles first (if selected),
        // wait for completion, then fire the two renders simultaneously.
        const has7 = sorted.includes(7);
        const has10 = sorted.includes(10);
        if (has7 && has10) {
          const prereqs = sorted.filter((n) => n !== 7 && n !== 10);

          if (prereqs.length > 0) {
            // Step 1: run prereqs (e.g. subtitles) to completion
            const prereqJob = await apiFetch<{ job_id: string }>("/api/pipeline/run-stages", {
              method: "POST",
              body: JSON.stringify({
                topic_id: topic.id,
                stages: prereqs,
              }),
            });

            // Poll until the prereq job finishes
            await (async () => {
              while (true) {
                await new Promise((r) => setTimeout(r, 3000));
                const info = await apiFetch<{ status: string }>(`/api/pipeline/jobs/${prereqJob.job_id}`);
                if (info.status === "done" || info.status === "error") break;
              }
            })();
          }

          // Step 2: launch render video + render shorts simultaneously
          const [jobA, jobB] = await Promise.all([
            apiFetch<{ job_id: string }>("/api/pipeline/run-stages", {
              method: "POST",
              body: JSON.stringify({
                topic_id: topic.id,
                stages: [...prereqs, 7],
              }),
            }),
            apiFetch<{ job_id: string }>("/api/pipeline/run-stages", {
              method: "POST",
              body: JSON.stringify({
                topic_id: topic.id,
                stages: [10],
              }),
            }),
          ]);
          // Navigate to first job; second job runs concurrently in the background
          window.location.href = `/run?job=${jobA.job_id}&parallel=${jobB.job_id}`;
          return;
        }

        job = await apiFetch<{ job_id: string }>("/api/pipeline/run-stages", {
          method: "POST",
          body: JSON.stringify({
            topic_id: topic.id,
            stages: sorted,
          }),
        });
      }
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

  const setStatus = useCallback(async (status: string) => {
    if (!topic) return;
    await apiFetch(`/api/topics/${topic.id}/status?status=${status}`, { method: "PATCH" });
    mutate();
  }, [topic, mutate]);

  if (!topic) return <div className="text-gray-400 text-sm">Loading…</div>;

  const ps = topic.media.platform_status;
  const platformDot = (s: string) =>
    s === "done" ? "🟢" : s === "partial" ? "🟡" : "";

  const TABS: { key: TabKey; label: string }[] = [
    { key: "overview", label: "Overview" },
    { key: "script", label: "Script" },
    { key: "media", label: "Media" },
    { key: "pipeline", label: "Pipeline" },
    { key: "youtube", label: `YouTube${platformDot(ps.youtube_shorts) ? " " + platformDot(ps.youtube_shorts) : ""}` },
    { key: "reels", label: "Reels Schedule" },
    { key: "instagram", label: `Instagram ${platformDot(ps.instagram) || "⚪"}` },
    { key: "tiktok", label: `TikTok ${platformDot(ps.tiktok) || "⚪"}` },
    { key: "facebook", label: `Facebook ${platformDot(ps.facebook) || "⚪"}` },
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
          <select
            value={topic.status}
            onChange={(e) => setStatus(e.target.value)}
            className="text-sm bg-gray-800 border border-gray-700 text-gray-300 px-2 py-1.5 rounded-lg cursor-pointer hover:border-gray-500"
            title="Manually set topic status"
          >
            <option value="pending">pending</option>
            <option value="generated">generated</option>
            <option value="ready_to_publish">ready_to_publish</option>
            <option value="done">done</option>
          </select>
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
      {tab === "script" && <ScriptTab topic={topic} mutate={mutate} />}
      {tab === "media" && <MediaTab topic={topic} mutate={mutate} />}
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
      {tab === "reels" && <ReelsScheduleTab topic={topic} mutate={mutate} />}
      {tab === "instagram" && <InstagramTab topic={topic} mutate={mutate} />}
      {tab === "tiktok" && <TikTokTab topic={topic} mutate={mutate} />}
      {tab === "facebook" && <FacebookTab topic={topic} mutate={mutate} />}
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

function ScriptTab({ topic, mutate }: { topic: TopicDetail; mutate: () => void }) {
  const script = topic.script as any;
  if (!script) return <p className="text-gray-500">No script generated yet.</p>;
  const ttsDialogue = Array.isArray(topic.tts_dialogue) ? topic.tts_dialogue : [];
  const hasExpressiveTags = ttsDialogue.some((line: any) => {
    const speaker = line.speaker || Object.keys(line)[0];
    const text = line.line || line[speaker] || "";
    return /\[[^\]]+\]/.test(String(text));
  });

  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const [saving, setSaving] = useState(false);
  const [saveMsg, setSaveMsg] = useState("");
  const [subTab, setSubTab] = useState<"dialogue" | "vocabulary" | "grammar" | "quiz">("dialogue");

  useEffect(() => {
    if (!editing) {
      setDraft(JSON.stringify(script, null, 2));
    }
  }, [script, editing]);

  const startEditing = () => {
    setDraft(JSON.stringify(script, null, 2));
    setSaveMsg("");
    setEditing(true);
  };

  const cancelEditing = () => {
    setDraft(JSON.stringify(script, null, 2));
    setSaveMsg("");
    setEditing(false);
  };

  const saveScript = async () => {
    setSaving(true);
    setSaveMsg("");
    try {
      const parsed = JSON.parse(draft);
      await apiFetch(`/api/topics/${topic.id}/script`, {
        method: "PUT",
        body: JSON.stringify({ script: parsed }),
      });
      await mutate();
      setEditing(false);
      setSaveMsg("Saved");
    } catch (err) {
      setSaveMsg(String(err));
    } finally {
      setSaving(false);
    }
  };

  const dialogue: Array<{ Speaker1?: string; Speaker2?: string } | { speaker: string; line: string }> =
    script.dialogue || script.script || [];

  return (
    <div className="space-y-6">
      <section className="bg-gray-900 border border-gray-800 rounded-xl p-4 space-y-3">
        <div className="flex items-center justify-between gap-3">
          <h3 className="text-sm font-semibold text-gray-300 uppercase tracking-wide">Script JSON</h3>
          {!editing ? (
            <button
              onClick={startEditing}
              className="text-xs border border-sky-700 text-sky-300 hover:text-white hover:bg-sky-900/40 px-3 py-1.5 rounded-lg"
            >
              Edit Script
            </button>
          ) : (
            <div className="flex items-center gap-2">
              <button
                onClick={cancelEditing}
                disabled={saving}
                className="text-xs border border-gray-700 text-gray-300 hover:text-white px-3 py-1.5 rounded-lg disabled:opacity-50"
              >
                Cancel
              </button>
              <button
                onClick={saveScript}
                disabled={saving}
                className="text-xs bg-sky-600 hover:bg-sky-500 text-white px-3 py-1.5 rounded-lg disabled:opacity-50"
              >
                {saving ? "Saving..." : "Save"}
              </button>
            </div>
          )}
        </div>
        {editing ? (
          <textarea
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            className="w-full min-h-[22rem] bg-gray-950 border border-gray-700 rounded-lg p-3 text-xs font-mono text-gray-200 focus:outline-none focus:border-sky-600"
            spellCheck={false}
          />
        ) : (
          <p className="text-xs text-gray-500">Click Edit Script to modify and save the generated script.</p>
        )}
        {saveMsg && <p className="text-xs text-gray-300">{saveMsg}</p>}
      </section>

      {/* Sub-navigation */}
      <div className="flex gap-2 border-b border-gray-800">
        {([
          ["dialogue", "Dialogue"],
          ["vocabulary", `Vocabulary${script.vocabulary?.length ? ` (${script.vocabulary.length})` : ""}`],
          ["grammar", `Grammar${script.grammar_notes?.length ? ` (${script.grammar_notes.length})` : ""}`],
          ["quiz", `Quiz${script.quiz?.length ? ` (${script.quiz.length})` : ""}`],
        ] as const).map(([key, label]) => (
          <button
            key={key}
            onClick={() => setSubTab(key)}
            className={`px-3 py-2 text-sm border-b-2 -mb-px ${
              subTab === key
                ? "border-sky-500 text-white"
                : "border-transparent text-gray-400 hover:text-gray-200"
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {/* Dialogue */}
      {subTab === "dialogue" && (
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
      )}

      {/* Expressive dialogue */}
      {subTab === "dialogue" && (
      <section>
        <h3 className="text-sm font-semibold text-gray-400 uppercase tracking-wide mb-3">Expressive Dialogue (Stage 2)</h3>
        {ttsDialogue.length > 0 && !hasExpressiveTags && (
          <p className="text-yellow-400 text-xs mb-2">Stage 2 output exists but contains no expressive tags yet.</p>
        )}
        {ttsDialogue.length > 0 ? (
          <div className="space-y-2">
            {ttsDialogue.map((line: any, i: number) => {
              const speaker = line.speaker || Object.keys(line)[0];
              const text = line.line || line[speaker];
              const isLeft = speaker === "Speaker1";
              return (
                <div key={`tts-${i}`} className={`flex gap-3 ${isLeft ? "" : "flex-row-reverse"}`}>
                  <div className={`text-xs px-1.5 py-0.5 rounded self-start mt-1 ${isLeft ? "bg-emerald-800 text-emerald-200" : "bg-teal-800 text-teal-200"}`}>
                    {speaker}
                  </div>
                  <div className={`bg-gray-800 rounded-xl px-4 py-2.5 text-sm max-w-lg ${isLeft ? "rounded-tl-sm" : "rounded-tr-sm"}`}>
                    {text}
                  </div>
                </div>
              );
            })}
          </div>
        ) : (
          <p className="text-gray-500 text-sm">No expressive tags yet. Run stage 2 (Expression Tags) to generate tagged TTS dialogue.</p>
        )}
      </section>
      )}

      {/* Vocabulary */}
      {subTab === "vocabulary" && (
        script.vocabulary?.length > 0 ? (
        <section>
          <h3 className="text-sm font-semibold text-gray-400 uppercase tracking-wide mb-3">Vocabulary ({script.vocabulary.length} words)</h3>
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
            {script.vocabulary.map((v: any, i: number) => (
              <div key={i} className="bg-gray-800/50 border border-gray-700 rounded-lg px-3 py-2 text-sm">
                <div className="text-white font-medium">{v.nl}</div>
                <div className="text-gray-400">{v.en}</div>
              </div>
            ))}
          </div>
        </section>
        ) : <p className="text-gray-500 text-sm">No vocabulary in this script.</p>
      )}

      {/* Grammar notes */}
      {subTab === "grammar" && (
        script.grammar_notes?.length > 0 ? (
        <section>
          <h3 className="text-sm font-semibold text-gray-400 uppercase tracking-wide mb-3">Grammar Notes</h3>
          {script.grammar_notes.map((g: any, i: number) => (
            <div key={i} className="bg-gray-800/50 border border-gray-700 rounded-lg px-4 py-3 mb-2">
              <div className="font-medium text-white text-sm">{g.title}</div>
              <div className="text-gray-400 text-sm mt-1">{g.explanation}</div>
            </div>
          ))}
        </section>
        ) : <p className="text-gray-500 text-sm">No grammar notes in this script.</p>
      )}

      {/* Quiz */}
      {subTab === "quiz" && (
        script.quiz?.length > 0 ? (
        <section>
          <h3 className="text-sm font-semibold text-gray-400 uppercase tracking-wide mb-3">Quiz ({script.quiz.length} questions)</h3>
          {script.quiz.map((q: any, i: number) => (
            <div key={i} className="bg-gray-800/50 border border-gray-700 rounded-lg px-4 py-3 mb-2 text-sm">
              <div className="text-white font-medium">{i + 1}. {q.question}</div>
              {Array.isArray(q.options) && (
                <ul className="mt-1.5 space-y-0.5">
                  {q.options.map((opt: string, j: number) => (
                    <li key={j} className={opt === q.answer ? "text-green-400" : "text-gray-400"}>
                      {opt === q.answer ? "✓ " : "· "}{opt}
                    </li>
                  ))}
                </ul>
              )}
              {q.explanation && <div className="text-gray-500 mt-1.5">{q.explanation}</div>}
            </div>
          ))}
        </section>
        ) : <p className="text-gray-500 text-sm">No quiz in this script.</p>
      )}
    </div>
  );
}

function MediaTab({ topic, mutate }: { topic: TopicDetail; mutate: () => void }) {
  const m = topic.media;
  // Recomputed whenever the topic data is re-fetched so every media URL below is unique,
  // forcing the browser to always issue a fresh request instead of reusing a cached one.
  const v = useMemo(() => Date.now(), [topic]);
  return (
    <div className="space-y-6">
      {/* Audio */}
      <section>
        <h3 className="text-sm font-semibold text-gray-400 uppercase tracking-wide mb-3 flex items-center gap-2"><Music size={14} /> Audio</h3>
        {m.audio ? (
          <audio
            key={`${m.audio}-${m.audio_mtime ?? v}`}
            controls
            src={`/api/media/audio?path=${encodeURIComponent(m.audio)}&v=${m.audio_mtime ?? v}`}
            className="w-full"
          />
        ) : <p className="text-gray-500 text-sm">No audio generated yet.</p>}
      </section>

      {/* Video */}
      <section>
        <h3 className="text-sm font-semibold text-gray-400 uppercase tracking-wide mb-3 flex items-center gap-2"><Video size={14} /> Video</h3>
        {m.video ? (
          <video key={`${m.video}-${v}`} controls src={`/api/media/video?path=${encodeURIComponent(m.video)}&v=${v}`} className="w-full rounded-xl max-h-96">
            {m.subtitles.srt_en && (
              <track
                kind="subtitles"
                label="English"
                srcLang="en"
                src={`/api/media/subtitle-vtt?path=${encodeURIComponent(m.subtitles.srt_en)}&v=${v}`}
                default
              />
            )}
          </video>
        ) : <p className="text-gray-500 text-sm">No video rendered yet.</p>}
      </section>

      {/* Scene Images */}
      <section>
        <h3 className="text-sm font-semibold text-gray-400 uppercase tracking-wide mb-3 flex items-center gap-2"><ImageIcon size={14} /> Scene Images</h3>
        {m.scene_images.length > 0 ? (
          <div className="space-y-4">
            {m.scene_images.map((scene) => (
              <SceneImageCard key={scene.scene} scene={scene} topicId={topic.id} onUploaded={mutate} cacheBust={v} />
            ))}
          </div>
        ) : m.images.length > 0 ? (
          <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
            {m.images.map((img, i) => (
              <img key={`${img}-${v}`} src={`/api/media/image?path=${encodeURIComponent(img)}&v=${v}`} alt={`Scene ${i + 1}`} className="rounded-lg border border-gray-700 object-cover aspect-video" />
            ))}
          </div>
        ) : <p className="text-gray-500 text-sm">No images yet — run the Script stage to generate scene prompts.</p>}
      </section>

      {/* Subtitles */}
      <section>
        <h3 className="text-sm font-semibold text-gray-400 uppercase tracking-wide mb-3 flex items-center gap-2"><FileText size={14} /> Subtitles</h3>
        <div className="flex gap-3 flex-wrap">
          {m.subtitles.srt_en && (
            <a href={`/api/media/subtitle?path=${encodeURIComponent(m.subtitles.srt_en)}&v=${v}`} target="_blank" rel="noopener noreferrer" className="text-xs text-sky-400 hover:underline border border-sky-700/40 px-3 py-1.5 rounded-lg">
              📄 English SRT
            </a>
          )}
          {m.subtitles.srt_nl && (
            <a href={`/api/media/subtitle?path=${encodeURIComponent(m.subtitles.srt_nl)}&v=${v}`} target="_blank" rel="noopener noreferrer" className="text-xs text-sky-400 hover:underline border border-sky-700/40 px-3 py-1.5 rounded-lg">
              📄 Dutch SRT
            </a>
          )}
          {m.subtitles.ass && (
            <a href={`/api/media/subtitle?path=${encodeURIComponent(m.subtitles.ass)}&v=${v}`} target="_blank" rel="noopener noreferrer" className="text-xs text-sky-400 hover:underline border border-sky-700/40 px-3 py-1.5 rounded-lg">
              🎨 Karaoke ASS
            </a>
          )}
          {!m.subtitles.srt_en && !m.subtitles.srt_nl && !m.subtitles.ass && (
            <p className="text-gray-500 text-sm">No subtitles generated yet.</p>
          )}
        </div>
      </section>

      {/* Short Clips / Reels */}
      <section>
        <h3 className="text-sm font-semibold text-gray-400 uppercase tracking-wide mb-3 flex items-center gap-2"><Video size={14} /> Shorts / Reels</h3>
        {m.shorts.filter((s) => s.video_file).length > 0 ? (
          <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
            {m.shorts.filter((s) => s.video_file).map((s, i) => (
              <div key={i} className="bg-gray-900 border border-gray-800 rounded-lg p-2 space-y-1">
                <p className="text-xs text-gray-400">Scene {s.scene}</p>
                <video
                  key={`${s.video_file}-${v}`}
                  controls
                  src={`/api/media/video?path=${encodeURIComponent(s.video_file!)}&v=${v}`}
                  className="w-full rounded-lg border border-gray-700 aspect-[9/16] object-contain bg-black max-h-48"
                />
              </div>
            ))}
          </div>
        ) : (
          <p className="text-gray-500 text-sm">No shorts rendered yet — run stage 11 (Render Shorts).</p>
        )}
      </section>
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
  type StageStatus = "done" | "missing" | "partial" | "unknown";
  const m = topic.media;
  const hasTtsDialogue = Array.isArray(topic.tts_dialogue) && topic.tts_dialogue.length > 0;
  const stageStatus = (n: number): StageStatus => {
    if (n === 1) return m.artifact ? "done" : "missing";
    if (n === 2) return hasTtsDialogue ? "done" : "missing";
    if (n === 3) return (m.images.length > 0 || m.scene_images.some((s) => s.image_16x9)) ? "done" : "missing";
    if (n === 4) return m.audio ? "done" : "missing";
    if (n === 5) return m.subtitles.ass ? "done" : "missing";
    if (n === 8) return m.video ? "done" : "missing";
    if (n === 9) return topic.youtube_video_id ? "done" : "missing";
    if (n === 10) return m.scene_images.some((s) => s.image_9x16) ? "done" : "missing";
    if (n === 11) return m.shorts.length > 0 ? "done" : "missing";
    if (n === 12) return m.shorts.some((s: any) => s.youtube?.short_video_id) ? "done" : "missing";
    if (n === 13) return m.shorts.some((s: any) => s.reel_id || s.instagram?.reel_id) ? "done" : "missing";
    if (n === 14) return m.shorts.some((s: any) => s.tiktok?.publish_id) ? "done" : "missing";
    if (n === 15) return m.shorts.some((s: any) => s.facebook?.post_id) ? "done" : "missing";
    if (n === 16) return (topic as any).artifact_youtube_captions ? "done" : "missing";
    if (n === 18) return ((topic.script as any)?.quiz?.length ?? 0) > 0 ? "done" : "missing";
    return "unknown";
  };

  return (
    <div className="space-y-5">
      <p className="text-sm text-gray-400">Select stages to re-run, then click Run Selected Stages.</p>
      <div className="grid grid-cols-3 gap-3">
        {STAGES.map((s) => {
          const st = stageStatus(s.n);
          const locked = !m.artifact && s.n !== 1;
          return (
            <button
              key={s.n}
              onClick={() => !locked && toggleStage(s.n)}
              disabled={locked}
              className={`flex items-center gap-2 px-4 py-3 rounded-xl border text-sm transition ${
                locked
                  ? "border-gray-800 bg-gray-900/20 text-gray-600 cursor-not-allowed"
                  : selectedStages.has(s.n)
                  ? "border-sky-500 bg-sky-900/30 text-sky-200"
                  : "border-gray-700 bg-gray-800/30 text-gray-300 hover:border-gray-600"
              }`}
            >
              <span className={`w-2 h-2 rounded-full ${st === "done" ? "bg-green-500" : st === "partial" ? "bg-yellow-400" : "bg-gray-600"}`} />
              {s.d}. {s.label}
            </button>
          );
        })}
      </div>
      {!m.artifact && (
        <p className="text-yellow-400 text-sm">No artifact yet — select Stage 1 (Script) to initialise this topic.</p>
      )}
      {selectedStages.has(1) && (
        <p className="text-amber-400 text-sm">Stage 1 regenerates script from AI and overwrites manual Script tab edits.</p>
      )}
      <div>
        <button
          onClick={runStages}
          disabled={selectedStages.size === 0 || launching || (!m.artifact && !selectedStages.has(1))}
          className="bg-sky-600 hover:bg-sky-500 text-white px-4 py-2 rounded-lg text-sm font-medium disabled:opacity-40"
        >
          {launching ? "Starting…" : `Run ${selectedStages.size} stage(s)`}
        </button>
      </div>
    </div>
  );
}

function YoutubeTab({ topic }: { topic: TopicDetail }) {
  if (!topic.youtube_video_id) {
    return (
      <div className="text-gray-400 text-sm space-y-3">
        <p>This topic has not been uploaded to YouTube yet.</p>
        <p>Use the Pipeline tab to run stage 10 (Upload YouTube).</p>
      </div>
    );
  }
  const url = `https://youtube.com/watch?v=${topic.youtube_video_id}`;
  const uploadedShorts = topic.media.shorts.filter((s) => s.youtube?.short_video_id);
  return (
    <div className="space-y-6">
      {/* Main video */}
      <section>
        <h3 className="text-sm font-semibold text-gray-400 uppercase tracking-wide mb-3 flex items-center gap-2"><ExternalLink size={14} /> Full Video</h3>
        <div className="flex items-center gap-3 mb-3">
          <a href={url} target="_blank" rel="noopener noreferrer" className="flex items-center gap-2 text-red-400 hover:underline font-medium text-sm">
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
        <div className="text-sm text-gray-400 space-y-1 mt-3">
          <div>Playlist: {topic.playlist_name || "—"}</div>
          <div>Scheduled: {topic.scheduled_at || "—"}</div>
          <div>Published: {topic.published_at || "—"}</div>
        </div>
      </section>

      {/* YouTube Shorts */}
      <section>
        <h3 className="text-sm font-semibold text-gray-400 uppercase tracking-wide mb-3">YouTube Shorts</h3>
        {uploadedShorts.length > 0 ? (
          <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
            {uploadedShorts.map((s, i) => {
              const shortId = s.youtube!.short_video_id as string;
              const shortUrl = `https://youtube.com/shorts/${shortId}`;
              return (
                <div key={i} className="bg-gray-900 border border-gray-800 rounded-xl p-3 space-y-2">
                  <p className="text-xs text-gray-400">Scene {s.scene}{s.description ? ` — ${s.description}` : ""}</p>
                  <div className="aspect-[9/16] rounded-lg overflow-hidden bg-black border border-gray-700">
                    <iframe
                      src={`https://www.youtube.com/embed/${shortId}`}
                      className="w-full h-full"
                      allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
                      allowFullScreen
                    />
                  </div>
                  <a href={shortUrl} target="_blank" rel="noopener noreferrer" className="flex items-center gap-1 text-red-400 hover:underline text-xs">
                    <ExternalLink size={11} /> Watch on YouTube
                  </a>
                </div>
              );
            })}
          </div>
        ) : (
          <p className="text-gray-500 text-sm">No Shorts uploaded yet — run stage 11 (Upload Shorts YT).</p>
        )}
      </section>
    </div>
  );
}

// ── ReelsScheduleTab ────────────────────────────────────────────────────────
function ReelsScheduleTab({ topic, mutate }: { topic: TopicDetail; mutate: () => void }) {
  const shorts = topic.media.shorts;
  const [inputs, setInputs] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState<Record<string, boolean>>({});

  const schedule = async (scene: string | null, isoOrEmpty: string) => {
    const k = String(scene);
    setBusy((b) => ({ ...b, [k]: true }));
    try {
      await apiFetch(`/api/publish/reels/${topic.id}/scene/${scene}/schedule`, {
        method: "PATCH",
        body: JSON.stringify({ scheduled_at: isoOrEmpty }),
      });
      mutate();
    } catch (err) {
      alert(String(err));
    } finally {
      setBusy((b) => ({ ...b, [k]: false }));
    }
  };

  if (shorts.length === 0) {
    return (
      <div className="text-gray-400 text-sm space-y-2">
        <p>No scene shorts found. Run stage 10 (Render Shorts) first.</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <p className="text-sm text-gray-400">
        Set a publish time for each reel. When that time passes,{" "}
        <code className="text-xs bg-gray-800 px-1.5 py-0.5 rounded">publish_pending_reels.py</code> will upload
        to all enabled platforms (Instagram, TikTok, Facebook) in one pass.
      </p>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {shorts.map((s) => {
          const k = String(s.scene);
          const scheduled = s.reel_scheduled_at;
          const igDone = !!(s.reel_id || s.instagram?.reel_id);
          const ttDone = !!s.tiktok?.publish_id;
          const fbDone = !!s.facebook?.post_id;
          const allDone = igDone && ttDone && fbDone;

          return (
            <div key={k} className="bg-gray-900 border border-gray-800 rounded-xl p-4 space-y-3">
              {/* Header */}
              <div className="flex items-center justify-between">
                <span className="text-sm font-medium text-white">Scene {s.scene}</span>
                {allDone
                  ? <span className="text-xs bg-green-800/40 text-green-300 px-2 py-0.5 rounded border border-green-700/30">✓ All platforms done</span>
                  : scheduled
                  ? <span className="text-xs bg-purple-800/40 text-purple-300 px-2 py-0.5 rounded border border-purple-700/30">⏰ Scheduled</span>
                  : <span className="text-xs bg-gray-800 text-gray-500 px-2 py-0.5 rounded border border-gray-700">Unscheduled</span>
                }
              </div>

              {s.description && <p className="text-xs text-gray-400">{s.description}</p>}

              {/* Platform upload status */}
              <div className="flex gap-3 text-xs">
                <span className={igDone ? "text-green-400" : "text-gray-600"}>
                  {igDone ? "✓" : "○"} Instagram
                </span>
                <span className={ttDone ? "text-green-400" : "text-gray-600"}>
                  {ttDone ? "✓" : "○"} TikTok
                </span>
                <span className={fbDone ? "text-green-400" : "text-gray-600"}>
                  {fbDone ? "✓" : "○"} Facebook
                </span>
              </div>

              {/* Video thumbnail */}
              {s.video_file && (
                <video
                  src={`/api/media/video?path=${encodeURIComponent(s.video_file)}`}
                  className="w-full rounded-lg aspect-[9/16] object-contain bg-black max-h-48"
                />
              )}

              {/* Schedule controls */}
              {!allDone && (
                <div className="pt-2 border-t border-gray-800 space-y-2">
                  {scheduled ? (
                    <div className="space-y-1.5">
                      <div className="flex items-center gap-2 text-xs text-purple-300">
                        <span>⏰ {formatNL(scheduled)} (NL)</span>
                        <button
                          onClick={() => schedule(s.scene, "")}
                          disabled={busy[k]}
                          className="text-gray-500 hover:text-red-400 underline"
                        >
                          Clear
                        </button>
                      </div>
                      <p className="text-xs text-gray-500">
                        Will upload to all enabled platforms automatically when this time arrives.
                      </p>
                    </div>
                  ) : (
                    <div className="space-y-1">
                      <p className="text-xs text-gray-500">Schedule for all platforms (NL time):</p>
                      <div className="flex items-center gap-2">
                        <input
                          type="datetime-local"
                          value={inputs[k] || ""}
                          onChange={(e) => setInputs((p) => ({ ...p, [k]: e.target.value }))}
                          className="text-xs bg-gray-800 border border-gray-700 rounded px-2 py-1.5 text-gray-200 flex-1 min-w-0"
                        />
                        <button
                          onClick={() => {
                            if (inputs[k]) schedule(s.scene, nlInputToUtcIso(inputs[k]));
                          }}
                          disabled={!inputs[k] || busy[k]}
                          className="text-xs bg-purple-700 hover:bg-purple-600 text-white px-3 py-1.5 rounded-lg disabled:opacity-40 whitespace-nowrap"
                        >
                          {busy[k] ? "Saving…" : "Schedule"}
                        </button>
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function InstagramTab({ topic, mutate }: { topic: TopicDetail; mutate: () => void }) {
  const shorts = topic.media.shorts;
  const [busy, setBusy] = useState<Record<string, boolean>>({});
  const [scheduleInputs, setScheduleInputs] = useState<Record<string, string>>({});
  const [reelIdInputs, setReelIdInputs] = useState<Record<string, string>>({});
  const [showMarkForm, setShowMarkForm] = useState<Record<string, boolean>>({});

  const key = (s: (typeof shorts)[0]) => String(s.scene);

  const uploadNow = async (scene: string | null) => {
    setBusy((b) => ({ ...b, [String(scene)]: true }));
    try {
      await apiFetch(`/api/publish/instagram/${topic.id}/shorts/${scene}/upload`, { method: "POST" });
      mutate();
    } catch (err) { alert(String(err)); }
    finally { setBusy((b) => ({ ...b, [String(scene)]: false })); }
  };

  const markUploaded = async (scene: string | null, reelId: string, permalink: string) => {
    setBusy((b) => ({ ...b, [String(scene)]: true }));
    try {
      const params = new URLSearchParams();
      if (reelId) params.set("reel_id", reelId);
      if (permalink) params.set("permalink", permalink);
      await apiFetch(`/api/publish/instagram/${topic.id}/shorts/${scene}/mark-uploaded?${params}`, { method: "POST" });
      setShowMarkForm((p) => ({ ...p, [String(scene)]: false }));
      mutate();
    } catch (err) { alert(String(err)); }
    finally { setBusy((b) => ({ ...b, [String(scene)]: false })); }
  };

  const publishDraft = async (scene: string | null, containerId: string) => {
    if (!confirm(`Publish draft container ${containerId}?`)) return;
    setBusy((b) => ({ ...b, [String(scene)]: true }));
    try {
      const r = await apiFetch<any>(
        `/api/publish/instagram/${topic.id}/publish-draft?container_id=${containerId}`,
        { method: "POST" },
      );
      if (r.error) throw new Error(r.error.message);
      mutate();
    } catch (err) { alert(String(err)); }
    finally { setBusy((b) => ({ ...b, [String(scene)]: false })); }
  };

  const scheduleUpload = async (scene: string | null, dt: string) => {
    setBusy((b) => ({ ...b, [String(scene)]: true }));
    try {
      await apiFetch(
        `/api/publish/instagram/${topic.id}/shorts/${scene}/schedule?scheduled_at=${encodeURIComponent(dt)}`,
        { method: "POST" },
      );
      mutate();
    } catch (err) { alert(String(err)); }
    finally { setBusy((b) => ({ ...b, [String(scene)]: false })); }
  };

  const clearSchedule = (scene: string | null) => scheduleUpload(scene, "");

  if (shorts.length === 0) {
    return (
      <div className="text-gray-400 text-sm space-y-3">
        <p>No Instagram Reels / Shorts found for this topic.</p>
        <p>Run stage 9 (Render Shorts) to generate scene clips first.</p>
      </div>
    );
  }

  const ps = topic.media.platform_status.instagram;
  const uploadedCount = shorts.filter(s => !!(s.reel_id || s.instagram?.reel_id)).length;

  return (
    <div className="space-y-4">
      {/* Platform status banner */}
      <div className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm border ${
        ps === "done" ? "bg-green-900/30 border-green-700/40 text-green-300"
        : ps === "partial" ? "bg-yellow-900/30 border-yellow-700/40 text-yellow-300"
        : "bg-gray-800/50 border-gray-700/40 text-gray-400"
      }`}>
        <span>{ps === "done" ? "✓ All scenes uploaded to Instagram" : ps === "partial" ? "⚡ Partially uploaded" : "⚪ Not uploaded yet"}</span>
        <span className="text-xs opacity-60">({uploadedCount}/{shorts.length} scenes)</span>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
      {shorts.map((s) => {
        const k = key(s);
        const uploaded = !!(s.reel_id || s.instagram?.reel_id);
        const permalink = s.permalink || s.instagram?.permalink;
        const scheduledAt = s.instagram_scheduled_at;
        return (
          <div key={k} className="bg-gray-900 border border-gray-800 rounded-xl p-4 space-y-3">
            {/* Header */}
            <div className="flex items-center justify-between">
              <span className="text-sm font-medium text-white">Scene {s.scene}</span>
              <div className="flex items-center gap-1.5">
                {uploaded
                  ? <span className="text-xs bg-green-800/40 text-green-300 px-2 py-0.5 rounded border border-green-700/30">✓ Uploaded</span>
                  : scheduledAt
                  ? <span className="text-xs bg-purple-800/40 text-purple-300 px-2 py-0.5 rounded border border-purple-700/30">⏰ Scheduled</span>
                  : <span className="text-xs bg-gray-800 text-gray-500 px-2 py-0.5 rounded border border-gray-700">Pending</span>
                }
                {s.draft && !uploaded && (
                  <span className="text-xs bg-yellow-800/40 text-yellow-300 px-2 py-0.5 rounded border border-yellow-700/30">Draft</span>
                )}
              </div>
            </div>

            {s.description && <p className="text-xs text-gray-400">{s.description}</p>}

            {/* Video preview */}
            {s.video_file && (
              <video
                src={`/api/media/video?path=${encodeURIComponent(s.video_file)}`}
                controls
                className="w-full rounded-lg aspect-[9/16] object-contain bg-black max-h-56"
              />
            )}

            {/* Upload actions */}
            <div className="space-y-2">
              {uploaded ? (
                permalink ? (
                  <a href={permalink} target="_blank" rel="noopener noreferrer"
                    className="flex items-center gap-1 text-pink-400 hover:underline text-xs">
                    <Instagram size={12} /> View Reel
                  </a>
                ) : (
                  <span className="text-xs text-gray-400 flex items-center gap-1"><Instagram size={12} /> Reel ID: {s.reel_id || s.instagram?.reel_id}</span>
                )
              ) : (
                <div className="flex gap-2 flex-wrap">
                  {/* Upload Now */}
                  <button
                    onClick={() => uploadNow(s.scene)}
                    disabled={busy[k]}
                    className="text-xs bg-pink-700 hover:bg-pink-600 text-white px-3 py-1.5 rounded-lg disabled:opacity-50 flex items-center gap-1"
                  >
                    <Instagram size={11} /> {busy[k] ? "Uploading…" : "Upload Now"}
                  </button>
                  {/* Publish Draft */}
                  {s.container_id && s.draft && (
                    <button
                      onClick={() => publishDraft(s.scene, s.container_id!)}
                      disabled={busy[k]}
                      className="text-xs bg-gray-700 hover:bg-gray-600 text-white px-3 py-1.5 rounded-lg disabled:opacity-50"
                    >
                      {busy[k] ? "Publishing…" : "Publish Draft"}
                    </button>
                  )}
                  {/* Mark as Uploaded manually */}
                  <button
                    onClick={() => setShowMarkForm((p) => ({ ...p, [k]: !p[k] }))}
                    className="text-xs text-gray-400 hover:text-green-400 border border-gray-700 hover:border-green-700 px-2 py-1.5 rounded-lg"
                  >
                    ✓ Mark Uploaded
                  </button>
                </div>
              )}
              {/* Mark Uploaded form */}
              {!uploaded && showMarkForm[k] && (
                <div className="bg-gray-800/60 border border-gray-700 rounded-lg p-3 space-y-2">
                  <p className="text-xs text-gray-400">Optionally enter the Reel ID and permalink from Instagram:</p>
                  <input
                    type="text"
                    placeholder="Reel ID (optional)"
                    value={reelIdInputs[`${k}_reel`] || ""}
                    onChange={(e) => setReelIdInputs((p) => ({ ...p, [`${k}_reel`]: e.target.value }))}
                    className="w-full text-xs bg-gray-900 border border-gray-700 rounded px-2 py-1 text-gray-200"
                  />
                  <input
                    type="text"
                    placeholder="Permalink (optional)"
                    value={reelIdInputs[`${k}_url`] || ""}
                    onChange={(e) => setReelIdInputs((p) => ({ ...p, [`${k}_url`]: e.target.value }))}
                    className="w-full text-xs bg-gray-900 border border-gray-700 rounded px-2 py-1 text-gray-200"
                  />
                  <div className="flex gap-2">
                    <button
                      onClick={() => markUploaded(s.scene, reelIdInputs[`${k}_reel`] || "", reelIdInputs[`${k}_url`] || "")}
                      disabled={busy[k]}
                      className="text-xs bg-green-700 hover:bg-green-600 text-white px-3 py-1.5 rounded-lg disabled:opacity-50"
                    >
                      {busy[k] ? "Saving…" : "Confirm"}
                    </button>
                    <button
                      onClick={() => setShowMarkForm((p) => ({ ...p, [k]: false }))}
                      className="text-xs text-gray-500 hover:text-gray-300"
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              )}

              {/* Scheduler */}
              {!uploaded && (
                <div className="pt-1 border-t border-gray-800 space-y-1.5">
                  {scheduledAt ? (
                    <div className="flex items-center gap-2 text-xs text-purple-300">
                      <span>⏰ {formatNL(scheduledAt)} (NL)</span>
                      <button
                        onClick={() => clearSchedule(s.scene)}
                        className="text-gray-500 hover:text-red-400 underline"
                      >
                        Clear
                      </button>
                    </div>
                  ) : (
                    <div className="space-y-1">
                      <p className="text-xs text-gray-500">NL time (Europe/Amsterdam)</p>
                      <div className="flex items-center gap-2">
                        <input
                          type="datetime-local"
                          value={scheduleInputs[k] || ""}
                          onChange={(e) => setScheduleInputs((p) => ({ ...p, [k]: e.target.value }))}
                          className="text-xs bg-gray-800 border border-gray-700 rounded px-2 py-1 text-gray-200 flex-1 min-w-0"
                        />
                        <button
                          onClick={() => {
                            if (scheduleInputs[k]) {
                              scheduleUpload(s.scene, nlInputToUtcIso(scheduleInputs[k]));
                            }
                          }}
                          disabled={!scheduleInputs[k] || busy[k]}
                          className="text-xs bg-purple-700 hover:bg-purple-600 text-white px-2 py-1.5 rounded-lg disabled:opacity-40 whitespace-nowrap"
                        >
                          Schedule
                        </button>
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
        );
      })}
      </div>
    </div>
  );
}

function TikTokTab({ topic, mutate }: { topic: TopicDetail; mutate: () => void }) {
  const shorts = topic.media.shorts;
  const ps = topic.media.platform_status.tiktok;
  const [busy, setBusy] = useState<Record<string, boolean>>({});
  const [scheduleInputs, setScheduleInputs] = useState<Record<string, string>>({});
  const [showMarkForm, setShowMarkForm] = useState<Record<string, boolean>>({});
  const [markInputs, setMarkInputs] = useState<Record<string, string>>({});

  const uploadNow = async (scene: string | null) => {
    setBusy((b) => ({ ...b, [String(scene)]: true }));
    try {
      await apiFetch(`/api/publish/tiktok/${topic.id}/shorts/${scene}/upload`, { method: "POST" });
      mutate();
    } catch (err) { alert(String(err)); }
    finally { setBusy((b) => ({ ...b, [String(scene)]: false })); }
  };

  const scheduleUpload = async (scene: string | null, dt: string) => {
    setBusy((b) => ({ ...b, [String(scene)]: true }));
    try {
      await apiFetch(
        `/api/publish/tiktok/${topic.id}/shorts/${scene}/schedule?scheduled_at=${encodeURIComponent(dt)}`,
        { method: "POST" },
      );
      mutate();
    } catch (err) { alert(String(err)); }
    finally { setBusy((b) => ({ ...b, [String(scene)]: false })); }
  };

  const markUploaded = async (scene: string | null, publishId: string) => {
    setBusy((b) => ({ ...b, [String(scene)]: true }));
    try {
      const params = new URLSearchParams();
      if (publishId) params.set("publish_id", publishId);
      await apiFetch(`/api/publish/tiktok/${topic.id}/shorts/${scene}/mark-uploaded?${params}`, { method: "POST" });
      setShowMarkForm((p) => ({ ...p, [String(scene)]: false }));
      mutate();
    } catch (err) { alert(String(err)); }
    finally { setBusy((b) => ({ ...b, [String(scene)]: false })); }
  };

  if (shorts.length === 0) {
    return (
      <div className="text-gray-400 text-sm space-y-3">
        <p>No shorts rendered yet. Run stage 9 (Render Shorts) first.</p>
      </div>
    );
  }

  const uploadedCount = shorts.filter(s => s.tiktok?.publish_id).length;

  return (
    <div className="space-y-4">
      {/* Status banner */}
      <div className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm border ${
        ps === "done" ? "bg-green-900/30 border-green-700/40 text-green-300"
        : ps === "partial" ? "bg-yellow-900/30 border-yellow-700/40 text-yellow-300"
        : "bg-gray-800/50 border-gray-700/40 text-gray-400"
      }`}>
        <span>{ps === "done" ? "✓ All scenes uploaded to TikTok" : ps === "partial" ? "⚡ Partially uploaded" : "⚪ Not uploaded yet"}</span>
        <span className="text-xs opacity-60">({uploadedCount}/{shorts.length} scenes)</span>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
        {shorts.map((s) => {
          const k = String(s.scene);
          const isUploaded = !!s.tiktok?.publish_id;
          const scheduledAt = s.tiktok_scheduled_at;
          return (
            <div key={k} className="bg-gray-900 border border-gray-800 rounded-xl p-4 space-y-3">
              <div className="flex items-center justify-between">
                <p className="text-sm font-medium text-white">Scene {s.scene}</p>
                {isUploaded
                  ? <span className="text-xs bg-green-800/40 text-green-300 px-2 py-0.5 rounded border border-green-700/30">✓ Uploaded</span>
                  : scheduledAt
                  ? <span className="text-xs bg-purple-800/40 text-purple-300 px-2 py-0.5 rounded border border-purple-700/30">⏰ Scheduled</span>
                  : <span className="text-xs bg-gray-800 text-gray-500 px-2 py-0.5 rounded border border-gray-700">Pending</span>
                }
              </div>
              {s.description && <p className="text-xs text-gray-400">{s.description}</p>}
              {s.video_file && (
                <video src={`/api/media/video?path=${encodeURIComponent(s.video_file)}`} controls
                  className="w-full rounded-lg aspect-[9/16] object-contain bg-black max-h-56" />
              )}

              {isUploaded ? (
                <p className="text-xs text-gray-500 font-mono">Publish ID: {s.tiktok?.publish_id}</p>
              ) : (
                <div className="space-y-2">
                  <div className="flex gap-2 flex-wrap">
                    <button onClick={() => uploadNow(s.scene)} disabled={busy[k]}
                      className="text-xs bg-cyan-700 hover:bg-cyan-600 text-white px-3 py-1.5 rounded-lg disabled:opacity-50">
                      {busy[k] ? "Uploading…" : "▶ Upload Now"}
                    </button>
                    <button onClick={() => setShowMarkForm((p) => ({ ...p, [k]: !p[k] }))}
                      className="text-xs text-gray-400 hover:text-green-400 border border-gray-700 hover:border-green-700 px-2 py-1.5 rounded-lg">
                      ✓ Mark Uploaded
                    </button>
                  </div>
                  {showMarkForm[k] && (
                    <div className="bg-gray-800/60 border border-gray-700 rounded-lg p-3 space-y-2">
                      <input type="text" placeholder="Publish ID (optional)"
                        value={markInputs[k] || ""}
                        onChange={(e) => setMarkInputs((p) => ({ ...p, [k]: e.target.value }))}
                        className="w-full text-xs bg-gray-900 border border-gray-700 rounded px-2 py-1 text-gray-200" />
                      <div className="flex gap-2">
                        <button onClick={() => markUploaded(s.scene, markInputs[k] || "")} disabled={busy[k]}
                          className="text-xs bg-green-700 hover:bg-green-600 text-white px-3 py-1.5 rounded-lg disabled:opacity-50">
                          {busy[k] ? "Saving…" : "Confirm"}
                        </button>
                        <button onClick={() => setShowMarkForm((p) => ({ ...p, [k]: false }))}
                          className="text-xs text-gray-500 hover:text-gray-300">Cancel</button>
                      </div>
                    </div>
                  )}
                  {/* Scheduler */}
                  <div className="pt-1 border-t border-gray-800 space-y-1.5">
                    {scheduledAt ? (
                      <div className="flex items-center gap-2 text-xs text-purple-300">
                        <span>⏰ {formatNL(scheduledAt)} (NL)</span>
                        <button onClick={() => scheduleUpload(s.scene, "")}
                          className="text-gray-500 hover:text-red-400 underline">Clear</button>
                      </div>
                    ) : (
                      <div className="space-y-1">
                        <p className="text-xs text-gray-500">NL time (Europe/Amsterdam)</p>
                        <div className="flex items-center gap-2">
                          <input type="datetime-local" value={scheduleInputs[k] || ""}
                            onChange={(e) => setScheduleInputs((p) => ({ ...p, [k]: e.target.value }))}
                            className="text-xs bg-gray-800 border border-gray-700 rounded px-2 py-1 text-gray-200 flex-1 min-w-0" />
                          <button
                            onClick={() => { if (scheduleInputs[k]) scheduleUpload(s.scene, nlInputToUtcIso(scheduleInputs[k])); }}
                            disabled={!scheduleInputs[k] || busy[k]}
                            className="text-xs bg-purple-700 hover:bg-purple-600 text-white px-2 py-1.5 rounded-lg disabled:opacity-40 whitespace-nowrap">
                            Schedule
                          </button>
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function FacebookTab({ topic, mutate }: { topic: TopicDetail; mutate: () => void }) {
  const shorts = topic.media.shorts;
  const ps = topic.media.platform_status.facebook;
  const [busy, setBusy] = useState<Record<string, boolean>>({});
  const [scheduleInputs, setScheduleInputs] = useState<Record<string, string>>({});
  const [showMarkForm, setShowMarkForm] = useState<Record<string, boolean>>({});
  const [markInputs, setMarkInputs] = useState<Record<string, string>>({});

  const uploadNow = async (scene: string | null) => {
    setBusy((b) => ({ ...b, [String(scene)]: true }));
    try {
      await apiFetch(`/api/publish/facebook/${topic.id}/shorts/${scene}/upload`, { method: "POST" });
      mutate();
    } catch (err) { alert(String(err)); }
    finally { setBusy((b) => ({ ...b, [String(scene)]: false })); }
  };

  const scheduleUpload = async (scene: string | null, dt: string) => {
    setBusy((b) => ({ ...b, [String(scene)]: true }));
    try {
      await apiFetch(
        `/api/publish/facebook/${topic.id}/shorts/${scene}/schedule?scheduled_at=${encodeURIComponent(dt)}`,
        { method: "POST" },
      );
      mutate();
    } catch (err) { alert(String(err)); }
    finally { setBusy((b) => ({ ...b, [String(scene)]: false })); }
  };

  const markUploaded = async (scene: string | null, postId: string) => {
    setBusy((b) => ({ ...b, [String(scene)]: true }));
    try {
      const params = new URLSearchParams();
      if (postId) params.set("post_id", postId);
      await apiFetch(`/api/publish/facebook/${topic.id}/shorts/${scene}/mark-uploaded?${params}`, { method: "POST" });
      setShowMarkForm((p) => ({ ...p, [String(scene)]: false }));
      mutate();
    } catch (err) { alert(String(err)); }
    finally { setBusy((b) => ({ ...b, [String(scene)]: false })); }
  };

  if (shorts.length === 0) {
    return (
      <div className="text-gray-400 text-sm space-y-3">
        <p>No shorts rendered yet. Run stage 9 (Render Shorts) first.</p>
      </div>
    );
  }

  const uploadedCount = shorts.filter(s => s.facebook?.post_id).length;

  return (
    <div className="space-y-4">
      {/* Status banner */}
      <div className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm border ${
        ps === "done" ? "bg-green-900/30 border-green-700/40 text-green-300"
        : ps === "partial" ? "bg-yellow-900/30 border-yellow-700/40 text-yellow-300"
        : "bg-gray-800/50 border-gray-700/40 text-gray-400"
      }`}>
        <span>{ps === "done" ? "✓ All scenes uploaded to Facebook" : ps === "partial" ? "⚡ Partially uploaded" : "⚪ Not uploaded yet"}</span>
        <span className="text-xs opacity-60">({uploadedCount}/{shorts.length} scenes)</span>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
        {shorts.map((s) => {
          const k = String(s.scene);
          const isUploaded = !!s.facebook?.post_id;
          const scheduledAt = s.facebook_scheduled_at;
          return (
            <div key={k} className="bg-gray-900 border border-gray-800 rounded-xl p-4 space-y-3">
              <div className="flex items-center justify-between">
                <p className="text-sm font-medium text-white">Scene {s.scene}</p>
                {isUploaded
                  ? <span className="text-xs bg-green-800/40 text-green-300 px-2 py-0.5 rounded border border-green-700/30">✓ Uploaded</span>
                  : scheduledAt
                  ? <span className="text-xs bg-purple-800/40 text-purple-300 px-2 py-0.5 rounded border border-purple-700/30">⏰ Scheduled</span>
                  : <span className="text-xs bg-gray-800 text-gray-500 px-2 py-0.5 rounded border border-gray-700">Pending</span>
                }
              </div>
              {s.description && <p className="text-xs text-gray-400">{s.description}</p>}
              {s.video_file && (
                <video src={`/api/media/video?path=${encodeURIComponent(s.video_file)}`} controls
                  className="w-full rounded-lg aspect-[9/16] object-contain bg-black max-h-56" />
              )}

              {isUploaded ? (
                <p className="text-xs text-gray-500 font-mono">Post ID: {s.facebook?.post_id}</p>
              ) : (
                <div className="space-y-2">
                  <div className="flex gap-2 flex-wrap">
                    <button onClick={() => uploadNow(s.scene)} disabled={busy[k]}
                      className="text-xs bg-blue-700 hover:bg-blue-600 text-white px-3 py-1.5 rounded-lg disabled:opacity-50">
                      {busy[k] ? "Uploading…" : "📘 Upload Now"}
                    </button>
                    <button onClick={() => setShowMarkForm((p) => ({ ...p, [k]: !p[k] }))}
                      className="text-xs text-gray-400 hover:text-green-400 border border-gray-700 hover:border-green-700 px-2 py-1.5 rounded-lg">
                      ✓ Mark Uploaded
                    </button>
                  </div>
                  {showMarkForm[k] && (
                    <div className="bg-gray-800/60 border border-gray-700 rounded-lg p-3 space-y-2">
                      <input type="text" placeholder="Post ID (optional)"
                        value={markInputs[k] || ""}
                        onChange={(e) => setMarkInputs((p) => ({ ...p, [k]: e.target.value }))}
                        className="w-full text-xs bg-gray-900 border border-gray-700 rounded px-2 py-1 text-gray-200" />
                      <div className="flex gap-2">
                        <button onClick={() => markUploaded(s.scene, markInputs[k] || "")} disabled={busy[k]}
                          className="text-xs bg-green-700 hover:bg-green-600 text-white px-3 py-1.5 rounded-lg disabled:opacity-50">
                          {busy[k] ? "Saving…" : "Confirm"}
                        </button>
                        <button onClick={() => setShowMarkForm((p) => ({ ...p, [k]: false }))}
                          className="text-xs text-gray-500 hover:text-gray-300">Cancel</button>
                      </div>
                    </div>
                  )}
                  {/* Scheduler */}
                  <div className="pt-1 border-t border-gray-800 space-y-1.5">
                    {scheduledAt ? (
                      <div className="flex items-center gap-2 text-xs text-purple-300">
                        <span>⏰ {formatNL(scheduledAt)} (NL)</span>
                        <button onClick={() => scheduleUpload(s.scene, "")}
                          className="text-gray-500 hover:text-red-400 underline">Clear</button>
                      </div>
                    ) : (
                      <div className="space-y-1">
                        <p className="text-xs text-gray-500">NL time (Europe/Amsterdam)</p>
                        <div className="flex items-center gap-2">
                          <input type="datetime-local" value={scheduleInputs[k] || ""}
                            onChange={(e) => setScheduleInputs((p) => ({ ...p, [k]: e.target.value }))}
                            className="text-xs bg-gray-800 border border-gray-700 rounded px-2 py-1 text-gray-200 flex-1 min-w-0" />
                          <button
                            onClick={() => { if (scheduleInputs[k]) scheduleUpload(s.scene, nlInputToUtcIso(scheduleInputs[k])); }}
                            disabled={!scheduleInputs[k] || busy[k]}
                            className="text-xs bg-purple-700 hover:bg-purple-600 text-white px-2 py-1.5 rounded-lg disabled:opacity-40 whitespace-nowrap">
                            Schedule
                          </button>
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}