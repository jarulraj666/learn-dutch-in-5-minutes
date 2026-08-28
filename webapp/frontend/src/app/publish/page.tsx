"use client";
import { useState, useMemo, useEffect } from "react";
import useSWR from "swr";
import { apiFetch } from "@/lib/api";
import type {
  PlatformStatusItem,
  PlatformStatusResponse,
} from "@/lib/types";
import { ExternalLink, ChevronUp, ChevronDown, ChevronsUpDown } from "lucide-react";

const fetcher = (url: string) => apiFetch<PlatformStatusResponse>(url);

// ---------------------------------------------------------------------------
// Platform config
// ---------------------------------------------------------------------------

const PLATFORMS = [
  { key: "youtube",        label: "YouTube",   accent: "text-red-400",  border: "border-red-500"  },
  { key: "youtube_shorts", label: "YT Shorts", accent: "text-red-300",  border: "border-red-400"  },
  { key: "instagram",      label: "Instagram", accent: "text-pink-400", border: "border-pink-500" },
  { key: "tiktok",         label: "TikTok",    accent: "text-cyan-400", border: "border-cyan-500" },
  { key: "facebook",       label: "Facebook",  accent: "text-blue-400", border: "border-blue-500" },
] as const;

type PlatformKey = (typeof PLATFORMS)[number]["key"];

// ---------------------------------------------------------------------------
// Shared components
// ---------------------------------------------------------------------------

function StatusDot({ uploaded, scheduled }: { uploaded: boolean; scheduled: boolean }) {
  if (uploaded)  return <span className="inline-block w-2 h-2 rounded-full bg-green-400" title="Published" />;
  if (scheduled) return <span className="inline-block w-2 h-2 rounded-full bg-blue-400"  title="Scheduled" />;
  return              <span className="inline-block w-2 h-2 rounded-full bg-gray-600"  title="Pending"   />;
}

function CountBadge({ value, color }: { value: number; color: string }) {
  return (
    <span className={`inline-flex items-center justify-center min-w-[1.25rem] h-5 px-1 rounded text-[11px] font-mono font-semibold ${color}`}>
      {value}
    </span>
  );
}

function StatusChip({ status, hasId }: { status: string; hasId: boolean }) {
  if (hasId) return <span className="px-2 py-0.5 rounded text-xs font-medium bg-green-500/20 text-green-300">published</span>;
  const map: Record<string, string> = {
    scheduled:        "bg-blue-500/20 text-blue-300",
    upload_failed:    "bg-red-500/20 text-red-300",
    ready_for_upload: "bg-yellow-500/20 text-yellow-300",
    uploaded:         "bg-green-500/20 text-green-300",
  };
  return (
    <span className={`px-2 py-0.5 rounded text-xs font-medium ${map[status] ?? "bg-gray-700/60 text-gray-400"}`}>
      {status.replace(/_/g, " ")}
    </span>
  );
}

function fmtDate(iso: string | null | undefined) {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString(undefined, { day: "2-digit", month: "short", year: "numeric" });
}

function fmtDateTime(iso: string | null | undefined) {
  if (!iso) return "—";
  return new Date(iso).toLocaleString(undefined, {
    day: "2-digit", month: "short", year: "numeric",
    hour: "2-digit", minute: "2-digit",
  });
}

// ---------------------------------------------------------------------------
// Sorting
// ---------------------------------------------------------------------------

type SortDir = "asc" | "desc" | null;

function useSortable<T>(rows: T[], key: keyof T | null, dir: SortDir): T[] {
  return useMemo(() => {
    if (!key || !dir) return rows;
    return [...rows].sort((a, b) => {
      const av = a[key];
      const bv = b[key];
      if (av == null && bv == null) return 0;
      if (av == null) return 1;
      if (bv == null) return -1;
      // Convert ISO date strings to timestamps so different timezone offsets sort correctly
      let va: string | number = typeof av === "number" ? av : String(av);
      let vb: string | number = typeof bv === "number" ? bv : String(bv);
      if (typeof av === "string" && typeof bv === "string" && /^\d{4}-\d{2}-\d{2}/.test(av)) {
        const ta = Date.parse(av), tb = Date.parse(bv);
        if (!isNaN(ta) && !isNaN(tb)) { va = ta; vb = tb; }
      }
      const cmp = va < vb ? -1 : va > vb ? 1 : 0;
      return dir === "asc" ? cmp : -cmp;
    });
  }, [rows, key, dir]);
}

