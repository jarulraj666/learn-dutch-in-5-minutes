"use client";
import { useState, useEffect, useRef, useCallback } from "react";
import useSWR from "swr";
import { useParams } from "next/navigation";
import { apiFetch, API_URL } from "@/lib/api";
import { StatusBadge } from "@/components/StatusBadge";

type Passage = {
  id: string;
  order_index: number;
  part_number: number | null;
  passage_type: string;
  title: string;
  content_nl: string;
  content_en?: string | null;
  scene_description?: string;
  presenter_gender?: "female" | "male" | null;
  media_urls: { type: string; url: string }[];
  image_prompt?: string[] | null;
  render_manifest_path?: string | null;
};

type Question = {
  id: string;
  passage_id: string | null;
  part_number: number | null;
  order_index: number;
  question_text: string;
  question_type: string;
  options?: string[] | null;
  answer?: string | null;
  explanation: string;
  category?: string | null;
  max_score: number;
  grading_rubric?: { criterion: string; max_points: number }[] | null;
  model_answer?: string | null;
  year_asked?: number | null;
  option_image_prompts?: string[] | null;
  option_media_urls?: (string | null)[] | null;
  audio_script?: string | null;
  question_audio_url?: string | null;
};

type MockExamArtifact = {
  id: string;
  section: string;
  exam_number: number;
  level: string;
  title: string;
  instructions: string;
  time_limit_minutes: number;
  total_questions: number;
  parts_count: number;
  pass_threshold: number | null;
  max_score: number | null;
  passages: Passage[];
  questions: Question[];
};

type MockExamJob = {
  id: string;
  section: string;
  exam_number: number;
  level: string;
  status: string;
  exported_at: string | null;
  artifact: MockExamArtifact | null;
};

const fetcher = (url: string) => apiFetch<MockExamJob>(url);

const TABS = ["Overview", "Content", "Media", "Pipeline"] as const;

function genericTtsScript(script: string, addPictureReminder = false): string {
  const completeScript = addPictureReminder && !script.endsWith("Gebruik het plaatje.")
    ? `${script} Gebruik het plaatje.`
    : script;
  return completeScript;
}

export default function MockExamDetailPage() {
  const params = useParams();
  const examId = params.id as string;
  const [tab, setTab] = useState<(typeof TABS)[number]>("Overview");

  const { data: job, mutate } = useSWR(`/api/mock-exams/${examId}`, fetcher, {
    refreshInterval: 5000,
  });

  const artifact = job?.artifact;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold">{examId}</h1>
        {job && <StatusBadge status={job.status} />}
      </div>

      <div className="flex gap-1 border-b border-gray-800">
        {TABS.map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`px-3 py-2 text-sm ${
              tab === t ? "border-b-2 border-sky-500 text-white" : "text-gray-400 hover:text-white"
            }`}
          >
            {t}
          </button>
        ))}
      </div>

      {!artifact && (
        <p className="text-gray-500 text-sm">No content generated yet — use the Pipeline tab.</p>
      )}

      {artifact && tab === "Overview" && <OverviewTab artifact={artifact} />}
      {artifact && tab === "Content" && <ContentTab artifact={artifact} />}
      {artifact && tab === "Media" && (
        <MediaTab examId={examId} artifact={artifact} onUploaded={() => mutate()} />
      )}
      {tab === "Pipeline" && <PipelineTab examId={examId} onDone={() => mutate()} />}
    </div>
  );
}

function OverviewTab({ artifact }: { artifact: MockExamArtifact }) {
  return (
    <dl className="grid grid-cols-2 gap-3 text-sm max-w-xl">
      {[
        ["Title", artifact.title],
        ["Time limit", `${artifact.time_limit_minutes} min`],
        ["Total questions", artifact.total_questions],
        ["Parts", artifact.parts_count],
        ["Pass threshold", artifact.pass_threshold ?? "not published"],
        ["Max score", artifact.max_score ?? "not published"],
      ].map(([label, value]) => (
        <div key={label as string} className="bg-gray-800/50 rounded p-3">
          <dt className="text-gray-400 text-xs">{label}</dt>
          <dd className="font-semibold">{value}</dd>
        </div>
      ))}
    </dl>
  );
}

