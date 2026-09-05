import Link from "next/link";
import { redirect } from "next/navigation";
import { Lock } from "lucide-react";
import { learnerSession } from "@/lib/learner-session";
import { api, ApiError } from "@/lib/api";
import { CheckoutButton } from "@/components/CheckoutButton";
import type { Entitlement, MockExamAttemptSummary, MockExamSection, MockExamSummary } from "@/lib/types";

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

  let entitlements: Entitlement[] = [];
  try {
    entitlements = await api<Entitlement[]>("/api/billing/me");
  } catch {
    // Treat as no active entitlements rather than breaking the page.
  }
  const hasSectionAccess = entitlements.some(
    (e) => e.product === "full" || (e.product === "section" && e.section === section),
  );

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

      {!hasSectionAccess && exams.some((e) => !e.is_free_preview) && (
        <div className="card flex flex-wrap items-center justify-between gap-4 p-5">
          <p className="text-sm text-slate-600">
            Your first exam in this section is free. Unlock the rest of {label} for 3 months.
          </p>
          <div className="flex items-center gap-3">
            <CheckoutButton
              product="section"
              section={section as MockExamSection}
              label="Unlock this section — €9"
              className="btn-primary px-5 py-2 text-sm"
            />
            <Link href="/pricing" className="text-sm font-semibold text-brand-700 hover:underline">
              See all plans
            </Link>
          </div>
        </div>
      )}

      {exams.length === 0 ? (
        <p className="text-slate-500">No exams available yet for this section.</p>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {exams.map((exam, i) => {
            const best = bestAttempts[i];
            const locked = !exam.is_free_preview && !hasSectionAccess;
            return (
              <div key={exam.id} className="card p-5">
                <div className="flex items-center justify-between gap-2">
                  <h3 className="font-semibold">{exam.title}</h3>
                  {locked ? (
                    <span className="inline-flex items-center gap-1 rounded-full bg-brand px-2.5 py-1 text-xs font-semibold text-white">
                      <Lock size={11} />
                      Premium
                    </span>
                  ) : (
                    <span className="rounded-full bg-emerald-50 px-2.5 py-1 text-xs font-semibold text-emerald-700">
                      Free
                    </span>
                  )}
                </div>
                <p className="mt-2 text-sm text-slate-600">
                  {exam.total_questions} questions · {exam.time_limit_minutes} min
                  {exam.pass_threshold != null && ` · pass ${exam.pass_threshold}/${exam.max_score}`}
                </p>
                {best && (
                  <p className="mt-2 text-sm font-medium text-brand-700">
                    Best score: {best.score}/{best.total} ({best.percent}%) — {best.label}
                  </p>
                )}
                {locked ? (
                  <Link href="/pricing" className="btn-secondary mt-4 inline-block px-5 py-2 text-sm">
                    Unlock to start
                  </Link>
                ) : (
                  <Link href={`/mock-exams/${section}/${exam.id}`} className="btn-primary mt-4 inline-block px-5 py-2 text-sm">
                    {best ? "Reattempt" : "Start exam"}
                  </Link>
                )}
                <Link href={`/mock-exams/${section}/${exam.id}/attempts`} className="mt-4 block text-sm font-semibold text-brand-700 hover:underline">
                  View attempts
                </Link>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
