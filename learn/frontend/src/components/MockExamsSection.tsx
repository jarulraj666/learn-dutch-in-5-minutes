"use client";
import { useState } from "react";
import Link from "next/link";
import { formatDate } from "@/lib/format";
import type { MockExamSection, MockExamSummary } from "@/lib/types";
import { PremiumBadge } from "@/components/PremiumBadge";

const LEVEL_TABS = ["A2", "B1", "B2", "C1", "C2"] as const;

// Who each Staatsexamen NT2 level is for, shown as context above the exam grid.
const LEVEL_INFO: Record<(typeof LEVEL_TABS)[number], { title: string; description: string } | null> = {
  A2: {
    title: "Inburgering",
    description:
      "You want a Dutch passport, permanent residence, or EU long-term resident status — A2 Dutch is the standard requirement.",
  },
  B1: {
    title: "Inburgering B1 Staatsexamen NT2 I",
    description:
      "You got a DUO or gemeente letter with a PIP, or you need Dutch for MBO-3, MBO-4, or work.",
  },
  B2: {
    title: "Staatsexamen NT2 II",
    description: "You need Dutch for HBO, university, a master's, or professional work.",
  },
  C1: null,
  C2: null,
};

const SECTIONS: { key: MockExamSummary["section"]; label: string }[] = [
  { key: "reading", label: "Lezen (Reading)" },
  { key: "listening", label: "Luisteren (Listening)" },
  { key: "writing", label: "Schrijven (Writing)" },
  { key: "speaking", label: "Spreken (Speaking)" },
  { key: "knm", label: "KNM (Dutch Society)" },
];

export function MockExamsSection({
  mockExams,
  fullExpiry,
  sectionExpiry,
}: {
  mockExams: MockExamSummary[];
  fullExpiry: string | null;
  sectionExpiry: Partial<Record<MockExamSection, string>>;
}) {
  const [level, setLevel] = useState<(typeof LEVEL_TABS)[number]>("A2");
  const info = LEVEL_INFO[level];

  return (
    <section>
      <div className="flex items-center justify-center gap-2">
        <h2 className="text-center text-3xl font-bold">Inburgering Exams</h2>
      </div>
      <p className="mx-auto mt-2 max-w-2xl text-center text-sm text-slate-600">
        Practice on the same screen you'll see on exam day — the same layout,
        timer and question format as the real Staatsexamen NT2 Programma I. Build confidence before it counts.
      </p>

      <div className="mx-auto mt-6 max-w-3xl rounded-2xl border border-emerald-200 bg-emerald-50 px-5 py-4 text-center sm:px-8">
        <p className="font-semibold text-emerald-950">Try a real-format practice exam before you decide</p>
        <p className="mt-1 text-sm text-emerald-800">
          Start with a free exam in any available section. See how the questions and timer feel, then unlock more practice only if it helps.
        </p>
      </div>

      <div className="mx-auto mt-6 flex max-w-5xl justify-center gap-2">
        {LEVEL_TABS.map((tab) => (
          <button
            key={tab}
            onClick={() => setLevel(tab)}
            className={`rounded-full px-4 py-1.5 text-sm font-semibold transition ${
              level === tab
                ? "bg-brand-700 text-white"
                : "bg-slate-100 text-slate-600 hover:bg-slate-200"
            }`}
          >
            {tab}
          </button>
        ))}
      </div>

      {info && (
        <div className="card mx-auto mt-6 max-w-xl p-5 text-center">
          <h3 className="font-semibold">{info.title}</h3>
          <p className="mt-1 text-sm text-slate-600">{info.description}</p>
        </div>
      )}

      {level === "A2" ? (
        <div className="mx-auto mt-8 grid max-w-5xl gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {SECTIONS.map(({ key, label }) => {
            const exams = mockExams.filter((e) => e.section === key);
            const freeCount = exams.filter((e) => e.is_free_preview).length;
            const premiumCount = exams.length - freeCount;
            const freeExam = exams.find((exam) => exam.is_free_preview);
            const expiry = fullExpiry ?? sectionExpiry[key];
            return (
              <article key={key} className="card flex flex-col p-5 transition hover:-translate-y-0.5 hover:shadow-md">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="rounded-full bg-brand-50 px-3 py-1 text-xs font-semibold uppercase text-brand-700">
                    {key}
                  </span>
                  {freeCount > 0 && (
                    <span className="rounded-full bg-emerald-50 px-3 py-1 text-xs font-semibold text-emerald-700">
                      First exam free
                    </span>
                  )}
                  {premiumCount > 0 && <PremiumBadge label={`+${premiumCount} more`} linkToPricing={false} />}
                </div>
                <h4 className="mt-3 font-semibold">{label}</h4>
                {expiry && <p className="mt-2 text-xs font-semibold text-emerald-700">Expires {formatDate(expiry)}</p>}
                {exams.length > 0 ? (
                  <p className="mt-2 text-sm text-slate-600">
                    {exams.length} practice exam{exams.length > 1 ? "s" : ""} available
                  </p>
                ) : (
                  <p className="mt-2 text-sm font-medium text-slate-500">Coming soon</p>
                )}
                {exams.length > 0 && (
                  <div className="mt-auto flex flex-col items-start gap-2 pt-5">
                    {freeExam ? (
                      <Link href={`/mock-exams/${key}/${freeExam.id}`} className="btn-primary w-full px-5 py-2.5 text-center text-sm">
                        Try a free {key} exam
                      </Link>
                    ) : (
                      <Link href={`/mock-exams/${key}`} className="btn-primary w-full px-5 py-2.5 text-center text-sm">
                        View {key} exams
                      </Link>
                    )}
                    <Link href={`/mock-exams/${key}`} className="text-sm font-semibold text-brand-700 hover:underline">
                      See all exams
                    </Link>
                  </div>
                )}
              </article>
            );
          })}
        </div>
      ) : (
        <div className="mx-auto mt-8 max-w-md text-center">
          <p className="text-sm font-medium text-slate-500">
            {level} mock exams are coming soon.
          </p>
        </div>
      )}
    </section>
  );
}
