import Link from "next/link";
import { redirect } from "next/navigation";
import { learnerSession } from "@/lib/learner-session";
import { api } from "@/lib/api";
import { formatDate } from "@/lib/format";
import type { MockExamAttemptSummary } from "@/lib/types";

export default async function MockExamAttemptsPage({
  params,
}: {
  params: { section: string; examId: string };
}) {
  const session = await learnerSession();
  if (!session?.user) redirect("/signin");

  const attempts = await api<MockExamAttemptSummary[]>(`/api/mock-exams/${params.examId}/attempts`);
  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <div>
        <Link href={`/mock-exams/${params.section}`} className="text-sm text-brand-700 hover:underline">← Back to exams</Link>
        <h1 className="mt-2 text-3xl font-bold">Previous attempts</h1>
      </div>
      {attempts.length === 0 ? (
        <p className="text-slate-600">You have not completed this exam yet.</p>
      ) : (
        <div className="divide-y divide-slate-200 border border-slate-200 bg-white">
          {attempts.map((attempt) => (
            <Link key={attempt.attempt_no} href={`/mock-exams/${params.section}/${params.examId}/attempts/${attempt.attempt_no}`} className="flex items-center justify-between gap-4 px-5 py-4 transition hover:bg-slate-50">
              <div>
                <p className="font-semibold text-slate-900">Attempt #{attempt.attempt_no}</p>
                <p className="mt-1 text-sm text-slate-600">{formatDate(attempt.created_at)}</p>
              </div>
              <div className="text-right">
                <p className="font-semibold text-brand-700">{attempt.label}</p>
                <p className="mt-1 text-sm text-slate-600">{attempt.score}/{attempt.total} practice points ({attempt.percent}%)</p>
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}