function ContentTab({ artifact }: { artifact: MockExamArtifact }) {
  const questionsByPassage = new Map<string | null, Question[]>();
  for (const q of artifact.questions) {
    const key = q.passage_id;
    if (!questionsByPassage.has(key)) questionsByPassage.set(key, []);
    questionsByPassage.get(key)!.push(q);
  }
  // Passages first (in order), then any passage-less questions (e.g. speaking/writing without a shared text) last.
  const passages = [...artifact.passages].sort((a, b) => a.order_index - b.order_index);
  const orphanQuestions = questionsByPassage.get(null) ?? [];

  return (
    <div className="space-y-6">
      {passages.map((p) => (
        <div key={p.id} className="space-y-3">
          <div className="bg-gray-900 border border-gray-700 rounded p-3 text-sm">
            <div className="flex items-center gap-2 text-gray-400 text-xs mb-1">
              <span>{p.id}</span>
              {p.part_number != null && <span>· part {p.part_number}</span>}
              <span>· {p.passage_type}</span>
            </div>
            {p.title && <p className="font-semibold mb-1">{p.title}</p>}
            {p.content_nl && <p className="whitespace-pre-wrap text-gray-200">{p.content_nl}</p>}
            {p.scene_description && (
              <p className="text-gray-400 text-xs italic mt-1">Scene: {p.scene_description}</p>
            )}
            {!p.content_nl && !p.scene_description && (
              <p className="text-gray-500 text-xs italic">No text for this passage.</p>
            )}
          </div>
          <div className="space-y-3 pl-3">
            {(questionsByPassage.get(p.id) ?? []).map((q) => (
              <QuestionCard key={q.id} q={q} />
            ))}
          </div>
        </div>
      ))}

      {orphanQuestions.length > 0 && (
        <div className="space-y-3">
          {orphanQuestions.map((q) => (
            <QuestionCard key={q.id} q={q} />
          ))}
        </div>
      )}
    </div>
  );
}

function QuestionCard({ q }: { q: Question }) {
  return (
    <div className="bg-gray-800/50 rounded p-3 text-sm space-y-1">
      <div className="flex items-center gap-2 text-gray-400 text-xs">
        <span>{q.id}</span>
        {q.part_number != null && <span>· part {q.part_number}</span>}
        {q.category && <span>· {q.category}</span>}
        {q.year_asked && <span>· asked in {q.year_asked}</span>}
      </div>
      <p className="font-medium">{q.question_text}</p>
      {q.options && (
        <ul className="list-disc list-inside text-gray-300">
          {q.options.map((o) => (
            <li key={o} className={o === q.answer ? "text-green-400" : ""}>{o}</li>
          ))}
        </ul>
      )}
      {q.grading_rubric && (
        <p className="text-gray-400 text-xs">
          Rubric: {q.grading_rubric.map((r) => `${r.criterion} (${r.max_points}pt)`).join(", ")}
        </p>
      )}
      {q.model_answer && <p className="text-gray-400 text-xs italic">Model answer: {q.model_answer}</p>}
    </div>
  );
}

