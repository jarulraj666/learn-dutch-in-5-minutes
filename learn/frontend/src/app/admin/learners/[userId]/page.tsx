import Link from "next/link";
import { redirect } from "next/navigation";
import { learnerSession } from "@/lib/learner-session";
import { api, ApiError } from "@/lib/api";
import { formatDate } from "@/lib/format";

type LearnerDetail = {
  user: { id: string; email: string | null; name: string | null; plan: string; role: string; created_at: string };
  progress: Array<{
    lesson_id: string;
    title: string;
    course_id: string;
    percent: number;
    completed_at: string | null;
    updated_at: string;
  }>;
  quiz_attempts: Array<{
    lesson_id: string;
    attempt_no: number;
    score: number;
    total: number;
    created_at: string;
  }>;
  certificates: Array<{ serial: string; course_id: string; issued_at: string }>;
};

export default async function LearnerDetailPage({ params }: { params: { userId: string } }) {
  const session = await learnerSession();
  if (!session?.user) redirect("/signin");

  let data: LearnerDetail;
  try {
    data = await api<LearnerDetail>(`/api/admin/learners/${params.userId}`);
  } catch (error) {
    if (error instanceof ApiError && error.status === 403) {
      return <p className="text-slate-600">You do not have access to this page.</p>;
    }
    throw error;
  }

  return (
    <div className="space-y-8">
      <Link href="/admin" className="text-sm text-slate-500 hover:text-brand-700">
        ← All learners
      </Link>

      <header>
        <h1 className="text-2xl font-bold">{data.user.name ?? "Learner"}</h1>
        <p className="text-sm text-slate-500">
          {data.user.email} · joined {formatDate(data.user.created_at)} · {data.user.plan} plan
        </p>
      </header>

      <section className="card overflow-hidden">
        <h2 className="border-b border-slate-200 px-5 py-3 font-semibold">Lesson progress</h2>
        <table className="w-full text-sm">
          <tbody>
            {data.progress.map((row) => (
              <tr key={row.lesson_id} className="border-t border-slate-100">
                <td className="px-5 py-2">{row.title}</td>
                <td className="px-5 py-2 tabular-nums text-slate-500">{row.percent}%</td>
                <td className="px-5 py-2 text-slate-500">
                  {row.completed_at ? `Completed ${formatDate(row.completed_at)}` : "In progress"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section className="card overflow-hidden">
        <h2 className="border-b border-slate-200 px-5 py-3 font-semibold">Quiz attempts</h2>
        <table className="w-full text-sm">
          <tbody>
            {data.quiz_attempts.map((row) => (
              <tr key={`${row.lesson_id}-${row.attempt_no}`} className="border-t border-slate-100">
                <td className="px-5 py-2">{row.lesson_id}</td>
                <td className="px-5 py-2 text-slate-500">Attempt {row.attempt_no}</td>
                <td className="px-5 py-2 tabular-nums">
                  {row.score}/{row.total}
                </td>
                <td className="px-5 py-2 text-slate-500">{formatDate(row.created_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  );
}
