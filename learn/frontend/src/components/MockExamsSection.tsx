"use client";
import { useState } from "react";
import Link from "next/link";
import type { MockExamSummary } from "@/lib/types";

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

export function MockExamsSection({ mockExams }: { mockExams: MockExamSummary[] }) {
  const [level, setLevel] = useState<(typeof LEVEL_TABS)[number]>("A2");
  const info = LEVEL_INFO[level];

  return (
    <section>
      <div className="flex items-center justify-center gap-2">
        <h2 className="text-center text-3xl font-bold">Mock Exams</h2>
        <span className="rounded-full bg-amber-100 px-2 py-0.5 text-xs font-semibold text-amber-700">
          Admin preview
        </span>
      </div>
      <p className="mx-auto mt-2 max-w-2xl text-center text-sm text-slate-600">
        Full-length practice exams matching the real Staatsexamen NT2 Programma I — visible
        to admins only while this feature is being built out.
      </p>

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
            const cardBody = (
              <>
                <span className="rounded-full bg-brand-50 px-3 py-1 text-xs font-semibold uppercase text-brand-700">
                  {key}
                </span>
                <h4 className="mt-3 font-semibold">{label}</h4>
                {exams.length > 0 ? (
                  <p className="mt-2 text-sm text-slate-600">
                    {exams.length} practice exam{exams.length > 1 ? "s" : ""} available — click to start
                  </p>
                ) : (
                  <p className="mt-2 text-sm font-medium text-slate-500">Coming soon</p>
                )}
              </>
            );
            return exams.length > 0 ? (
              <Link key={key} href={`/mock-exams/${key}`} className="card block p-5 transition hover:-translate-y-0.5">
                {cardBody}
              </Link>
            ) : (
              <article key={key} className="card p-5">
                {cardBody}
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