function MediaTab({
  examId,
  artifact,
  onUploaded,
}: {
  examId: string;
  artifact: MockExamArtifact;
  onUploaded: () => void;
}) {
  const [openPrompt, setOpenPrompt] = useState<string | null>(null);
  const [uploading, setUploading] = useState<string | null>(null);

  const upload = async (passageId: string, imageIndex: number, file: File) => {
    const key = `${passageId}-image-${imageIndex}`;
    setUploading(key);
    try {
      const form = new FormData();
      form.append("passage_id", passageId);
      form.append("image_index", String(imageIndex));
      form.append("file", file);
      await fetch(`${API_URL}/api/mock-exams/${examId}/upload-image`, { method: "POST", body: form });
      onUploaded();
    } finally {
      setUploading(null);
    }
  };

  const uploadOption = async (questionId: string, optionIndex: number, file: File) => {
    const key = `${questionId}-${optionIndex}`;
    setUploading(key);
    try {
      const form = new FormData();
      form.append("question_id", questionId);
      form.append("option_index", String(optionIndex));
      form.append("file", file);
      await fetch(`${API_URL}/api/mock-exams/${examId}/upload-option-image`, { method: "POST", body: form });
      onUploaded();
    } finally {
      setUploading(null);
    }
  };

  const uploadAudio = async (passageId: string, file: File) => {
    const key = `${passageId}-audio`;
    setUploading(key);
    try {
      const form = new FormData();
      form.append("passage_id", passageId);
      form.append("file", file);
      await fetch(`${API_URL}/api/mock-exams/${examId}/upload-audio`, { method: "POST", body: form });
      onUploaded();
    } finally {
      setUploading(null);
    }
  };

  const uploadVideo = async (passageId: string, file: File) => {
    const key = `${passageId}-video`;
    setUploading(key);
    try {
      const form = new FormData();
      form.append("passage_id", passageId);
      form.append("file", file);
      await fetch(`${API_URL}/api/mock-exams/${examId}/upload-video`, { method: "POST", body: form });
      onUploaded();
    } finally {
      setUploading(null);
    }
  };

  const generateVoice = async (passageId: string) => {
    const key = `${passageId}-generate`;
    setUploading(key);
    try {
      const form = new FormData();
      form.append("passage_id", passageId);
      await fetch(`${API_URL}/api/mock-exams/${examId}/generate-voice`, { method: "POST", body: form });
      onUploaded();
    } finally {
      setUploading(null);
    }
  };

  const generatePassageAudio = async (passageId: string) => {
    const key = `${passageId}-audio-generate`;
    setUploading(key);
    try {
      const form = new FormData();
      form.append("passage_id", passageId);
      await fetch(`${API_URL}/api/mock-exams/${examId}/generate-passage-audio`, { method: "POST", body: form });
      onUploaded();
    } finally {
      setUploading(null);
    }
  };

  const uploadQuestionAudio = async (questionId: string, file: File) => {
    const key = `${questionId}-audio`;
    setUploading(key);
    try {
      const form = new FormData();
      form.append("question_id", questionId);
      form.append("file", file);
      await fetch(`${API_URL}/api/mock-exams/${examId}/upload-question-audio`, { method: "POST", body: form });
      onUploaded();
    } finally {
      setUploading(null);
    }
  };

  const generateQuestionAudio = async (questionId: string) => {
    const key = `${questionId}-audio-generate`;
    setUploading(key);
    try {
      const form = new FormData();
      form.append("question_id", questionId);
      await fetch(`${API_URL}/api/mock-exams/${examId}/generate-question-audio`, { method: "POST", body: form });
      onUploaded();
    } finally {
      setUploading(null);
    }
  };

  const refreshImagePrompt = async (passageId: string) => {
    const key = `${passageId}-prompt`;
    setUploading(key);
    try {
      const form = new FormData();
      form.append("passage_id", passageId);
      await fetch(`${API_URL}/api/mock-exams/${examId}/refresh-image-prompt`, { method: "POST", body: form });
      onUploaded();
    } finally {
      setUploading(null);
    }
  };

  const mediaOnly = artifact.passages.filter(
    (p) => p.passage_type !== "text" || p.scene_description || (p.image_prompt && p.image_prompt.length > 0)
  );
  const pictureChoiceQuestions = artifact.questions.filter(
    (q) => q.option_image_prompts && q.option_image_prompts.length > 0
  );
  const spokenQuestions = artifact.questions.filter((q) => q.audio_script?.trim());
  if (mediaOnly.length === 0 && pictureChoiceQuestions.length === 0 && spokenQuestions.length === 0) {
    return <p className="text-gray-500 text-sm">This section has no media (text-only passages).</p>;
  }
  return (
    <div className="space-y-4">
      {mediaOnly.map((p) => (
        <div key={p.id} className="bg-gray-800/50 rounded p-3 text-sm space-y-2">
          <div className="flex items-center justify-between">
            <span className="font-medium">{p.title || p.id}</span>
            <span className="text-xs text-gray-400">{p.passage_type}</span>
          </div>

          <div className="flex flex-wrap gap-2">
            {p.media_urls.map((m) => (
              <div key={m.url} className="border border-gray-700 rounded p-1">
                {m.type === "image" && (
                  <img src={`${API_URL}/api/media/image?path=${encodeURIComponent(m.url)}`} alt="" className="h-24" />
                )}
                {m.type === "audio" && <audio controls src={`${API_URL}/api/media/audio?path=${encodeURIComponent(m.url)}`} />}
                {m.type === "video" && <video controls className="h-40" src={`${API_URL}/api/media/video?path=${encodeURIComponent(m.url)}`} />}
              </div>
            ))}
            {p.media_urls.length === 0 && <span className="text-gray-500 text-xs">No media generated yet</span>}
          </div>

          <button
            onClick={() => refreshImagePrompt(p.id)}
            disabled={uploading === `${p.id}-prompt`}
            className="text-xs text-sky-400 hover:underline disabled:cursor-not-allowed disabled:opacity-50"
          >
            {uploading === `${p.id}-prompt` ? "Refreshing image prompt..." : "Refresh image prompt"}
          </button>

          {(p.scene_description || p.image_prompt?.length) && (
            <VisualScriptBlock
              passage={p}
              openPrompt={openPrompt}
              onToggle={(key) => setOpenPrompt(openPrompt === key ? null : key)}
            />
          )}

          {p.passage_type === "video" ? (
            <div className="space-y-2">
              <p className="text-xs text-gray-400">
                Presenter: <span className="font-medium text-gray-200">{p.presenter_gender ?? "female"}</span>
              </p>
              <div className="flex flex-wrap items-center gap-3">
                <button
                  onClick={() => setOpenPrompt(openPrompt === `${p.id}-script` ? null : `${p.id}-script`)}
                  className="text-xs text-sky-400 hover:underline"
                >
                  {openPrompt === `${p.id}-script` ? "Hide voice script" : "Show voice script"}
                </button>
                <button
                  onClick={() => generateVoice(p.id)}
                  disabled={uploading === `${p.id}-generate`}
                  className="text-xs text-emerald-400 hover:underline disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {uploading === `${p.id}-generate` ? "Generating voice..." : `Generate ${p.presenter_gender ?? "female"} voice`}
                </button>
              </div>
              {openPrompt === `${p.id}-script` && (
                <pre className="bg-black/40 p-2 rounded text-xs whitespace-pre-wrap">{p.content_nl}</pre>
              )}
              <div className="flex flex-wrap gap-3">
                <label className="inline-block cursor-pointer text-xs text-gray-400">
                  {uploading === `${p.id}-video` ? "Uploading..." : "Upload video"}
                  <input
                    type="file"
                    accept="video/mp4,video/webm,video/quicktime,video/x-m4v,.mp4,.webm,.mov,.m4v"
                    className="hidden"
                    onChange={(e) => e.target.files?.[0] && uploadVideo(p.id, e.target.files[0])}
                  />
                </label>
                <label className="inline-block text-xs text-gray-400 cursor-pointer">
                  {uploading === p.id ? "Uploading…" : "Upload image"}
                  <input
                    type="file"
                    accept=".png,.jpg,.jpeg,.webp"
                    className="hidden"
                    onChange={(e) => e.target.files?.[0] && upload(p.id, 0, e.target.files[0])}
                  />
                </label>
                <label className="inline-block text-xs text-gray-400 cursor-pointer">
                  {uploading === `${p.id}-audio` ? "Uploading…" : `Upload ${p.presenter_gender ?? "female"} voice`}
                  <input
                    type="file"
                    accept="audio/mpeg,audio/wav,audio/mp4,audio/ogg,.mp3,.wav,.m4a,.ogg"
                    className="hidden"
                    onChange={(e) => e.target.files?.[0] && uploadAudio(p.id, e.target.files[0])}
                  />
                </label>
              </div>
            </div>
          ) : (
            <>
              {(p.passage_type !== "text") && (() => {
                const question = artifact.questions.find((item) => item.passage_id === p.id);
                const audioScript = mockExamAudioScript(p, question);
                return audioScript ? (
                  <div className="space-y-2">
                    <div className="flex flex-wrap items-center gap-3">
                      <button
                        onClick={() => setOpenPrompt(openPrompt === `${p.id}-audio-script` ? null : `${p.id}-audio-script`)}
                        className="text-xs text-sky-400 hover:underline"
                      >
                        {openPrompt === `${p.id}-audio-script` ? "Hide audio script" : "Show audio script"}
                      </button>
                      <button
                        onClick={() => generatePassageAudio(p.id)}
                        disabled={uploading === `${p.id}-audio-generate`}
                        className="text-xs text-emerald-400 hover:underline disabled:cursor-not-allowed disabled:opacity-50"
                      >
                        {uploading === `${p.id}-audio-generate` ? "Generating audio..." : "Generate audio"}
                      </button>
                      <label className="inline-block cursor-pointer text-xs text-gray-400">
                        {uploading === `${p.id}-audio` ? "Uploading..." : "Upload audio"}
                        <input
                          type="file"
                          accept="audio/mpeg,audio/wav,audio/mp4,audio/ogg,.mp3,.wav,.m4a,.ogg"
                          className="hidden"
                          onChange={(e) => e.target.files?.[0] && uploadAudio(p.id, e.target.files[0])}
                        />
                      </label>
                    </div>
                    {openPrompt === `${p.id}-audio-script` && (
                      <pre className="bg-black/40 p-2 rounded text-xs whitespace-pre-wrap">
                        {genericTtsScript(audioScript, p.passage_type === "one_picture")}
                      </pre>
                    )}
                  </div>
                ) : null;
              })()}
            <div className="flex flex-wrap gap-3">
              {Array.from({ length: p.passage_type === "three_picture" ? 3 : p.passage_type === "two_picture" ? 2 : 1 }, (_, imageIndex) => (
                <label key={imageIndex} className="inline-block cursor-pointer text-xs text-gray-400">
                  {uploading === `${p.id}-image-${imageIndex}` ? "Uploading..." : `Upload image ${imageIndex + 1}`}
                  <input
                    type="file"
                    accept=".png,.jpg,.jpeg,.webp"
                    className="hidden"
                    onChange={(e) => e.target.files?.[0] && upload(p.id, imageIndex, e.target.files[0])}
                  />
                </label>
              ))}
            </div>
            <QuestionAudioList
              questions={spokenQuestions.filter((q) => q.passage_id === p.id)}
              openPrompt={openPrompt}
              uploading={uploading}
              onToggleScript={(key) => setOpenPrompt(openPrompt === key ? null : key)}
              onGenerate={generateQuestionAudio}
              onUpload={uploadQuestionAudio}
            />
            </>
          )}
        </div>
      ))}

      {pictureChoiceQuestions.map((q) => (
        <div key={q.id} className="bg-gray-800/50 rounded p-3 text-sm space-y-2">
          <div className="flex items-center justify-between">
            <span className="font-medium">{q.question_text}</span>
            <span className="text-xs text-gray-400">picture-choice options</span>
          </div>
          <div className="flex flex-wrap gap-3">
            {(q.option_image_prompts ?? []).map((prompt, i) => {
              const url = q.option_media_urls?.[i];
              const key = `${q.id}-${i}`;
              return (
                <div key={key} className="border border-gray-700 rounded p-2 space-y-1 w-40">
                  <span className="text-xs text-gray-400">Option {String.fromCharCode(65 + i)}: {q.options?.[i]}</span>
                  {url ? (
                    <img src={`${API_URL}/api/media/image?path=${encodeURIComponent(url)}`} alt="" className="h-20 w-full object-cover rounded" />
                  ) : (
                    <span className="block text-xs text-gray-500">No image yet</span>
                  )}
                  <button
                    onClick={() => setOpenPrompt(openPrompt === key ? null : key)}
                    className="text-xs text-sky-400 hover:underline block"
                  >
                    {openPrompt === key ? "Hide prompt" : "Show prompt"}
                  </button>
                  {openPrompt === key && (
                    <pre className="bg-black/40 p-2 rounded text-xs whitespace-pre-wrap">{prompt}</pre>
                  )}
                  <label className="inline-block text-xs text-gray-400 cursor-pointer">
                    {uploading === key ? "Uploading…" : "Upload image"}
                    <input
                      type="file"
                      accept=".png,.jpg,.jpeg,.webp"
                      className="hidden"
                      onChange={(e) => e.target.files?.[0] && uploadOption(q.id, i, e.target.files[0])}
                    />
                  </label>
                </div>
              );
            })}
          </div>
        </div>
      ))}

      <QuestionAudioList
        questions={spokenQuestions.filter((q) => !mediaOnly.some((p) => p.id === q.passage_id))}
        openPrompt={openPrompt}
        uploading={uploading}
        onToggleScript={(key) => setOpenPrompt(openPrompt === key ? null : key)}
        onGenerate={generateQuestionAudio}
        onUpload={uploadQuestionAudio}
      />
    </div>
  );
}

