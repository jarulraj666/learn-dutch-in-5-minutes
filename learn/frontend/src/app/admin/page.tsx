import Link from "next/link";
import { redirect } from "next/navigation";
import { learnerSession } from "@/lib/learner-session";
import { api, ApiError } from "@/lib/api";
import { formatDate } from "@/lib/format";
import type { AdminAnonymousMockExamAttemptList, AdminLearner } from "@/lib/types";
import { AdminActivityTabs, type AdminActivity } from "@/components/AdminActivityTabs";

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
  let activity: AdminActivity;
  let anonymousAttempts: AdminAnonymousMockExamAttemptList;
  try {
    [stats, learners, activity, anonymousAttempts] = await Promise.all([
      api<Stats>("/api/admin/stats"),
      api<AdminLearner[]>("/api/admin/learners"),
      api<AdminActivity>("/api/admin/activity"),
      api<AdminAnonymousMockExamAttemptList>("/api/admin/anonymous-mock-exams?limit=100"),
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
        <div className="flex gap-2">
          <Link href="/admin/feedback" className="btn-secondary text-sm">
            Review feedback
          </Link>
        </div>
      </div>

      <div className="grid gap-4 sm:grid-cols-3 lg:grid-cols-6">
        <Stat label="Learners" value={stats.learners} />
        <Stat label="New (7d)" value={stats.learners_new_7d} />
        <Stat label="Lessons" value={stats.lessons} />
        <Stat label="Completions" value={stats.lessons_completed} />
        <Stat label="Quiz attempts" value={stats.quiz_attempts} />
        <Stat label="Certificates" value={stats.certificates} />
      </div>

      <AdminActivityTabs activity={activity} />

      <section className="card overflow-hidden">
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-200 px-5 py-3">
          <h2 className="font-semibold">Anonymous practice exam attempts</h2>
          <span className="rounded-full bg-slate-100 px-3 py-1 text-xs font-semibold text-slate-600">
            {anonymousAttempts.total_count} total
          </span>
        </div>
        <p className="px-5 pt-3 text-xs text-slate-500">
          Guest attempts are not linked to an account. Only exam, score and submission time are retained; answers are not stored.
        </p>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[42rem] text-sm">
            <thead>
              <tr className="text-left text-xs uppercase tracking-wide text-slate-400">
                <th className="px-5 py-2">Exam</th>
                <th className="px-5 py-2">Section</th>
                <th className="px-5 py-2">Score</th>
                <th className="px-5 py-2">Result</th>
                <th className="px-5 py-2">Submitted</th>
              </tr>
            </thead>
            <tbody>
              {anonymousAttempts.attempts.map((attempt) => (
                <tr key={attempt.id} className="border-t border-slate-100 hover:bg-slate-50">
                  <td className="px-5 py-3 font-medium">{attempt.title}</td>
                  <td className="px-5 py-3 capitalize text-slate-600">{attempt.section}</td>
                  <td className="px-5 py-3 tabular-nums">{attempt.score}/{attempt.total} ({attempt.percent}%)</td>
                  <td className="px-5 py-3">{attempt.label}</td>
                  <td className="px-5 py-3 text-slate-500">{formatDate(attempt.created_at)}</td>
                </tr>
              ))}
              {anonymousAttempts.attempts.length === 0 && (
                <tr><td colSpan={5} className="px-5 py-8 text-center text-slate-500">No anonymous exam attempts yet.</td></tr>
              )}
            </tbody>
          </table>
        </div>
        {anonymousAttempts.total_count > anonymousAttempts.attempts.length && (
          <p className="border-t border-slate-100 px-5 py-3 text-xs text-slate-500">
            Showing the latest {anonymousAttempts.attempts.length} attempts.
          </p>
        )}
      </section>

      <section className="card overflow-hidden">
        <h2 className="border-b border-slate-200 px-5 py-3 font-semibold">Learners</h2>
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-xs uppercase tracking-wide text-slate-400">
              <th className="px-5 py-2">Name</th>
              <th className="px-5 py-2">Email</th>
              <th className="px-5 py-2">Completed</th>
              <th className="px-5 py-2">Attempts</th>
              <th className="px-5 py-2">Mock exams</th>
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
                <td className="px-5 py-2 tabular-nums">{learner.mock_exam_attempts}</td>
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
