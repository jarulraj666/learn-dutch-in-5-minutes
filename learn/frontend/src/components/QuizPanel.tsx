"use client";

import { useState } from "react";
import clsx from "clsx";
import { CheckCircle2, RotateCcw, XCircle } from "lucide-react";
import type { QuizQuestion, QuizResult } from "@/lib/types";
import { callApi } from "@/lib/format";

type Props = {
  lessonId: string;
  questions: QuizQuestion[];
  signedIn: boolean;
};

export function QuizPanel({ lessonId, questions, signedIn }: Props) {
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [result, setResult] = useState<QuizResult | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (questions.length === 0) {
    return <p className="text-sm text-slate-500">No quiz is available for this lesson yet.</p>;
  }

  if (!signedIn) {
    return (
      <p className="text-sm text-slate-500">
        Sign in to take the quiz and save your score.
      </p>
    );
  }

  const byId = new Map(result?.results.map((r) => [r.id, r]));
  const answeredAll = questions.every((q) => answers[q.id]);

  async function submit() {
    setSubmitting(true);
    setError(null);
    try {
      setResult(await callApi<QuizResult>(`lessons/${lessonId}/quiz/submit`, {
        method: "POST",
        body: JSON.stringify({ answers }),
      }));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not submit the quiz");
    } finally {
      setSubmitting(false);
    }
  }

  function retry() {
    setAnswers({});
    setResult(null);
    setError(null);
  }

  return (
    <div className="space-y-6">
      {result && (
        <div
          className={clsx(
            "rounded-xl border p-4",
            result.percent >= 70
              ? "border-emerald-200 bg-emerald-50 text-emerald-800"
              : "border-amber-200 bg-amber-50 text-amber-800",
          )}
        >
          <p className="text-lg font-semibold">
            {result.score} / {result.total} correct ({result.percent}%)
          </p>
          <p className="mt-1 text-sm">
            {result.percent >= 70
              ? "Passed — you can move on to the next lesson."
              : "You need 70% to pass. Review the explanations and try again."}
          </p>
        </div>
      )}

      {questions.map((question, index) => {
        const outcome = byId.get(question.id);
        return (
          <fieldset key={question.id} className="space-y-2">
            <legend className="text-sm font-semibold">
              {index + 1}. {question.question}
            </legend>
            <div className="grid gap-2">
              {question.options.map((option) => {
                const selected = answers[question.id] === option;
                const isAnswer = outcome && option === outcome.answer;
                const isWrongPick = outcome && selected && !outcome.correct;
                return (
                  <label
                    key={option}
                    className={clsx(
                      "flex cursor-pointer items-center gap-3 rounded-lg border px-3 py-2 text-sm transition",
                      isAnswer && "border-emerald-400 bg-emerald-50",
                      isWrongPick && "border-rose-400 bg-rose-50",
                      !outcome && selected && "border-brand-400 bg-brand-50",
                      !outcome && !selected && "border-slate-200 hover:border-brand-300",
                      outcome && !isAnswer && !isWrongPick && "border-slate-200 opacity-70",
                    )}
                  >
                    <input
                      type="radio"
                      name={question.id}
                      value={option}
                      checked={selected}
                      disabled={Boolean(result)}
                      onChange={() => setAnswers((a) => ({ ...a, [question.id]: option }))}
                      className="accent-brand-600"
                    />
                    <span className="flex-1">{option}</span>
                    {isAnswer && <CheckCircle2 size={16} className="text-emerald-600" />}
                    {isWrongPick && <XCircle size={16} className="text-rose-600" />}
                  </label>
                );
              })}
            </div>
            {outcome?.explanation && (
              <p className="rounded-lg bg-slate-50 px-3 py-2 text-sm text-slate-600">
                {outcome.explanation}
              </p>
            )}
          </fieldset>
        );
      })}

      {error && <p className="text-sm text-rose-600">{error}</p>}

      <div className="flex gap-3">
        {result ? (
          <button onClick={retry} className="btn-secondary">
            <RotateCcw size={16} /> Try again
          </button>
        ) : (
          <button onClick={submit} disabled={!answeredAll || submitting} className="btn-primary">
            {submitting ? "Checking…" : "Check answers"}
          </button>
        )}
      </div>
    </div>
  );
}