function QuestionAudioList({
  questions,
  openPrompt,
  uploading,
  onToggleScript,
  onGenerate,
  onUpload,
}: {
  questions: Question[];
  openPrompt: string | null;
  uploading: string | null;
  onToggleScript: (key: string) => void;
  onGenerate: (questionId: string) => void;
  onUpload: (questionId: string, file: File) => void;
}) {
  if (questions.length === 0) return null;
  return (
    <div className="space-y-2 border-t border-gray-700/60 pt-2">
      <p className="text-xs uppercase tracking-wide text-gray-400">
        Question audio ({questions.filter((q) => q.question_audio_url).length}/{questions.length} recorded)
      </p>
      {questions.map((q) => {
        const scriptKey = `${q.id}-audio-script`;
        return (
          <div key={q.id} className="rounded border border-gray-700/60 p-2 space-y-2">
            <p className="text-xs text-gray-300">{q.order_index}. {q.question_text}</p>
            {q.question_audio_url ? (
              <audio
                controls
                className="h-8 w-full max-w-sm"
                src={`${API_URL}/api/media/audio?path=${encodeURIComponent(q.question_audio_url)}`}
              />
            ) : (
              <span className="block text-xs text-gray-500">No audio yet</span>
            )}
            <div className="flex flex-wrap items-center gap-3">
              <button onClick={() => onToggleScript(scriptKey)} className="text-xs text-sky-400 hover:underline">
                {openPrompt === scriptKey ? "Hide audio script" : "Show audio script"}
              </button>
              <button
                onClick={() => onGenerate(q.id)}
                disabled={uploading === `${q.id}-audio-generate`}
                className="text-xs text-emerald-400 hover:underline disabled:cursor-not-allowed disabled:opacity-50"
              >
                {uploading === `${q.id}-audio-generate` ? "Generating audio..." : "Generate audio"}
              </button>
              <label className="inline-block cursor-pointer text-xs text-gray-400">
                {uploading === `${q.id}-audio` ? "Uploading..." : "Upload audio"}
                <input
                  type="file"
                  accept="audio/mpeg,audio/wav,audio/mp4,audio/ogg,.mp3,.wav,.m4a,.ogg"
                  className="hidden"
                  onChange={(e) => e.target.files?.[0] && onUpload(q.id, e.target.files[0])}
                />
              </label>
            </div>
            {openPrompt === scriptKey && (
              <pre className="bg-black/40 p-2 rounded text-xs whitespace-pre-wrap">{q.audio_script}</pre>
            )}
          </div>
        );
      })}
    </div>
  );
}

