"use client";
import { useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import clsx from "clsx";
import { Bookmark, Grid2X2, LoaderCircle } from "lucide-react";
import { callApi, formatDate } from "@/lib/format";
import { PassageContent } from "./PassageContent";
import { ListeningExam } from "./ListeningExam";
import { KnmExam } from "./KnmExam";
import { ReadingExam } from "./ReadingExam";
import { SpeakingExam as SpeakingExamComponent } from "./SpeakingExam";
import { WritingExam } from "./WritingExam";
import { TimeUpDialog, ExamFooter, ExamHeader, IntroBody, IntroHeading, IntroLayout, IntroNote, IntroSidePanel, QuestionPicker } from "./DuoExamChrome";
import type {
  MockExamAttemptResult,
  MockExamAttemptSummary,
  MockExamTakeDetail,
} from "@/lib/types";

// Colors match the official DUO/Optimum Assessment exam player exactly (navy header/footer, orange accent).
const NAVY = "bg-[#2b4a78]";
const ORANGE = "bg-[#e8863c] hover:bg-[#dc7a30]";


function mediaProxyUrl(type: "image" | "audio" | "video", path: string): string {
  if (path.startsWith("https://") || path.startsWith("http://")) return path;
  return `/api/backend/mock-exams/media/${type}?path=${encodeURIComponent(path)}`;
}

function readingDisplayPrompt(passage: MockExamTakeDetail["passages"][number]): string {
  if (passage.display_prompt_nl?.trim()) return passage.display_prompt_nl;
  return "Lees eerst de vraag.\nLees daarna de tekst.";
}

/** Reading texts start with a one-line situation, which the DUO player shows above the rule. */
function splitReadingIntro(passage: MockExamTakeDetail["passages"][number]): { intro: string; body: string } {
  const paragraphs = (passage.content_nl ?? "").split(/\n\s*\n/);
  let intro = "";
  if (paragraphs.length > 1 && paragraphs[0].trim().length <= 140 && !paragraphs[0].trim().includes("\n")) {
    intro = paragraphs.shift()!.trim();
  }
  // The text often repeats its own title as the first line; it is already rendered above.
  const title = passage.title?.trim().toLowerCase();
  if (title && paragraphs[0]?.trim().toLowerCase() === title) paragraphs.shift();
  return { intro, body: paragraphs.join("\n\n") };
}

function PassageMedia({ mediaUrls }: { mediaUrls: { type: string; url: string }[] }) {
  if (mediaUrls.length === 0) return null;
  return (
    <div className="mb-3 space-y-3">
      {mediaUrls.map((m) => (
        <div key={m.url}>
          {m.type === "image" && (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={mediaProxyUrl("image", m.url)} alt="" className="max-h-64 rounded-lg border border-slate-200" />
          )}
          {m.type === "audio" && <audio controls className="w-full" src={mediaProxyUrl("audio", m.url)} />}
          {m.type === "video" && (
            <video controls className="max-h-64 w-full rounded-lg" src={mediaProxyUrl("video", m.url)} />
          )}
        </div>
      ))}
    </div>
  );
}

function ResultView({
  exam,
  result,
}: {
  exam: MockExamTakeDetail;
  result: MockExamAttemptResult;
}) {
  const [answerFilter, setAnswerFilter] = useState<"all" | "correct" | "incorrect">("all");
  const scoreColor =
    result.percent >= 90
      ? "border-emerald-200 bg-emerald-50 text-emerald-800"
      : result.percent >= 60
        ? "border-sky-200 bg-sky-50 text-sky-800"
        : "border-amber-200 bg-amber-50 text-amber-800";

  if (result.status === "processing") {
    return (
      <div className="mx-auto max-w-xl space-y-6 text-center">
        <Link href={`/mock-exams/${exam.section}`} className="block text-left text-sm text-brand-700 hover:underline">← Back to {exam.section} exams</Link>
        <div className="border border-slate-200 bg-white p-8 shadow-sm">
          <LoaderCircle className="mx-auto animate-spin text-[#2b4a78]" size={40} aria-hidden="true" />
          <h1 className="mt-5 text-2xl font-bold text-slate-950">Your recordings are being reviewed</h1>
          <p className="mt-3 text-slate-700">Your feedback should be ready within 5 minutes. This page will update automatically when it is complete.</p>
          <p className="mt-3 text-sm text-slate-600">You can leave now and open View attempts later to see the completed feedback.</p>
          <p className="mt-5 border-t border-slate-200 pt-4 text-left text-sm leading-6 text-slate-600">The real speaking exam is assessed by people. We provide practice feedback on how you did, so this score and feedback may differ from the official exam result.</p>
        </div>
      </div>
    );
  }

  if (result.attempt_no === 0) {
    return (
      <div className="space-y-6">
        <Link href={`/mock-exams/${exam.section}`} className="text-sm text-brand-700 hover:underline">
          ← Back to {exam.section} exams
        </Link>
        <div className="card mx-auto max-w-md p-8 text-center">
          <h2 className="text-xl font-semibold">You&apos;ve completed the exam!</h2>
          <p className="mt-2 text-sm text-slate-600">
            Sign in with email/password or Google to view your score and detailed feedback — it&apos;s free.
          </p>
          <button
            type="button"
            onClick={() => {
              window.location.href = `/signin?callbackUrl=${encodeURIComponent(window.location.pathname)}`;
            }}
            className="btn-primary mt-6 px-5 py-2 text-sm"
          >
            Continue to sign in
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <Link href={`/mock-exams/${exam.section}`} className="text-sm text-brand-700 hover:underline">
        ← Back to {exam.section} exams
      </Link>
      <div className={clsx("rounded-xl border p-6 text-center", scoreColor)}>
        <p className="text-3xl font-bold">{result.label}</p>
        <p className="mt-2 text-lg">
          {result.score} / {result.total} {exam.section === "writing" ? "points" : exam.section === "speaking" ? "practice points" : "correct"} ({result.percent}%)
        </p>
        {exam.section === "writing" && (
          <p className="mt-1 text-sm">Study target: 25/37 points (about 68%). This is not an official DUO pass mark.</p>
        )}
        {exam.pass_threshold != null && (
          <p className="mt-1 text-sm">Pass mark: {exam.pass_threshold}/{exam.max_score}</p>
        )}
        <p className="mt-1 text-xs text-slate-500">
          Attempt #{result.attempt_no} · {formatDate(result.created_at)}
        </p>
        {exam.section === "speaking" && (
          <p className="mt-4 border-t border-current/20 pt-4 text-left text-sm leading-6">The real speaking exam is assessed by people. We provide practice feedback on how you did, so this score and feedback may differ from the official exam result.</p>
        )}
      </div>

      {result.results.some((item) => item.graded) && (
        <div className="flex flex-wrap items-center gap-2">
          {([
            ["all", "All answers"],
            ["correct", "Correct"],
            ["incorrect", "Incorrect"],
          ] as const).map(([value, label]) => (
            <button
              key={value}
              onClick={() => setAnswerFilter(value)}
              className={clsx(
                "rounded-full border px-4 py-2 text-sm font-semibold transition",
                answerFilter === value
                  ? "border-[#2b4a78] bg-[#2b4a78] text-white"
                  : "border-slate-200 bg-white text-slate-700 hover:border-slate-300",
              )}
            >
              {label}
            </button>
          ))}
        </div>
      )}

      <div className="space-y-4">
        {result.results
          .filter((r) => r.graded || exam.section === "writing" || exam.section === "speaking")
          .filter((r) => {
            if (answerFilter === "correct") return r.graded && r.correct === true;
            if (answerFilter === "incorrect") return r.graded && r.correct === false;
            return true;
          })
          .map((r) => {
            const question = exam.questions.find((q) => q.id === r.id);
            const questionNumber = exam.questions.slice().sort((a, b) => a.order_index - b.order_index).findIndex((q) => q.id === r.id) + 1;
            return (
              <div key={r.id} className="card p-4">
                {question && (
                  <p className="mb-2 text-sm font-semibold text-[#2b4a78]">
                    {exam.section === "speaking" && question.part_number ? `Part ${question.part_number} · ` : ""}
                    Question {questionNumber}
                  </p>
                )}
                <p className="font-medium">{question?.question_text}</p>
                {r.writing_feedback ? (
                  <>
                    <p className="mt-2 text-sm font-semibold text-slate-800">
                      Score: {r.writing_feedback.score}/{r.writing_feedback.max_score}
                    </p>
                    <div className="mt-4 border-l-4 border-slate-400 bg-slate-50 px-4 py-3">
                      <p className="text-sm font-semibold text-slate-800">Your answer</p>
                      <p className="mt-2 whitespace-pre-wrap text-sm text-slate-700">{r.given}</p>
                    </div>
                    <p className="mt-2 text-sm font-semibold text-slate-700">Feedback</p>
                    <p className="mt-2 whitespace-pre-wrap text-sm text-slate-700">{r.writing_feedback.feedback}</p>
                    {r.writing_feedback.criterion_scores.length > 0 && (
                      <div className="mt-4 grid gap-x-5 gap-y-1 text-sm sm:grid-cols-2">
                        {r.writing_feedback.criterion_scores.map((criterion) => (
                          <p key={criterion.criterion} className="flex justify-between border-b border-slate-200 py-1 text-slate-700">
                            <span>{criterion.criterion.replaceAll("_", " ")}</span>
                            <span className="font-semibold">{criterion.score}</span>
                          </p>
                        ))}
                      </div>
                    )}
                    {r.writing_feedback.possible_answer && (
                      <div className="mt-4 border-l-4 border-[#2563eb] bg-blue-50 px-4 py-3">
                        <p className="text-sm font-semibold text-slate-800">Improved answer (Dutch)</p>
                        <p className="mt-2 whitespace-pre-wrap text-sm text-slate-700">{r.writing_feedback.possible_answer}</p>
                      </div>
                    )}
                  </>
                ) : exam.section === "speaking" && r.speaking_feedback ? (
                  <>
                    <p className={clsx("mt-2 text-sm font-semibold", r.speaking_feedback.label === "Excellent" ? "text-emerald-700" : r.speaking_feedback.label === "Good" ? "text-sky-700" : "text-amber-700")}>
                      {r.speaking_feedback.label}
                    </p>
                    <div className="mt-4 border-l-4 border-slate-400 bg-slate-50 px-4 py-3">
                      <p className="text-sm font-semibold text-slate-800">What you said</p>
                      <p className="mt-2 whitespace-pre-wrap text-sm text-slate-700">{r.speaking_feedback.spoken_text || "Geen duidelijke spraak herkend."}</p>
                    </div>
                    {r.speaking_feedback.feedback && <p className="mt-3 whitespace-pre-wrap text-sm text-slate-700">{r.speaking_feedback.feedback}</p>}
                    {r.speaking_feedback.possible_answer && (
                      <div className="mt-4 border-l-4 border-[#2563eb] bg-blue-50 px-4 py-3">
                        <p className="text-sm font-semibold text-slate-800">Improved answer (Dutch)</p>
                        <p className="mt-2 whitespace-pre-wrap text-sm text-slate-700">{r.speaking_feedback.possible_answer}</p>
                      </div>
                    )}
                  </>
                ) : exam.section === "writing" && !r.given ? (
                  <p className="mt-2 text-sm font-semibold text-slate-500">Not filled / skipped</p>
                ) : exam.section === "writing" ? (
                  <p className="mt-2 text-sm text-slate-500">Not evaluated</p>
                ) : exam.section === "speaking" ? (
                  <p className="mt-2 text-sm font-semibold text-slate-500">Not answered</p>
                ) : (
                  <p className={clsx("mt-1 text-sm", r.correct ? "text-emerald-700" : "text-red-700")}>
                    Your answer: {r.given ?? "(no answer)"} {r.correct ? "✓" : `— correct answer: ${r.answer}`}
                  </p>
                )}
                {r.explanation && <p className="mt-1 text-sm text-slate-600">{r.explanation}</p>}
              </div>
            );
          })}
      </div>

    </div>
  );
}

export function ExamPageClient({ examId, viewAttemptNo }: { examId: string; viewAttemptNo?: number }) {
  const [exam, setExam] = useState<MockExamTakeDetail | null>(null);
  const [attempts, setAttempts] = useState<MockExamAttemptSummary[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [speakingRecordings, setSpeakingRecordings] = useState<Record<string, Blob>>({});
  const [result, setResult] = useState<MockExamAttemptResult | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [secondsLeft, setSecondsLeft] = useState<number | null>(null);
  const [timeUp, setTimeUp] = useState(false);

  const [phase, setPhase] = useState<"intro" | "question">("intro");
  const [currentIndex, setCurrentIndex] = useState(0);
  const [timerVisible, setTimerVisible] = useState(false);
  const [flagged, setFlagged] = useState<Set<string>>(new Set());
  const [showOverview, setShowOverview] = useState(false);

  useEffect(() => {
    callApi<MockExamTakeDetail>(`mock-exams/${examId}/take`)
      .then((data) => {
        setExam(data);
        setSecondsLeft(data.time_limit_minutes * 60);
      })
      .catch((e) => setLoadError(e instanceof Error ? e.message : "Could not load this exam"));
  }, [examId]);

  useEffect(() => {
    callApi<MockExamAttemptSummary[]>(`mock-exams/${examId}/attempts`)
      .then(setAttempts)
      .catch(() => {
        // Attempt history is a nice-to-have; don't block the exam if it fails to load.
      });
    if (viewAttemptNo) {
      callApi<MockExamAttemptResult>(`mock-exams/${examId}/attempts/${viewAttemptNo}`)
        .then(setResult)
        .catch((e) => setLoadError(e instanceof Error ? e.message : "Could not load this attempt"));
    }
  }, [examId, viewAttemptNo]);

  useEffect(() => {
    if (result?.status !== "processing") return;
    const interval = window.setInterval(() => {
      void callApi<MockExamAttemptResult>(`mock-exams/${examId}/attempts/${result.attempt_no}`)
        .then(setResult)
        .catch(() => {
          // Keep the processing screen visible while the background job runs.
        });
    }, 5000);
    return () => window.clearInterval(interval);
  }, [examId, result?.attempt_no, result?.status]);

  const submit = async () => {
    setSubmitting(true);
    setSubmitError(null);
    try {
      if (exam?.section === "speaking") {
        await Promise.all(Object.entries(speakingRecordings).map(async ([questionId, recording]) => {
          const form = new FormData();
          form.append("question_id", questionId);
          form.append("recording", recording, "answer.webm");
          const response = await fetch(`/api/backend/mock-exams/${examId}/recordings`, { method: "POST", body: form });
          if (!response.ok) throw new Error((await response.text()) || "Could not upload a speaking answer");
        }));
      }
      setResult(
        await callApi<MockExamAttemptResult>(`mock-exams/${examId}/submit`, {
          method: "POST",
          body: JSON.stringify({ answers }),
        }),
      );
    } catch (e) {
      setSubmitError(e instanceof Error ? e.message : "Could not submit the exam");
    } finally {
      setSubmitting(false);
    }
  };

  // Countdown always runs once the exam has started — the timer badge is just hidden
  // until the learner clicks the clock icon, matching the real DUO exam player. When it
  // reaches zero we flag time-up and stop; the learner can keep answering and submit
  // manually whenever they're ready (the real exam would end automatically here).
  useEffect(() => {
    if (phase !== "question" || result || secondsLeft === null || secondsLeft <= 0) return;
    const id = setTimeout(() => setSecondsLeft((s) => (s ?? 0) - 1), 1000);
    return () => clearTimeout(id);
  }, [phase, secondsLeft, result]);

  useEffect(() => {
    if (secondsLeft === 0) setTimeUp(true);
  }, [secondsLeft]);

  const passageById = useMemo(() => {
    const map = new Map<string, MockExamTakeDetail["passages"][number]>();
    for (const p of exam?.passages ?? []) map.set(p.id, p);
    return map;
  }, [exam]);

  const sortedQuestions = useMemo(
    () => (exam?.questions ?? []).slice().sort((a, b) => a.order_index - b.order_index),
    [exam],
  );

  if (loadError?.includes("LOGIN_REQUIRED")) {
    return (
      <div className="card mx-auto max-w-md p-8 text-center">
        <h2 className="text-xl font-semibold">Sign in to start this exam</h2>
        <p className="mt-2 text-sm text-slate-600">
          Sign in with email/password or Google to take practice exams and track your results — it&apos;s free.
        </p>
        <button
          type="button"
          onClick={() => {
            window.location.href = `/signin?callbackUrl=${encodeURIComponent(window.location.pathname)}`;
          }}
          className="btn-primary mt-6 px-5 py-2 text-sm"
        >
          Continue to sign in
        </button>
      </div>
    );
  }
  if (loadError?.includes("PREMIUM_REQUIRED")) {
    return (
      <div className="card mx-auto max-w-md p-8 text-center">
        <h2 className="text-xl font-semibold">This exam is Premium</h2>
        <p className="mt-2 text-sm text-slate-600">
          Unlock this section or the complete package to continue this exam.
        </p>
        <Link href="/pricing" className="btn-primary mt-6 inline-block px-5 py-2 text-sm">
          See plans
        </Link>
      </div>
    );
  }
  if (loadError) return <p className="text-red-600">{loadError}</p>;
  if (!exam || (viewAttemptNo && !result)) return <p className="text-slate-500">Loading…</p>;
  if (result) return <ResultView exam={exam} result={result} />;
  if (exam.section === "writing") {
    return (
      <WritingExam
        exam={exam}
        examId={examId}
        attempts={attempts}
        answers={answers}
        onAnswerChange={(questionId, answer) => setAnswers((current) => ({ ...current, [questionId]: answer }))}
        onSubmit={submit}
        submitting={submitting}
        submitError={submitError}
      />
    );
  }
  if (exam.section === "speaking") {
    return (
      <SpeakingExamComponent
        exam={exam}
        examId={examId}
        attempts={attempts}
        onAnswerChange={(questionId, answer) => setAnswers((current) => ({ ...current, [questionId]: answer }))}
        onRecordingReady={(questionId, recording) => setSpeakingRecordings((current) => ({ ...current, [questionId]: recording }))}
        onSubmit={submit}
        submitting={submitting}
        submitError={submitError}
      />
    );
  }
  if (exam.section === "listening") {
    return (
      <ListeningExam
        exam={exam}
        examId={examId}
        attempts={attempts}
        answers={answers}
        onAnswerChange={(questionId, answer) => setAnswers((current) => ({ ...current, [questionId]: answer }))}
        onSubmit={submit}
        submitting={submitting}
        submitError={submitError}
      />
    );
  }
  if (exam.section === "knm") {
    return (
      <KnmExam
        exam={exam}
        examId={examId}
        attempts={attempts}
        answers={answers}
        onAnswerChange={(questionId, answer) => setAnswers((current) => ({ ...current, [questionId]: answer }))}
        onSubmit={submit}
        submitting={submitting}
        submitError={submitError}
      />
    );
  }

  if (exam.section === "reading") {
    return <ReadingExam exam={exam} examId={examId} attempts={attempts} answers={answers} onAnswerChange={(questionId, answer) => setAnswers((current) => ({ ...current, [questionId]: answer }))} onSubmit={submit} submitting={submitting} submitError={submitError} />;
  }
  const minutesLeft = secondsLeft !== null ? Math.max(0, Math.ceil(secondsLeft / 60)) : null;
  const header = (
    <ExamHeader
      title={exam.title}
      backHref={`/mock-exams/${exam.section}`}
      timer={phase === "question" && minutesLeft !== null ? { minutesLeft, visible: timerVisible, onToggle: () => setTimerVisible((v) => !v) } : null}
    />
  );

  if (phase === "intro") {
    return (
      <div className="-mx-4 -my-8 min-h-[70vh]">
        {header}
        <div className="p-4 sm:p-6">
          <IntroLayout
            left={
              <>
                <IntroHeading>Welkom bij het oefenexamen {exam.title}.</IntroHeading>
                <IntroBody>
                  <p>{exam.instructions || `U moet in dit oefenexamen ${exam.total_questions} vragen beantwoorden.`}</p>
                  <p>Wilt u met het examen beginnen, klik dan op &lsquo;start&rsquo;</p>
                </IntroBody>
                <IntroNote>Dit oefenexamen volgt de indeling van het DUO oefenexamen.</IntroNote>
              </>
            }
            right={<IntroSidePanel exam={exam} showAudioTest={false} />}
          />
        </div>
        <ExamFooter
          primaryLabel="Start ›"
          onPrimary={() => setPhase("question")}
        />
      </div>
    );
  }

  const question = sortedQuestions[currentIndex];
  const passage = question?.passage_id ? passageById.get(question.passage_id) : undefined;
  const isLast = currentIndex === sortedQuestions.length - 1;
  const isFirst = currentIndex === 0;

  return (
    <div className="-mx-4 -my-8 min-h-[70vh]">
      {header}

      {timeUp && (
        <TimeUpDialog
          questions={sortedQuestions}
          isAnswered={(id) => Boolean(answers[id])}
          submitting={submitting}
          onSubmit={submit}
        />
      )}

      <div className="grid gap-4 p-4 sm:p-6 md:grid-cols-2">
        <section className="max-h-[60vh] overflow-y-auto border border-slate-200 bg-white px-7 py-6 text-slate-900 shadow-sm">
          {passage ? (
            (() => {
              const { intro, body } = splitReadingIntro(passage);
              return (
                <>
                  {intro && <p className="text-[0.95rem] leading-[1.6]">{intro}</p>}
                  <p className={clsx("whitespace-pre-wrap text-[0.95rem] leading-[1.6]", intro && "mt-4")}>
                    {readingDisplayPrompt(passage)}
                  </p>
                  <hr className="my-6 border-slate-300" />
                  {passage.title && <p className="text-[0.95rem] font-bold">{passage.title}</p>}
                  <PassageMedia key={passage.id} mediaUrls={passage.media_urls} />
                  {body && (
                    <div className="mt-4">
                      <PassageContent text={body} />
                    </div>
                  )}
                </>
              );
            })()
          ) : (
            <p className="text-slate-400">No reading text for this question.</p>
          )}
        </section>

        <section className="max-h-[60vh] overflow-y-auto border border-slate-200 bg-white px-7 py-6 text-slate-900 shadow-sm">
          {question && (
            <>
              <p className="whitespace-pre-wrap text-slate-800">{question.question_text}</p>
              {question.question_type === "multiple_choice" && question.options ? (
                <div className="mt-4 space-y-3">
                  {question.options.map((opt, i) => {
                    const selected = answers[question.id] === opt;
                    const optionImageUrl = question.option_media_urls?.[i];
                    return (
                      <button
                        key={opt}
                        onClick={() => setAnswers((a) => ({ ...a, [question.id]: opt }))}
                        className={clsx(
                          "w-full rounded-xl border-2 p-4 text-left transition",
                          selected ? clsx(NAVY, "border-transparent text-white") : "border-slate-200 hover:border-slate-300",
                        )}
                      >
                        <span className="flex items-center gap-3">
                          <span
                            className={clsx(
                              "grid h-5 w-5 shrink-0 place-items-center rounded-full border-2",
                              selected ? "border-[#e8863c] bg-[#e8863c]" : "border-slate-300",
                            )}
                          />
                          <span className="font-semibold">{String.fromCharCode(65 + i)}</span>
                          {!optionImageUrl && <span>{opt}</span>}
                        </span>
                        {optionImageUrl && (
                          <img
                            src={mediaProxyUrl("image", optionImageUrl)}
                            alt={opt}
                            className="mt-3 block h-32 w-full rounded border border-slate-200 object-cover"
                          />
                        )}
                      </button>
                    );
                  })}
                </div>
              ) : (
                <textarea
                  className="mt-4 w-full rounded-lg border border-slate-200 p-2 text-sm"
                  rows={5}
                  placeholder="Type your answer (not auto-graded yet)"
                  value={answers[question.id] ?? ""}
                  onChange={(e) => setAnswers((a) => ({ ...a, [question.id]: e.target.value }))}
                />
              )}
            </>
          )}
        </section>
      </div>

      {submitError && <p className="px-6 text-red-600">{submitError}</p>}

      <ExamFooter
        onPrevious={() => setCurrentIndex((i) => Math.max(0, i - 1))}
        previousDisabled={isFirst}
        primaryLabel={isLast ? (submitting ? "Inleveren..." : "Inleveren") : "Volgende ›"}
        onPrimary={isLast ? submit : () => setCurrentIndex((i) => Math.min(sortedQuestions.length - 1, i + 1))}
        primaryDisabled={submitting && isLast}
        badge={`${currentIndex + 1} / ${sortedQuestions.length}`}
      >
        <button
          onClick={() => setShowOverview((v) => !v)}
          className="grid h-10 w-10 place-items-center rounded-md transition hover:bg-white/10"
          title="Kies een vraag"
          aria-label="Kies een vraag"
        >
          <Grid2X2 size={26} strokeWidth={1.8} />
        </button>
        <button
          onClick={() =>
            setFlagged((f) => {
              const next = new Set(f);
              if (question) next.has(question.id) ? next.delete(question.id) : next.add(question.id);
              return next;
            })
          }
          className={clsx(
            "grid h-10 w-10 place-items-center rounded-md transition",
            question && flagged.has(question.id) ? "bg-[#e8863c] text-slate-950" : "hover:bg-white/10",
          )}
          title="Markeer vraag"
          aria-label="Markeer vraag"
        >
          <Bookmark size={26} strokeWidth={1.8} fill={question && flagged.has(question.id) ? "currentColor" : "none"} />
        </button>

        {showOverview && (
          <QuestionPicker
            questions={sortedQuestions}
            answers={answers}
            currentIndex={currentIndex}
            bookmarkedQuestionIds={Array.from(flagged)}
            onClose={() => setShowOverview(false)}
            onSelect={(index) => {
              setCurrentIndex(index);
              setShowOverview(false);
            }}
          />
        )}
      </ExamFooter>
    </div>
  );
}

