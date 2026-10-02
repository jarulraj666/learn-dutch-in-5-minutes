"use client";

import { Children, useState, type ReactNode } from "react";
import Link from "next/link";

type Learner = { user_id: string; name: string | null; email: string | null };
export type AdminActivity = {
  practice_exams: Learner[];
  quizzes: Learner[];
  video_lessons: Learner[];
};

type Tab = "practice_exams" | "quizzes" | "video_lessons";

const TABS: { id: Tab; label: string }[] = [
  { id: "practice_exams", label: "Practice exams" },
  { id: "quizzes", label: "Quizzes" },
  { id: "video_lessons", label: "Video lessons" },
];

function LearnerLink({ learner }: { learner: Learner }) {
  return (
    <td className="px-5 py-3">
      <Link href={`/admin/learners/${learner.user_id}`} className="font-medium text-brand-700 hover:underline">
        {learner.name || learner.email || "Learner"}
      </Link>
      {learner.name && <p className="text-xs text-slate-500">{learner.email || "—"}</p>}
    </td>
  );
}

export function AdminActivityTabs({ activity }: { activity: AdminActivity }) {
  const [active, setActive] = useState<Tab>("practice_exams");
  const counts: Record<Tab, number> = {
    practice_exams: activity.practice_exams.length,
    quizzes: activity.quizzes.length,
    video_lessons: activity.video_lessons.length,
  };

  return (
    <section className="card overflow-hidden">
      <div className="border-b border-slate-200 px-5 pt-4">
        <h2 className="font-semibold">Learner activity</h2>
        <div className="mt-3 flex gap-5 overflow-x-auto" role="tablist" aria-label="Learner activity categories">
          {TABS.map((tab) => (
            <button
              key={tab.id}
              type="button"
              role="tab"
              aria-selected={active === tab.id}
              onClick={() => setActive(tab.id)}
              className={`whitespace-nowrap border-b-2 pb-3 text-sm font-medium transition ${
                active === tab.id
                  ? "border-brand-600 text-brand-700"
                  : "border-transparent text-slate-500 hover:text-slate-800"
              }`}
            >
              {tab.label}<span className="ml-2 rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-600">{counts[tab.id]}</span>
            </button>
          ))}
        </div>
      </div>

      {active === "practice_exams" && (
        <ActivityTable
          empty="No practice exam attempts yet."
          headers={["Learners who took a practice exam"]}
        >
          {activity.practice_exams.map((learner) => (
            <tr key={learner.user_id} className="border-t border-slate-100">
              <LearnerLink learner={learner} />
            </tr>
          ))}
        </ActivityTable>
      )}

      {active === "quizzes" && (
        <ActivityTable
          empty="No quiz attempts yet."
          headers={["Learners who took a quiz"]}
        >
          {activity.quizzes.map((learner) => (
            <tr key={learner.user_id} className="border-t border-slate-100">
              <LearnerLink learner={learner} />
            </tr>
          ))}
        </ActivityTable>
      )}

      {active === "video_lessons" && (
        <ActivityTable
          empty="No video lessons have been started yet."
          headers={["Learners who watched a video lesson"]}
        >
          {activity.video_lessons.map((learner) => (
            <tr key={learner.user_id} className="border-t border-slate-100">
              <LearnerLink learner={learner} />
            </tr>
          ))}
        </ActivityTable>
      )}
    </section>
  );
}

function ActivityTable({
  headers,
  empty,
  children,
}: {
  headers: string[];
  empty: string;
  children: ReactNode;
}) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[48rem] text-sm">
        <thead>
          <tr className="text-left text-xs uppercase tracking-wide text-slate-400">
            {headers.map((header) => <th key={header} className="px-5 py-2">{header}</th>)}
          </tr>
        </thead>
        <tbody>
          {Children.count(children) > 0
            ? children
            : <tr><td colSpan={headers.length} className="px-5 py-8 text-center text-slate-500">{empty}</td></tr>}
        </tbody>
      </table>
    </div>
  );
}
