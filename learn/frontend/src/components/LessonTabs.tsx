"use client";

import { useState } from "react";
import clsx from "clsx";
import type { LessonDetail } from "@/lib/types";
import { QuizPanel } from "./QuizPanel";

const TABS = ["overview", "vocabulary", "grammar", "transcript", "quiz"] as const;
type Tab = (typeof TABS)[number];

const LABELS: Record<Tab, string> = {
  overview: "Overview",
  vocabulary: "Vocabulary",
  grammar: "Grammar",
  transcript: "Transcript",
  quiz: "Quiz",
};

export function LessonTabs({ lesson, signedIn }: { lesson: LessonDetail; signedIn: boolean }) {
  const [tab, setTab] = useState<Tab>("overview");
  const [showEnglish, setShowEnglish] = useState(true);

  const counts: Partial<Record<Tab, number>> = {
    vocabulary: lesson.vocabulary.length,
    grammar: lesson.grammar_notes.length,
    quiz: lesson.quiz.length,
  };

  return (
    <div className="card mt-6">
      <div className="flex gap-1 overflow-x-auto border-b border-slate-200 px-2">
        {TABS.map((key) => (
          <button
            key={key}
            onClick={() => setTab(key)}
            className={clsx(
              "whitespace-nowrap border-b-2 px-4 py-3 text-sm font-medium transition",
              tab === key
                ? "border-brand-600 text-brand-700"
                : "border-transparent text-slate-500 hover:text-slate-800",
            )}
          >
            {LABELS[key]}
            {counts[key] ? (
              <span className="ml-2 rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-500">
                {counts[key]}
              </span>
            ) : null}
          </button>
        ))}
      </div>

      <div className="p-5">
        {tab === "overview" && (
          <div className="space-y-6">
            {lesson.key_phrases.length > 0 && (
              <section>
                <h3 className="mb-2 text-sm font-semibold uppercase tracking-wide text-slate-500">
                  Key phrases
                </h3>
                <ul className="grid gap-2 sm:grid-cols-2">
                  {lesson.key_phrases.map((phrase) => (
                    <li
                      key={phrase}
                      className="rounded-lg border border-slate-200 px-3 py-2 text-sm"
                    >
                      {phrase}
                    </li>
                  ))}
                </ul>
              </section>
            )}
            <section>
              <h3 className="mb-2 text-sm font-semibold uppercase tracking-wide text-slate-500">
                About this lesson
              </h3>
              <p className="whitespace-pre-wrap text-sm leading-relaxed text-slate-700">
                {lesson.description || lesson.summary || "No description available."}
              </p>
            </section>
          </div>
        )}

        {tab === "vocabulary" && (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs uppercase tracking-wide text-slate-400">
                <th className="pb-2">Dutch</th>
                <th className="pb-2">English</th>
              </tr>
            </thead>
            <tbody>
              {lesson.vocabulary.map((item) => (
                <tr key={item.id} className="border-t border-slate-100">
                  <td className="py-2 pr-4 font-medium">{item.nl}</td>
                  <td className="py-2 text-slate-600">{item.en}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

        {tab === "grammar" && (
          <div className="space-y-5">
            {lesson.grammar_notes.length === 0 && (
              <p className="text-sm text-slate-500">No grammar notes for this lesson.</p>
            )}
            {lesson.grammar_notes.map((note) => (
              <article key={note.title}>
                <h3 className="font-semibold">{note.title}</h3>
                <p className="mt-1 text-sm text-slate-700">{note.explanation}</p>
                {note.examples.length > 0 && (
                  <ul className="mt-2 space-y-1">
                    {note.examples.map((example) => (
                      <li
                        key={example}
                        className="rounded-md bg-brand-50 px-3 py-1.5 text-sm text-brand-900"
                      >
                        {example}
                      </li>
                    ))}
                  </ul>
                )}
              </article>
            ))}
          </div>
        )}

        {tab === "transcript" && (
          <div>
            <label className="mb-3 flex items-center gap-2 text-sm text-slate-600">
              <input
                type="checkbox"
                checked={showEnglish}
                onChange={(e) => setShowEnglish(e.target.checked)}
                className="accent-brand-600"
              />
              Show English translation
            </label>
            <ol className="space-y-2">
              {lesson.transcript.map((line, index) => (
                <li key={index} className="rounded-lg border border-slate-100 px-3 py-2 text-sm">
                  <span className="mr-2 text-xs font-semibold uppercase text-brand-600">
                    {line.speaker}
                  </span>
                  <span>{line.line_nl}</span>
                  {showEnglish && line.line_en && (
                    <span className="mt-0.5 block text-slate-500">{line.line_en}</span>
                  )}
                </li>
              ))}
            </ol>
          </div>
        )}

        {tab === "quiz" && (
          <QuizPanel lessonId={lesson.id} questions={lesson.quiz} signedIn={signedIn} />
        )}
      </div>
    </div>
  );
}