function SortableHeader({
  label, sortKey, active, dir, onSort,
}: {
  label: string; sortKey: string; active: boolean; dir: SortDir;
  onSort: (k: string) => void;
}) {
  return (
    <th
      className="px-4 py-3 text-gray-400 font-medium whitespace-nowrap cursor-pointer select-none hover:text-gray-200 transition-colors"
      onClick={() => onSort(sortKey)}
    >
      <span className="inline-flex items-center gap-1">
        {label}
        {active && dir === "asc"  && <ChevronUp   size={12} className="text-sky-400" />}
        {active && dir === "desc" && <ChevronDown  size={12} className="text-sky-400" />}
        {!active                  && <ChevronsUpDown size={12} className="text-gray-600" />}
      </span>
    </th>
  );
}

// ---------------------------------------------------------------------------
// YouTube main video table
// ---------------------------------------------------------------------------

type YoutubeRow = PlatformStatusItem & { _published: string };

function YoutubeTable({ items }: { items: PlatformStatusItem[] }) {
  const [filter, setFilter] = useState<"all" | "published" | "pending">("all");
  const [sortKey, setSortKey] = useState<keyof YoutubeRow | null>(null);
  const [sortDir, setSortDir] = useState<SortDir>(null);
  const [markOpen, setMarkOpen] = useState<Record<string, boolean>>({});
  const [videoIdInput, setVideoIdInput] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState<Record<string, boolean>>({});

  const toggleSort = (k: string) => {
    const key = k as keyof YoutubeRow;
    if (sortKey === key) {
      setSortDir((d) => d === "asc" ? "desc" : d === "desc" ? null : "asc");
      if (sortDir === "desc") setSortKey(null);
    } else {
      setSortKey(key);
      setSortDir("asc");
    }
  };

  const enriched: YoutubeRow[] = items.map((i) => ({
    ...i,
    _published: i.youtube.published_at ?? "",
  }));

  const markUploaded = async (topicId: string, videoId: string) => {
    if (!videoId.trim()) return;
    setBusy((b) => ({ ...b, [topicId]: true }));
    try {
      await apiFetch(
        `/api/publish/youtube/${topicId}/mark-uploaded?video_id=${encodeURIComponent(videoId.trim())}`,
        { method: "POST" },
      );
      setMarkOpen((p) => ({ ...p, [topicId]: false }));
      setVideoIdInput((p) => ({ ...p, [topicId]: "" }));
      // Trigger parent SWR revalidation via window event
      window.dispatchEvent(new Event("publish-refresh"));
    } catch (err) { alert(String(err)); }
    finally { setBusy((b) => ({ ...b, [topicId]: false })); }
  };

  const filtered = enriched.filter((i) => {
    if (filter === "published") return !!i.youtube.video_id;
    if (filter === "pending")   return !i.youtube.video_id;
    return true;
  });

  const sorted = useSortable(filtered, sortKey, sortDir);
  const publishedCount = items.filter((i) => !!i.youtube.video_id).length;
  const pendingCount   = items.filter((i) => !i.youtube.video_id).length;

  const sh = (label: string, key: string) => (
    <SortableHeader label={label} sortKey={key} active={sortKey === key} dir={sortDir} onSort={toggleSort} />
  );

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2">
        {(["all", "published", "pending"] as const).map((f) => {
          const label = f === "all" ? `All (${items.length})` : f === "published" ? `Published (${publishedCount})` : `Pending (${pendingCount})`;
          return (
            <button key={f} onClick={() => setFilter(f)}
              className={`px-3 py-1 rounded-lg text-xs font-medium border transition-all ${
                filter === f
                  ? "border-sky-600 bg-sky-900/30 text-sky-300"
                  : "border-gray-700 text-gray-500 hover:border-gray-600 hover:text-gray-300"
              }`}>
              {label.charAt(0).toUpperCase() + label.slice(1)}
            </button>
          );
        })}
      </div>

      <div className="overflow-x-auto rounded-xl border border-gray-800">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-800 text-left bg-gray-900/60">
              <th className="px-4 py-3 w-6" />
              {sh("Title", "title")}
              {sh("Level", "level")}
              {sh("Category", "category")}
              {sh("Status", "youtube")}
              {sh("Published", "_published")}
              <th className="px-4 py-3 text-gray-400 font-medium whitespace-nowrap">Actions</th>
            </tr>
          </thead>
          <tbody className="bg-gray-900">
            {sorted.length === 0 ? (
              <tr><td colSpan={7} className="px-4 py-10 text-center text-gray-500">No videos found</td></tr>
            ) : sorted.map((item) => (
              <tr key={item.topic_id} className="border-b border-gray-800/40 hover:bg-gray-800/30 transition-colors">
                <td className="px-4 py-3">
                  <StatusDot uploaded={!!item.youtube.video_id} scheduled={false} />
                </td>
                <td className="px-4 py-3 text-gray-200 max-w-xs">
                  <span className="block truncate" title={item.title}>{item.title}</span>
                </td>
                <td className="px-4 py-3 text-gray-400 whitespace-nowrap">{item.level}</td>
                <td className="px-4 py-3 text-gray-400 capitalize whitespace-nowrap">{item.category.replace(/_/g, " ")}</td>
                <td className="px-4 py-3">
                  <StatusChip status={item.youtube.status} hasId={!!item.youtube.video_id} />
                </td>
                <td className="px-4 py-3 text-gray-400 text-xs whitespace-nowrap">{fmtDate(item.youtube.published_at)}</td>
                <td className="px-4 py-3 min-w-[10rem]">
                  {item.youtube.url ? (
                    <div className="flex items-center gap-2">
                      <a href={item.youtube.url} target="_blank" rel="noopener noreferrer"
                        className="flex items-center gap-1 text-red-400 hover:text-red-300 text-xs">
                        <ExternalLink size={12} /> Watch
                      </a>
                    </div>
                  ) : (
                    <div className="space-y-1.5">
                      {!markOpen[item.topic_id] ? (
                        <button
                          onClick={() => setMarkOpen((p) => ({ ...p, [item.topic_id]: true }))}
                          className="text-xs text-gray-500 hover:text-red-400 border border-gray-700 hover:border-red-700 px-2 py-1 rounded-lg transition-colors"
                        >
                          ✓ Set Video ID
                        </button>
                      ) : (
                        <div className="flex items-center gap-1.5">
                          <input
                            type="text"
                            placeholder="YouTube video ID"
                            value={videoIdInput[item.topic_id] || ""}
                            onChange={(e) => setVideoIdInput((p) => ({ ...p, [item.topic_id]: e.target.value }))}
                            onKeyDown={(e) => {
                              if (e.key === "Enter") markUploaded(item.topic_id, videoIdInput[item.topic_id] || "");
                              if (e.key === "Escape") setMarkOpen((p) => ({ ...p, [item.topic_id]: false }));
                            }}
                            autoFocus
                            className="text-xs bg-gray-800 border border-gray-700 focus:border-red-600 rounded px-2 py-1 text-gray-200 w-36 outline-none"
                          />
                          <button
                            onClick={() => markUploaded(item.topic_id, videoIdInput[item.topic_id] || "")}
                            disabled={!videoIdInput[item.topic_id]?.trim() || busy[item.topic_id]}
                            className="text-xs bg-red-700 hover:bg-red-600 text-white px-2 py-1 rounded-lg disabled:opacity-40"
                          >
                            {busy[item.topic_id] ? "…" : "Save"}
                          </button>
                          <button
                            onClick={() => setMarkOpen((p) => ({ ...p, [item.topic_id]: false }))}
                            className="text-xs text-gray-600 hover:text-gray-400"
                          >
                            ✕
                          </button>
                        </div>
                      )}
                    </div>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Shorts / Reels table (all non-YouTube platforms)
// ---------------------------------------------------------------------------

type ShortRow = {
  topic_id: string; title: string; level: string; scene: number;
  description: string | null; uploadedId: string | null; url: string | null;
  scheduledAt: string | null; manuallyMarked: boolean; hasVideo: boolean;
};

function buildShortRows(items: PlatformStatusItem[], platform: PlatformKey): ShortRow[] {
  const rows: ShortRow[] = [];
  for (const item of items) {
    for (const s of item.shorts) {
      let uploadedId: string | null = null, url: string | null = null;
      let scheduledAt: string | null = null, manuallyMarked = false;

      if (platform === "youtube_shorts") {
        uploadedId = s.youtube?.short_video_id ?? null;
        url        = s.youtube?.url ?? null;
        // No scheduling for YT Shorts — pipeline uploads directly
      } else if (platform === "instagram") {
        uploadedId     = s.instagram?.reel_id ?? null;
        url            = s.instagram?.permalink ?? null;
        scheduledAt    = s.instagram?.scheduled_at ?? null;
        manuallyMarked = s.instagram?.manually_marked ?? false;
      } else if (platform === "tiktok") {
        uploadedId  = s.tiktok?.publish_id ?? null;
        scheduledAt = s.tiktok?.scheduled_at ?? null;
      } else if (platform === "facebook") {
        uploadedId     = s.facebook?.post_id ?? null;
        scheduledAt    = s.facebook?.scheduled_at ?? null;
        manuallyMarked = s.facebook?.manually_marked ?? false;
      }

      if (!uploadedId && !scheduledAt && !s.video_file) continue;
      rows.push({ topic_id: item.topic_id, title: item.title, level: item.level,
        scene: s.scene, description: s.description, uploadedId, url, scheduledAt,
        manuallyMarked, hasVideo: !!s.video_file });
    }
  }
  return rows;
}

function ShortsTable({ items, platform, accent }: { items: PlatformStatusItem[]; platform: PlatformKey; accent: string }) {
  const isYtShorts = platform === "youtube_shorts";
  const allRows = buildShortRows(items, platform);
  const [filter, setFilter] = useState<"all" | "published" | "pending">("all");
  const [sortKey, setSortKey] = useState<keyof ShortRow | null>(null);
  const [sortDir, setSortDir] = useState<SortDir>(null);

  const toggleSort = (k: string) => {
    const key = k as keyof ShortRow;
    if (sortKey === key) {
      setSortDir((d) => d === "asc" ? "desc" : d === "desc" ? null : "asc");
      if (sortDir === "desc") setSortKey(null);
    } else {
      setSortKey(key);
      setSortDir("asc");
    }
  };

  const filtered = allRows.filter((r) => {
    if (filter === "published") return !!r.uploadedId;
    if (filter === "pending")   return !r.uploadedId;
    return true;
  });

  const rows = useSortable(filtered, sortKey, sortDir);
  const publishedCount = allRows.filter((r) => !!r.uploadedId).length;
  const pendingCount   = allRows.filter((r) => !r.uploadedId).length;

  const sh = (label: string, key: string) => (
    <SortableHeader label={label} sortKey={key} active={sortKey === key} dir={sortDir} onSort={toggleSort} />
  );

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2">
        {(["all", "published", "pending"] as const).map((f) => {
          const label = f === "all" ? `All (${allRows.length})` : f === "published" ? `Published (${publishedCount})` : `Pending (${pendingCount})`;
          return (
            <button key={f} onClick={() => setFilter(f)}
              className={`px-3 py-1 rounded-lg text-xs font-medium border transition-all ${
                filter === f
                  ? "border-sky-600 bg-sky-900/30 text-sky-300"
                  : "border-gray-700 text-gray-500 hover:border-gray-600 hover:text-gray-300"
              }`}>
              {label.charAt(0).toUpperCase() + label.slice(1)}
            </button>
          );
        })}
      </div>

    <div className="overflow-x-auto rounded-xl border border-gray-800">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-gray-800 text-left bg-gray-900/60">
            <th className="px-4 py-3 w-6" />
            {sh("Episode", "title")}
            {sh("Level", "level")}
            {sh("Scene", "scene")}
            {sh("Description", "description")}
            {sh("Status", "uploadedId")}
            {!isYtShorts && sh("Scheduled", "scheduledAt")}
            <th className="px-4 py-3" />
          </tr>
        </thead>
        <tbody className="bg-gray-900">
          {rows.length === 0 ? (
            <tr><td colSpan={isYtShorts ? 7 : 8} className="px-4 py-10 text-center text-gray-500">No shorts found</td></tr>
          ) : rows.map((row, i) => (
            <tr key={`${row.topic_id}-${row.scene}-${i}`} className="border-b border-gray-800/40 hover:bg-gray-800/30 transition-colors">
              <td className="px-4 py-3">
                <StatusDot uploaded={!!row.uploadedId} scheduled={!isYtShorts && !!row.scheduledAt && !row.uploadedId} />
              </td>
              <td className="px-4 py-3 text-gray-200 max-w-[11rem]">
                <span className="block truncate" title={row.title}>{row.title}</span>
              </td>
              <td className="px-4 py-3 text-gray-400 whitespace-nowrap">{row.level}</td>
              <td className="px-4 py-3 text-gray-400 tabular-nums">{row.scene}</td>
              <td className="px-4 py-3 text-gray-500 text-xs max-w-[14rem]">
                <span className="block truncate" title={row.description ?? ""}>{row.description || "—"}</span>
              </td>
              <td className="px-4 py-3 whitespace-nowrap">
                {row.uploadedId ? (
                  <span className={`text-xs font-medium ${accent}`}>{row.manuallyMarked ? "✓ manual" : "✓ published"}</span>
                ) : !isYtShorts && row.scheduledAt ? (
                  <span className="text-xs text-blue-400">scheduled</span>
                ) : row.hasVideo ? (
                  <span className="text-xs text-gray-500">pending</span>
                ) : (
                  <span className="text-xs text-gray-700">no video</span>
                )}
              </td>
              {!isYtShorts && (
                <td className="px-4 py-3 text-gray-400 text-xs whitespace-nowrap">
                  {row.scheduledAt && !row.uploadedId ? fmtDateTime(row.scheduledAt) : "—"}
                </td>
              )}
              <td className="px-4 py-3">
                {row.url ? (
                  <a href={row.url} target="_blank" rel="noopener noreferrer"
                    className={`flex items-center gap-1 hover:underline text-xs ${accent}`}>
                    <ExternalLink size={12} /> View
                  </a>
                ) : row.uploadedId ? (
                  <span className="text-gray-500 text-xs font-mono">{row.uploadedId.slice(0, 14)}…</span>
                ) : (
                  <span className="text-gray-700 text-xs">—</span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Page root
// ---------------------------------------------------------------------------

export default function PublishPage() {
  const [activeTab, setActiveTab] = useState<PlatformKey>("youtube");
  const [dryRunOutput, setDryRunOutput] = useState("");
  const [executing, setExecuting] = useState(false);

  const { data, mutate, isLoading } = useSWR("/api/publish/platform-status", fetcher, {
    refreshInterval: 30_000,
  });

  // Allow child tables to trigger a revalidation via a custom window event
  useEffect(() => {
    const handler = () => mutate();
    window.addEventListener("publish-refresh", handler);
    return () => window.removeEventListener("publish-refresh", handler);
  }, [mutate]);

  const counts = data?.counts ?? {};
  const items  = data?.items  ?? [];
  const activePlatform = PLATFORMS.find((p) => p.key === activeTab)!;

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
      {/* Header */}
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Publish Dashboard</h1>
        {activeTab === "youtube" && (
          <div className="flex gap-2">
            <button onClick={dryRun}
              className="border border-gray-600 text-gray-300 hover:text-white px-4 py-2 rounded-lg text-sm">
              Dry Run
            </button>
            <button onClick={execute} disabled={executing}
              className="bg-red-700 hover:bg-red-600 text-white px-4 py-2 rounded-lg text-sm font-medium disabled:opacity-50">
              {executing ? "Uploading…" : "Execute Uploads"}
            </button>
          </div>
        )}
      </div>

      {/* Summary cards */}
      <div className="grid grid-cols-5 gap-3">
        {PLATFORMS.map((p) => {
          const c = counts[p.key] ?? { published: 0, scheduled: 0, pending: 0 };
          const isActive = activeTab === p.key;
          return (
            <button key={p.key} onClick={() => setActiveTab(p.key as PlatformKey)}
              className={`rounded-xl border p-4 text-left transition-all ${
                isActive ? `${p.border} bg-gray-800/60` : "border-gray-800 bg-gray-900 hover:border-gray-700"
              }`}>
              <div className={`text-xs font-semibold mb-3 ${isActive ? p.accent : "text-gray-400"}`}>{p.label}</div>
              <div className="flex flex-col gap-1.5">
                <div className="flex items-center justify-between">
                  <span className="text-[11px] text-gray-500">Published</span>
                  <CountBadge value={c.published} color="bg-green-500/20 text-green-300" />
                </div>
                {c.scheduled > 0 && p.key !== "youtube" && p.key !== "youtube_shorts" && (
                  <div className="flex items-center justify-between">
                    <span className="text-[11px] text-gray-500">Scheduled</span>
                    <CountBadge value={c.scheduled} color="bg-blue-500/20 text-blue-300" />
                  </div>
                )}
                <div className="flex items-center justify-between">
                  <span className="text-[11px] text-gray-500">Pending</span>
                  <CountBadge value={c.pending} color="bg-gray-700/60 text-gray-400" />
                </div>
              </div>
            </button>
          );
        })}
      </div>

      {/* Tab strip */}
      <div className="flex gap-0.5 border-b border-gray-800">
        {PLATFORMS.map((p) => {
          const c = counts[p.key] ?? { published: 0, scheduled: 0, pending: 0 };
          const isActive = activeTab === p.key;
          return (
            <button key={p.key} onClick={() => setActiveTab(p.key as PlatformKey)}
              className={`flex items-center gap-2 px-4 py-2.5 text-sm font-medium border-b-2 transition-all whitespace-nowrap ${
                isActive
                  ? `${p.border} ${p.accent}`
                  : "border-transparent text-gray-500 hover:text-gray-300 hover:border-gray-600"
              }`}>
              {p.label}
              <span className="flex items-center gap-1">
                <span className="text-green-400 text-xs">{c.published}</span>
                {c.scheduled > 0 && p.key !== "youtube" && p.key !== "youtube_shorts" && <>
                  <span className="text-gray-600 text-xs">/</span>
                  <span className="text-blue-400 text-xs">{c.scheduled}</span>
                </>}
              </span>
            </button>
          );
        })}
      </div>

      {/* Loading */}
      {isLoading && <div className="text-center py-12 text-gray-500">Loading platform data…</div>}

      {/* Tab content */}
      {!isLoading && activeTab === "youtube" && <YoutubeTable items={items} />}
      {!isLoading && activeTab !== "youtube" && (
        <ShortsTable items={items} platform={activeTab} accent={activePlatform.accent} />
      )}

      {/* Dry-run output */}
      {dryRunOutput && (
        <div className="bg-gray-950 border border-gray-800 rounded-xl p-4">
          <div className="flex items-center justify-between mb-2">
            <h3 className="text-sm font-semibold text-gray-400">Output</h3>
            <button onClick={() => setDryRunOutput("")} className="text-xs text-gray-600 hover:text-gray-400">Clear</button>
          </div>
          <pre className="text-xs text-gray-300 whitespace-pre-wrap font-mono max-h-64 overflow-y-auto">{dryRunOutput}</pre>
        </div>
      )}
    </div>
  );
}
