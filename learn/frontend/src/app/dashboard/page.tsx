import Link from "next/link";
import { redirect } from "next/navigation";
import { ClipboardCheck, Layers } from "lucide-react";
import { learnerSession } from "@/lib/learner-session";
import { api } from "@/lib/api";
import { formatDate } from "@/lib/format";
import type { Dashboard, MockExamAttemptSummary, MockExamSummary } from "@/lib/types";

export const metadata = { title: "My learning · Learn Dutch in 5 Minutes" };

export default async function DashboardPage() {
  const session = await learnerSession();
  if (!session?.user) redirect("/signin");

  const data = await api<Dashboard>("/api/me/dashboard");
  let mockExams: MockExamSummary[] = [];
  try {
    mockExams = await api<MockExamSummary[]>("/api/mock-exams");
  } catch {
    // Keep the dashboard usable if mock-exam data is temporarily unavailable.
  }
  const latestMockAttempt = (
    await Promise.all(
      mockExams.map(async (exam) => {
        try {
          const attempts = await api<MockExamAttemptSummary[]>(`/api/mock-exams/${exam.id}/attempts`);
          const latest = attempts.reduce<MockExamAttemptSummary | null>(
            (current, attempt) => (!current || attempt.created_at > current.created_at ? attempt : current),
            null,
          );
          return latest ? { exam, attempt: latest } : null;
        } catch {
          return null;
        }
      }),
    )
  )
    .filter((item): item is { exam: MockExamSummary; attempt: MockExamAttemptSummary } => item !== null)
    .sort((a, b) => b.attempt.created_at.localeCompare(a.attempt.created_at))[0] ?? null;

  return (
    <div className="space-y-8">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold">My learning</h1>
          <p className="mt-1 text-slate-600">Welcome back, {session.user.name ?? "learner"}.</p>
        </div>
        <Link href="/flashcards" className="btn-secondary">
          <Layers size={16} />
          {data.flashcards_due} flashcards due
        </Link>
      </header>

      <div className="grid gap-6 md:grid-cols-2">
        {data.courses.map((course) => (
          <article key={course.course_id} className="card p-6">
            <h2 className="text-lg font-semibold">{course.title}</h2>
            <div className="mt-4 h-2 overflow-hidden rounded-full bg-slate-200">
              <div className="h-full rounded-full bg-brand" style={{ width: `${course.percent}%` }} />
            </div>
            <p className="mt-2 text-sm text-slate-500">
              {course.lessons_completed} of {course.lessons_total} core lessons · {course.percent}%
            </p>
            {course.optional_total > 0 && (
              <p className="mt-0.5 text-xs text-slate-400">
                Optional dialogue: {course.optional_completed} of {course.optional_total}
              </p>
            )}
            <div className="mt-4 flex flex-wrap gap-3">
              {course.resume_lesson_id ? (
                <Link
                  href={`/courses/${course.course_id}/lessons/${course.resume_lesson_id}`}
                  className="btn-primary px-5 py-2 text-sm"
                >
                  Continue: {course.resume_lesson_title}
                </Link>
              ) : (
                <Link
                  href={`/courses/${course.course_id}/certificate`}
                  className="btn-primary px-5 py-2 text-sm"
                >
                  Claim your certificate
                </Link>
              )}
              <Link href={`/courses/${course.course_id}`} className="btn-secondary text-sm">
                Course content
              </Link>
            </div>
          </article>
        ))}
      </div>

      <section className="card flex flex-wrap items-center justify-between gap-5 p-6">
        <div className="flex items-start gap-4">
          <span className="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-brand-50 text-brand-700">
            <ClipboardCheck size={21} />
          </span>
          <div>
            <h2 className="text-lg font-semibold">Mock exam practice</h2>
            {latestMockAttempt ? (
              <p className="mt-1 text-sm text-slate-600">
                Continue {latestMockAttempt.exam.title} · last result {latestMockAttempt.attempt.score}/{latestMockAttempt.attempt.total} ({latestMockAttempt.attempt.percent}%) · {formatDate(latestMockAttempt.attempt.created_at)}
              </p>
            ) : (
              <p className="mt-1 text-sm text-slate-600">Start a practice exam and track your results here.</p>
            )}
          </div>
        </div>
        <Link href={latestMockAttempt ? `/mock-exams/${latestMockAttempt.exam.section}` : "/#mock-exams"} className="btn-primary px-5 py-2 text-sm">
          {latestMockAttempt ? "Continue exam practice" : "Browse mock exams"}
        </Link>
      </section>

      {data.recent.length > 0 && (
        <section className="card overflow-hidden">
          <h2 className="border-b border-slate-200 px-5 py-3 font-semibold">Recent activity</h2>
          <ul className="divide-y divide-slate-100">
            {data.recent.map((item) => (
              <li key={item.lesson_id}>
                <Link
                  href={`/courses/${item.course_id}/lessons/${item.lesson_id}`}
                  className="flex items-center gap-4 px-5 py-3 text-sm hover:bg-slate-50"
                >
                  <span className="min-w-0 flex-1 truncate">{item.title}</span>
                  <span className="text-slate-400">{formatDate(item.updated_at)}</span>
                  <span className="w-12 text-right tabular-nums text-slate-500">
                    {item.percent}%
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