function mockExamAudioScript(passage: Passage, question: Question | undefined): string {
  if (passage.content_nl?.trim()) return passage.content_nl.trim();
  if (question?.question_text?.trim()) return question.question_text.trim();
  return "";
}

function VisualScriptBlock({
  passage,
  openPrompt,
  onToggle,
}: {
  passage: Passage;
  openPrompt: string | null;
  onToggle: (key: string) => void;
}) {
  const promptKey = `${passage.id}-visual-prompt`;
  const scripts = (passage.scene_description ?? "").split("|").map((script) => script.trim()).filter(Boolean);
  const prompts = passage.image_prompt?.length ? passage.image_prompt : scripts;
  return (
    <div className="rounded border border-amber-700/40 bg-amber-950/20 p-3 text-xs">
      <p className="font-medium text-amber-200">Image script</p>
      {scripts.length > 0 ? (
        <div className="mt-2 grid gap-2">
          {scripts.map((script, index) => (
            <pre key={index} className="whitespace-pre-wrap rounded bg-black/30 p-2 text-gray-100">
              {script}
            </pre>
          ))}
        </div>
      ) : (
        <p className="mt-1 text-gray-500">No image script saved for this passage.</p>
      )}
      <button onClick={() => onToggle(promptKey)} className="mt-3 text-sky-400 hover:underline">
        {openPrompt === promptKey ? "Hide generated image prompt" : "Show generated image prompt"}
      </button>
      {openPrompt === promptKey && (
        <div className="mt-2 grid gap-3">
          {prompts.map((prompt, imageIndex) => (
            <label key={imageIndex} className="grid gap-1 text-gray-400">
              {passage.passage_type === "two_picture" || passage.passage_type === "three_picture" ? `Image ${imageIndex + 1} prompt` : "Generated image prompt"}
              <textarea readOnly value={prompt} rows={5} className="w-full resize-y rounded bg-black/40 p-2 text-xs text-gray-100 outline-none" />
            </label>
          ))}
        </div>
      )}
    </div>
  );
}

