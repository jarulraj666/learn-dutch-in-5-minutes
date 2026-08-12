"use client";
import useSWR from "swr";
import Link from "next/link";
import { apiFetch } from "@/lib/api";
import type { Stats, PipelineJob } from "@/lib/types";
import { StatusBadge } from "@/components/StatusBadge";
import { HealthBanner } from "./HealthBanner";

const fetcher = (url: string) => apiFetch<any>(url);

function StatCard({ label, value, sub }: { label: string; value: number | string; sub?: string }) {
  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl p-5">
      <div className="text-2xl font-bold text-white">{value}</div>
      <div className="text-sm text-gray-400 mt-1">{label}</div>
      {sub && <div className="text-xs text-gray-600 mt-0.5">{sub}</div>}
    </div>
  );
}

export default function DashboardPage() {
  const { data: stats } = useSWR<Stats>("/api/stats", fetcher, { refreshInterval: 15000 });
  const { data: jobs } = useSWR<PipelineJob[]>("/api/pipeline/jobs", fetcher, { refreshInterval: 5000 });

  const activeJobs = jobs?.filter((j) => j.status === "running") ?? [];

  return (
    <div className="space-y-8">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Dashboard</h1>
        <Link
          href="/run"
          className="bg-sky-600 hover:bg-sky-500 text-white px-4 py-2 rounded-lg text-sm font-medium"
        >
          + Run Pipeline
        </Link>
      </div>

      <HealthBanner />

      {/* Stats grid */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard label="Total Topics" value={stats?.total ?? "—"} />
        <StatCard label="Pending" value={stats?.by_status?.pending ?? "—"} sub="not yet generated" />
        <StatCard label="Generated" value={stats?.by_status?.generated ?? "—"} sub="ready to upload" />
        <StatCard label="Done" value={stats?.by_status?.done ?? "—"} sub="live on YouTube" />
      </div>

      {/* Active jobs */}
      {activeJobs.length > 0 && (
        <section>
          <h2 className="text-lg font-semibold mb-3">Active Pipeline Jobs</h2>
          <div className="space-y-2">
            {activeJobs.map((job) => (
              <Link
                key={job.job_id}
                href={`/run?job=${job.job_id}`}
                className="flex items-center justify-between bg-blue-900/30 border border-blue-700/40 rounded-lg px-4 py-3 hover:bg-blue-900/50 transition"
              >
                <span className="text-sm text-blue-200 font-mono">{job.args.slice(2).join(" ")}</span>
                <span className="text-xs text-blue-400">{job.started_at}</span>
              </Link>
            ))}
          </div>
        </section>
      )}

      {/* By level + category */}
      <div className="grid grid-cols-2 gap-6">
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-5">
          <h3 className="text-sm font-semibold text-gray-400 uppercase tracking-wide mb-3">By Level</h3>
          {Object.entries(stats?.by_level ?? {}).map(([lvl, cnt]) => (
            <div key={lvl} className="flex justify-between py-1 text-sm">
              <span className="text-gray-300">{lvl}</span>
              <span className="text-white font-medium">{cnt as number}</span>
            </div>
          ))}
        </div>
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-5">
          <h3 className="text-sm font-semibold text-gray-400 uppercase tracking-wide mb-3">By Category</h3>
          {Object.entries(stats?.by_category ?? {}).map(([cat, cnt]) => (
            <div key={cat} className="flex justify-between py-1 text-sm">
              <span className="text-gray-300">{cat.replace("_", " ")}</span>
              <span className="text-white font-medium">{cnt as number}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Recent activity */}
      <section>
        <h2 className="text-lg font-semibold mb-3">Recent Activity</h2>
        <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-800">
                <th className="text-left px-4 py-2.5 text-gray-400 font-medium">Topic</th>
                <th className="text-left px-4 py-2.5 text-gray-400 font-medium">Level</th>
                <th className="text-left px-4 py-2.5 text-gray-400 font-medium">Category</th>
                <th className="text-left px-4 py-2.5 text-gray-400 font-medium">Status</th>
                <th className="text-left px-4 py-2.5 text-gray-400 font-medium">YouTube</th>
              </tr>
            </thead>
            <tbody>
              {stats?.recent.map((t) => (
                <tr key={t.id} className="border-b border-gray-800/50 hover:bg-gray-800/30">
                  <td className="px-4 py-2.5">
                    <Link href={`/topics/${t.id}`} className="text-sky-400 hover:underline">
                      {t.title_hint}
                    </Link>
                  </td>
                  <td className="px-4 py-2.5 text-gray-400">{t.level}</td>
                  <td className="px-4 py-2.5 text-gray-400">{t.category}</td>
                  <td className="px-4 py-2.5">
                    <StatusBadge status={t.status} />
                  </td>
                  <td className="px-4 py-2.5">
                    {t.youtube_video_id ? (
                      <a
                        href={`https://youtube.com/watch?v=${t.youtube_video_id}`}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-red-400 hover:underline text-xs"
                      >
                        ▶ Watch
                      </a>
                    ) : (
                      <span className="text-gray-600">—</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
