"use client";

import { FormEvent, useMemo, useState } from "react";

const EXAMPLE_PROMPT = "Explain why learning Dutch can help you feel more confident when speaking with native speakers.";

export type ExamFeedbackResult = {
  prompt: string;
  answer: string;
  summary: string;
  justification: string;
  improvement_suggestions: string[];
  strengths: string[];
  weaknesses: string[];
};

function fallbackFeedback(prompt: string, answer: string): ExamFeedbackResult {
  const safeAnswer = answer.trim();
  const words = safeAnswer ? safeAnswer.split(/\s+/).filter(Boolean).length : 0;
  const sentences = safeAnswer ? safeAnswer.split(/[.!?]+/).filter((part) => part.trim()).length : 0;
  const hasReason = /because|however|therefore|for example|although|in addition/i.test(safeAnswer);
  const hasDetail = /example|such as|because|therefore|for example/i.test(safeAnswer);
  const isStrong = words >= 30 && sentences >= 2 && hasReason && hasDetail;

  if (isStrong) {
    return {
      prompt,
      answer: safeAnswer,
      summary: "This is a strong answer. It already explains the point clearly and gives enough reasoning that no major revision is needed.",
      justification: "The response directly answers the question and supports the point with a clear reason and relevant detail. It is already persuasive and well structured enough that no major fix is required.",
      improvement_suggestions: [],
      strengths: [
        "Your answer clearly addresses the prompt.",
        "It gives a clear reason and supports it with relevant detail.",
        "The argument is easy to follow and reads as convincing.",
      ],
      weaknesses: [],
    };
  }

  return {
    prompt,
    answer: safeAnswer,
    summary: "The response addresses the question and shows a reasonable attempt at justification, but it can be made more specific and persuasive.",
    justification: "The answer is on the right track because it communicates the main point, but the reasoning would be stronger if it included more supporting detail and clearer links between ideas.",
    improvement_suggestions: [
      "Add one specific example that supports your point.",
      "Use linking words such as because, however, and for example to make the reasoning clearer.",
      "Finish with a short conclusion that restates why the answer is convincing.",
    ],
    strengths: [
      "Your answer is trying to address the question directly.",
      words >= 25 ? "It has enough content to show a clear idea." : "A bit more detail would make the reasoning easier to follow.",
    ],
    weaknesses: [
      words < 60 ? "The answer could be expanded with more detail and evidence." : "The main idea is clear, but it could be sharpened further.",
      "A stronger structure would improve the clarity of the justification.",
    ],
  };
}

export function ExamFeedbackForm() {
  const [prompt, setPrompt] = useState(EXAMPLE_PROMPT);
  const [answer, setAnswer] = useState(
    "Learning Dutch can help me speak to native speakers because it improves confidence and makes conversations more natural.",
  );
  const [result, setResult] = useState<ExamFeedbackResult | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const hasAnswer = useMemo(() => answer.trim().length > 0, [answer]);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (!hasAnswer) {
      setError("Add a draft answer before asking for feedback.");
      return;
    }

    setLoading(true);
    setError("");

    try {
      const response = await fetch("/api/backend/exam/feedback", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ prompt, answer }),
      });

      if (!response.ok) {
        throw new Error("Unable to analyze the answer.");
      }

      const data: ExamFeedbackResult = await response.json();
      setResult(data);
    } catch (e) {
      setResult(fallbackFeedback(prompt, answer));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <form onSubmit={handleSubmit} className="card space-y-5 p-6 sm:p-8">
        <div>
          <p className="text-sm font-semibold uppercase tracking-[0.16em] text-brand-700">Writing coach</p>
          <h1 className="mt-2 text-3xl font-bold text-slate-900">Exam justification and improvement feedback</h1>
          <p className="mt-2 text-slate-600">
            Paste a question and your answer. You will only see feedback when something is missing.
          </p>
        </div>

        <label className="block text-sm font-medium text-slate-700">
          Prompt or question
          <textarea
            value={prompt}
            onChange={(event) => setPrompt(event.target.value)}
            rows={4}
            className="mt-2 w-full rounded-xl border border-slate-200 bg-white p-3 text-slate-900 shadow-sm focus:border-brand-400 focus:outline-none focus:ring-2 focus:ring-brand-100"
          />
        </label>

        <label className="block text-sm font-medium text-slate-700">
          Your answer
          <textarea
            value={answer}
            onChange={(event) => setAnswer(event.target.value)}
            rows={8}
            className="mt-2 w-full rounded-xl border border-slate-200 bg-white p-3 text-slate-900 shadow-sm focus:border-brand-400 focus:outline-none focus:ring-2 focus:ring-brand-100"
            placeholder="Write your answer here..."
          />
        </label>

        {error && <p className="text-sm font-medium text-red-600">{error}</p>}

        <div className="flex flex-wrap gap-3">
          <button type="submit" className="btn-primary px-5 py-3" disabled={loading}>
            {loading ? "Analyzing..." : "Get feedback"}
          </button>
          <button
            type="button"
            className="btn-secondary px-5 py-3"
            onClick={() => {
              setPrompt(EXAMPLE_PROMPT);
              setAnswer(
                "Learning Dutch helps me speak with native speakers because it improves my confidence and makes the conversation feel more natural.",
              );
              setResult(null);
              setError("");
            }}
          >
            Load example
          </button>
        </div>
      </form>

      {result && (
        <div className="grid gap-6 lg:grid-cols-3">
          <section className="card p-6 lg:col-span-3">
            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-brand-700">Summary</p>
            <p className="mt-3 text-lg text-slate-700">{result.summary}</p>
          </section>

          <section className="card p-6">
            <h2 className="text-xl font-semibold text-slate-900">Justification</h2>
            <p className="mt-3 text-slate-700">{result.justification}</p>
          </section>

          {result.strengths.length > 0 && (
            <section className="card p-6">
              <h2 className="text-xl font-semibold text-slate-900">What’s strong</h2>
              <ul className="mt-3 space-y-2 text-slate-700">
                {result.strengths.map((item) => (
                  <li key={item} className="flex gap-2">
                    <span className="mt-1 text-brand-700">✓</span>
                    <span>{item}</span>
                  </li>
                ))}
              </ul>
            </section>
          )}

          {result.improvement_suggestions.length > 0 && (
            <section className="card p-6">
              <h2 className="text-xl font-semibold text-slate-900">How to improve</h2>
              <ul className="mt-3 space-y-2 text-slate-700">
                {result.improvement_suggestions.map((item) => (
                  <li key={item} className="flex gap-2">
                    <span className="mt-1 text-brand-700">→</span>
                    <span>{item}</span>
                  </li>
                ))}
              </ul>
            </section>
          )}

          {result.improvement_suggestions.length === 0 && result.weaknesses.length === 0 && (
            <section className="card p-6 lg:col-span-1">
              <h2 className="text-xl font-semibold text-slate-900">Feedback</h2>
              <p className="mt-3 text-slate-700">No major feedback needed — this answer is already strong.</p>
            </section>
          )}
        </div>
      )}
    </div>
  );
}
