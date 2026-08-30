import Link from "next/link";
import { redirect } from "next/navigation";
import { learnerSession } from "@/lib/learner-session";
import { api, ApiError } from "@/lib/api";
import { formatDate } from "@/lib/format";
import type { AdminLearner } from "@/lib/types";

export const metadata = { title: "Admin · Learn Dutch in 5 Minutes" };

type Stats = {
  learners: number;
  learners_new_7d: number;
  lessons: number;
  lessons_completed: number;
  quiz_attempts: number;
  certificates: number;
};

export default async function AdminPage() {
  const session = await learnerSession();
  if (!session?.user) redirect("/signin");

  let stats: Stats;
  let learners: AdminLearner[];
  try {
    [stats, learners] = await Promise.all([
      api<Stats>("/api/admin/stats"),
      api<AdminLearner[]>("/api/admin/learners"),
    ]);
  } catch (error) {
    if (error instanceof ApiError && error.status === 403) {
      return <p className="text-slate-600">You do not have access to this page.</p>;
    }
    throw error;
  }

  return (
    <div className="space-y-8">
      <div className="flex items-center justify-between">
        <h1 className="text-3xl font-bold">Admin</h1>
        <Link href="/admin/feedback" className="btn-secondary text-sm">
          Review feedback
        </Link>
      </div>

      <div className="grid gap-4 sm:grid-cols-3 lg:grid-cols-6">
        <Stat label="Learners" value={stats.learners} />
        <Stat label="New (7d)" value={stats.learners_new_7d} />
        <Stat label="Lessons" value={stats.lessons} />
        <Stat label="Completions" value={stats.lessons_completed} />
        <Stat label="Quiz attempts" value={stats.quiz_attempts} />
        <Stat label="Certificates" value={stats.certificates} />
      </div>

      <section className="card overflow-hidden">
        <h2 className="border-b border-slate-200 px-5 py-3 font-semibold">Learners</h2>
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-xs uppercase tracking-wide text-slate-400">
              <th className="px-5 py-2">Name</th>
              <th className="px-5 py-2">Email</th>
              <th className="px-5 py-2">Completed</th>
              <th className="px-5 py-2">Attempts</th>
              <th className="px-5 py-2">Last active</th>
            </tr>
          </thead>
          <tbody>
            {learners.map((learner) => (
              <tr key={learner.id} className="border-t border-slate-100 hover:bg-slate-50">
                <td className="px-5 py-2">
                  <Link href={`/admin/learners/${learner.id}`} className="text-brand-700">
                    {learner.name ?? "—"}
                  </Link>
                </td>
                <td className="px-5 py-2 text-slate-600">{learner.email ?? "—"}</td>
                <td className="px-5 py-2 tabular-nums">{learner.lessons_completed}</td>
                <td className="px-5 py-2 tabular-nums">{learner.quiz_attempts}</td>
                <td className="px-5 py-2 text-slate-500">{formatDate(learner.last_active)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div className="card p-4">
      <p className="text-2xl font-bold">{value}</p>
      <p className="text-xs uppercase tracking-wide text-slate-400">{label}</p>
    </div>
  );
}
