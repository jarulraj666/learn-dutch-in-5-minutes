import Link from "next/link";
import { redirect } from "next/navigation";
import { learnerSession } from "@/lib/learner-session";
import { api, ApiError } from "@/lib/api";
import type { MockExamAttemptSummary, MockExamSummary } from "@/lib/types";

const SECTION_LABELS: Record<string, string> = {
  reading: "Lezen (Reading)",
  listening: "Luisteren (Listening)",
  writing: "Schrijven (Writing)",
  speaking: "Spreken (Speaking)",
  knm: "KNM (Dutch Society)",
};

export default async function MockExamSectionPage({ params }: { params: { section: string } }) {
  const session = await learnerSession();
  if (!session?.user) redirect("/signin");

  const { section } = params;
  const label = SECTION_LABELS[section] ?? section;

  let exams: MockExamSummary[] = [];
  try {
    exams = await api<MockExamSummary[]>(`/api/mock-exams?section=${encodeURIComponent(section)}`);
  } catch (error) {
    if (error instanceof ApiError && error.status === 403) {
      return <p className="text-slate-600">You do not have access to this page.</p>;
    }
    throw error;
  }

  const bestAttempts = await Promise.all(
    exams.map(async (exam) => {
      try {
        const attempts = await api<MockExamAttemptSummary[]>(`/api/mock-exams/${exam.id}/attempts`);
        return attempts.reduce<MockExamAttemptSummary | null>(
          (best, a) => (!best || a.percent > best.percent ? a : best),
          null,
        );
      } catch {
        return null;
      }
    }),
  );

  return (
    <div className="space-y-6">
      <div>
        <Link href="/" className="text-sm text-brand-700 hover:underline">
          ← Back
        </Link>
        <h1 className="mt-2 text-3xl font-bold">{label}</h1>
        <p className="mt-1 text-slate-600">Choose a practice exam to start.</p>
      </div>

      {exams.length === 0 ? (
        <p className="text-slate-500">No exams available yet for this section.</p>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {exams.map((exam, i) => {
            const best = bestAttempts[i];
            return (
              <Link
                key={exam.id}
                href={`/mock-exams/${section}/${exam.id}`}
                className="card block p-5 transition hover:-translate-y-0.5"
              >
                <h3 className="font-semibold">{exam.title}</h3>
                <p className="mt-2 text-sm text-slate-600">
                  {exam.total_questions} questions · {exam.time_limit_minutes} min
                  {exam.pass_threshold != null && ` · pass ${exam.pass_threshold}/${exam.max_score}`}
                </p>
                {best && (
                  <p className="mt-2 text-sm font-medium text-brand-700">
                    Best score: {best.score}/{best.total} ({best.percent}%) — {best.label}
                  </p>
                )}
                <span className="btn-primary mt-4 inline-block px-5 py-2 text-sm">
                  {best ? "Reattempt" : "Start exam"}
                </span>
              </Link>
            );
          })}
        </div>
      )}
    </div>
  );
}
