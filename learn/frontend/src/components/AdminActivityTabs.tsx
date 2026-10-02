"use client";

import { Children, useState, type ReactNode } from "react";
import Link from "next/link";
import { formatDate, formatDuration } from "@/lib/format";

type Learner = { user_id: string; name: string | null; email: string | null };
type ExamActivity = Learner & {
  id: number;
  exam_id: string;
  exam_title: string;
  section: string;
  exam_number: number;
  attempt_no: number;
  score: number;
  total: number;
  percent: number;
  label: string;
  status: string;
  activity_at: string;
};
type QuizActivity = Learner & {
  id: number;
  lesson_id: string;
  lesson_title: string;
  course_id: string;
  attempt_no: number;
  score: number;
  total: number;
  activity_at: string;
};
type LessonActivity = Learner & {
  lesson_id: string;
  lesson_title: string;
  course_id: string;
  watched_sec: number;
  last_position_sec: number;
  percent: number;
  completed_at: string | null;
  activity_at: string;
};

export type AdminActivity = {
  practice_exams: ExamActivity[];
  quizzes: QuizActivity[];
  video_lessons: LessonActivity[];
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
          headers={["Learner", "Exam", "Attempt", "Result", "Status", "Date"]}
        >
          {activity.practice_exams.map((row) => (
            <tr key={row.id} className="border-t border-slate-100 align-top">
              <LearnerLink learner={row} />
              <td className="px-5 py-3"><p className="font-medium">{row.exam_title}</p><p className="text-xs capitalize text-slate-500">{row.section} · Exam {row.exam_number}</p></td>
              <td className="px-5 py-3 text-slate-500">#{row.attempt_no}</td>
              <td className="px-5 py-3 tabular-nums">{row.score}/{row.total} ({row.percent}%) <span className="text-slate-500">{row.label}</span></td>
              <td className="px-5 py-3 capitalize text-slate-500">{row.status}</td>
              <td className="px-5 py-3 whitespace-nowrap text-slate-500">{formatDate(row.activity_at)}</td>
            </tr>
          ))}
        </ActivityTable>
      )}

      {active === "quizzes" && (
        <ActivityTable
          empty="No quiz attempts yet."
          headers={["Learner", "Lesson", "Course", "Attempt", "Score", "Date"]}
        >
          {activity.quizzes.map((row) => (
            <tr key={row.id} className="border-t border-slate-100 align-top">
              <LearnerLink learner={row} />
              <td className="px-5 py-3">{row.lesson_title}</td>
              <td className="px-5 py-3 text-slate-500">{row.course_id}</td>
              <td className="px-5 py-3 text-slate-500">#{row.attempt_no}</td>
              <td className="px-5 py-3 tabular-nums">{row.score}/{row.total}</td>
              <td className="px-5 py-3 whitespace-nowrap text-slate-500">{formatDate(row.activity_at)}</td>
            </tr>
          ))}
        </ActivityTable>
      )}

      {active === "video_lessons" && (
        <ActivityTable
          empty="No video lessons have been started yet."
          headers={["Learner", "Lesson", "Course", "Watched", "Progress", "Activity"]}
        >
          {activity.video_lessons.map((row) => (
            <tr key={`${row.user_id}-${row.lesson_id}`} className="border-t border-slate-100 align-top">
              <LearnerLink learner={row} />
              <td className="px-5 py-3">{row.lesson_title}</td>
              <td className="px-5 py-3 text-slate-500">{row.course_id}</td>
              <td className="px-5 py-3 tabular-nums">{formatDuration(row.watched_sec)}</td>
              <td className="px-5 py-3 tabular-nums">{row.percent}%{row.completed_at ? <span className="ml-2 text-xs text-emerald-700">Complete</span> : null}</td>
              <td className="px-5 py-3 whitespace-nowrap text-slate-500">{formatDate(row.activity_at)}</td>
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
