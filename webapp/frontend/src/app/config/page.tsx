"use client";
import { useState } from "react";
import useSWR from "swr";
import { apiFetch } from "@/lib/api";

const CONFIGS = ["playlists", "pedagogy", "scheduling", "visual_style", "topic_backlog"];

interface ConfigResponse {
  name: string;
  content: string;
}

const fetcher = (url: string) => apiFetch<ConfigResponse>(url);

export default function ConfigPage() {
  const [selected, setSelected] = useState("playlists");
  const [editContent, setEditContent] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [saveMsg, setSaveMsg] = useState("");

  const { data, mutate } = useSWR(`/api/config/${selected}`, fetcher);

  const content = editContent ?? data?.content ?? "";

  const save = async () => {
    setSaving(true);
    setSaveMsg("");
    try {
      await apiFetch(`/api/config/${selected}`, {
        method: "PUT",
        body: JSON.stringify({ content }),
      });
      setSaveMsg("Saved ✓");
      setEditContent(null);
      mutate();
    } catch (err) {
      setSaveMsg(String(err));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-5">
      <h1 className="text-2xl font-bold">Config</h1>

      <div className="flex gap-2 flex-wrap">
        {CONFIGS.map((c) => (
          <button
            key={c}
            onClick={() => { setSelected(c); setEditContent(null); setSaveMsg(""); }}
            className={`px-3 py-1.5 rounded-lg text-sm border transition ${
              selected === c
                ? "border-sky-600 bg-sky-900/30 text-sky-300"
                : "border-gray-700 text-gray-400 hover:border-gray-600"
            }`}
          >
            {c.replace("_", " ")}
          </button>
        ))}
      </div>

      <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
        <div className="flex items-center justify-between px-4 py-3 border-b border-gray-800">
          <span className="text-sm font-mono text-gray-300">config/{selected}.yaml</span>
          <div className="flex items-center gap-3">
            {saveMsg && <span className={`text-xs ${saveMsg.startsWith("Saved") ? "text-green-400" : "text-red-400"}`}>{saveMsg}</span>}
            {editContent !== null && (
              <>
                <button
                  onClick={() => { setEditContent(null); setSaveMsg(""); }}
                  className="text-xs text-gray-400 hover:text-white"
                >
                  Cancel
                </button>
                <button
                  onClick={save}
                  disabled={saving}
                  className="text-xs bg-sky-600 hover:bg-sky-500 text-white px-3 py-1.5 rounded-lg disabled:opacity-50"
                >
                  {saving ? "Saving…" : "Save"}
                </button>
              </>
            )}
            {editContent === null && (
              <button
                onClick={() => setEditContent(data?.content ?? "")}
                className="text-xs text-gray-400 hover:text-white border border-gray-700 px-3 py-1.5 rounded-lg"
              >
                Edit
              </button>
            )}
          </div>
        </div>
        {editContent !== null ? (
          <textarea
            value={content}
            onChange={(e) => setEditContent(e.target.value)}
            className="w-full h-[600px] bg-gray-950 text-gray-200 text-xs font-mono p-4 focus:outline-none resize-none"
            spellCheck={false}
          />
        ) : (
          <pre className="text-xs text-gray-300 font-mono p-4 whitespace-pre-wrap overflow-auto max-h-[600px]">
            {data?.content ?? "Loading…"}
          </pre>
        )}
      </div>
    </div>
  );
}