function PipelineTab({ examId, onDone }: { examId: string; onDone: () => void }) {
  const [section, examNumber] = (() => {
    const parts = examId.split("-");
    return [parts[1], Number(parts[2])];
  })();

  const [jobId, setJobId] = useState<string | null>(null);
  const [logs, setLogs] = useState<string[]>([]);
  const logEndRef = useRef<HTMLDivElement>(null);
  const esRef = useRef<EventSource | null>(null);

  const runStage = useCallback(
    async (stage: string) => {
      setLogs([]);
      const job = await apiFetch<{ job_id: string }>("/api/mock-exams/run", {
        method: "POST",
        body: JSON.stringify({ stage, section, exam_number: examNumber }),
      });
      setJobId(job.job_id);
    },
    [section, examNumber]
  );

  useEffect(() => {
    if (!jobId) return;
    const es = new EventSource(`${API_URL}/api/pipeline/logs/${jobId}`);
    esRef.current = es;
    es.onmessage = (e) => {
      setLogs((prev) => [...prev, e.data]);
      if (e.data.startsWith("__STATUS__")) {
        es.close();
        onDone();
      }
    };
    es.onerror = () => es.close();
    return () => es.close();
  }, [jobId, onDone]);

  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [logs]);

  return (
    <div className="space-y-3">
      <div className="flex gap-2">
        <button onClick={() => runStage("content")} className="bg-sky-600 hover:bg-sky-500 text-white px-3 py-1.5 rounded text-sm">
          Generate Content
        </button>
        <button onClick={() => runStage("media")} className="bg-sky-600 hover:bg-sky-500 text-white px-3 py-1.5 rounded text-sm">
          Generate Media
        </button>
        {(section === "knm" || section === "listening") && (
          <button
            onClick={() => runStage("question_audio")}
            className="bg-indigo-600 hover:bg-indigo-500 text-white px-3 py-1.5 rounded text-sm"
          >
            Generate Question Audio
          </button>
        )}
        <button onClick={() => runStage("export")} className="bg-emerald-600 hover:bg-emerald-500 text-white px-3 py-1.5 rounded text-sm">
          Export to Postgres
        </button>
      </div>
      <pre className="bg-black/60 rounded p-3 text-xs h-80 overflow-y-auto whitespace-pre-wrap">
        {logs.join("\n")}
        <div ref={logEndRef} />
      </pre>
    </div>
  );
}
