"use client";

import { Fragment, useEffect, useRef, useState } from "react";
import clsx from "clsx";
import { Bookmark, Grid2X2, Info, X } from "lucide-react";
import { DuoPlaybackControls } from "./DuoPlaybackControls";
import {
  ExamFooter,
  ExamHeader,
  IncompleteDialog,
  IntroBody,
  IntroHeading,
  IntroLayout,
  IntroNote,
  IntroSidePanel,
  TimeReminderDialog,
  TimeUpDialog,
  mediaProxyUrl,
} from "./DuoExamChrome";
import type { MockExamAttemptSummary, MockExamTakeDetail } from "@/lib/types";

const QUESTION_AUDIO_PLAYBACK_RATE = 1.1;

export function KnmExam({
  exam,
  examId,
  attempts,
  answers,
  onAnswerChange,
  onSubmit,
  submitting,
  submitError,
}: {
  exam: MockExamTakeDetail;
  examId: string;
  attempts: MockExamAttemptSummary[];
  answers: Record<string, string>;
  onAnswerChange: (questionId: string, answer: string) => void;
  onSubmit: () => void;
  submitting: boolean;
  submitError: string | null;
}) {
  const questions = exam.questions.slice().sort((a, b) => a.order_index - b.order_index);
  const passageById = new Map(exam.passages.map((passage) => [passage.id, passage]));
  const [showExamIntroduction, setShowExamIntroduction] = useState(true);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [questionPickerOpen, setQuestionPickerOpen] = useState(false);
  const [bookmarkedQuestionIds, setBookmarkedQuestionIds] = useState<string[]>([]);
  const [examSecondsLeft, setExamSecondsLeft] = useState(exam.time_limit_minutes * 60);
  const [showExamTime, setShowExamTime] = useState(false);
  const [showTimeReminder, setShowTimeReminder] = useState(false);
  const [showIncompleteConfirmation, setShowIncompleteConfirmation] = useState(false);
  const [showTimeUp, setShowTimeUp] = useState(false);
  const [themeIntro, setThemeIntro] = useState<string | null>(() => exam.questions[0]?.category ?? null);
  const [audioPlaying, setAudioPlaying] = useState(false);
  const [audioProgress, setAudioProgress] = useState(0);
  const [volume, setVolume] = useState(1);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const timeUpSubmitRef = useRef(false);

  const question = questions[currentIndex];
  const passage = question?.passage_id ? passageById.get(question.passage_id) : undefined;
  const passageImage = passage?.media_urls.find((media) => media.type === "image");
  const isLast = currentIndex === questions.length - 1;
  const questionAudioUrl = question?.question_audio_url
    ?? passage?.media_urls.find((media) => media.type === "audio")?.url
    ?? null;
  const incompleteQuestionIds = questions.filter((item) => !answers[item.id]).map((item) => item.id);

  function stopAudio() {
    audioRef.current?.pause();
    audioRef.current = null;
    setAudioPlaying(false);
    setAudioProgress(0);
  }

  function skipAudio(seconds: number) {
    const player = audioRef.current;
    if (!player) return;
    player.currentTime = Math.max(0, Math.min(player.duration || Infinity, player.currentTime + seconds));
  }

  function toggleAudio() {
    if (!questionAudioUrl) return;
    const player = audioRef.current;
    if (player) {
      if (player.paused) void player.play();
      else player.pause();
      return;
    }
    const audio = new Audio(mediaProxyUrl("audio", questionAudioUrl));
    audio.playbackRate = QUESTION_AUDIO_PLAYBACK_RATE;
    audio.volume = volume;
    audioRef.current = audio;
    audio.ontimeupdate = () => {
      if (Number.isFinite(audio.duration) && audio.duration > 0) {
        setAudioProgress(Math.min(100, (audio.currentTime / audio.duration) * 100));
      }
    };
    audio.onplay = () => setAudioPlaying(true);
    audio.onpause = () => setAudioPlaying(false);
    audio.onended = () => {
      setAudioPlaying(false);
      setAudioProgress(100);
    };
    void audio.play().catch(() => setAudioPlaying(false));
  }

  function showQuestion(index: number) {
    stopAudio();
    setThemeIntro(null);
    setCurrentIndex(index);
  }

  function showThemeIntro(category: string) {
    stopAudio();
    setThemeIntro(category);
  }

  function goNext() {
    if (themeIntro !== null) {
      setThemeIntro(null);
      return;
    }
    const next = Math.min(questions.length - 1, currentIndex + 1);
    stopAudio();
    setCurrentIndex(next);
    const nextCategory = questions[next]?.category;
    if (nextCategory && nextCategory !== question?.category) setThemeIntro(nextCategory);
  }

  function goPrevious() {
    if (themeIntro !== null) {
      const firstOfTheme = questions.findIndex((item) => item.category === themeIntro);
      if (firstOfTheme > 0) showQuestion(firstOfTheme - 1);
      return;
    }
    const category = question?.category;
    if (category && questions[currentIndex - 1]?.category !== category) {
      showThemeIntro(category);
      return;
    }
    if (currentIndex === 0) return;
    stopAudio();
    setCurrentIndex(currentIndex - 1);
  }

  function requestSubmit() {
    if (incompleteQuestionIds.length > 0) {
      setShowIncompleteConfirmation(true);
      return;
    }
    onSubmit();
  }

  useEffect(() => {
    if (showExamIntroduction || submitting || examSecondsLeft <= 0) return;
    const timer = window.setTimeout(() => setExamSecondsLeft((seconds) => Math.max(0, seconds - 1)), 1000);
    return () => window.clearTimeout(timer);
  }, [showExamIntroduction, submitting, examSecondsLeft]);

  useEffect(() => {
    if (!showExamIntroduction && examSecondsLeft === 15 * 60) setShowTimeReminder(true);
  }, [showExamIntroduction, examSecondsLeft]);

  useEffect(() => {
    if (showExamIntroduction || examSecondsLeft !== 0 || timeUpSubmitRef.current) return;
    timeUpSubmitRef.current = true;
    stopAudio();
    setShowTimeUp(true);
  }, [showExamIntroduction, examSecondsLeft]);

  useEffect(() => {
    if (audioRef.current) audioRef.current.volume = volume;
  }, [volume]);

  useEffect(() => {
    stopAudio();
  }, [question?.id]);

  useEffect(() => () => {
    audioRef.current?.pause();
  }, []);

  if (!question) return null;

  return (
    <div className="fixed inset-0 z-50 flex h-screen w-screen flex-col overflow-hidden bg-[#f1f2f4]">
      <ExamHeader
        title={exam.title}
        backHref={`/mock-exams/${exam.section}`}
        timer={showExamIntroduction ? null : { minutesLeft: Math.ceil(examSecondsLeft / 60), visible: showExamTime, onToggle: () => setShowExamTime((show) => !show) }}
        volume={showExamIntroduction ? null : { value: volume, onChange: setVolume }}
      />

      <main className="min-h-0 w-full flex-1 overflow-hidden px-4 py-7 sm:px-6">
        {showExamIntroduction ? (
          <KnmExamIntroduction exam={exam} attempts={attempts} examId={examId} />
        ) : themeIntro !== null ? (
          <KnmThemeIntroduction category={themeIntro} />
        ) : (
          <div className="grid h-full min-h-0 gap-4 lg:grid-cols-2">
            <section className="min-h-0 overflow-y-auto border border-slate-200 bg-white px-7 py-6 text-slate-900 shadow-sm">
              <div className="flex items-start justify-between gap-6">
                <div className="min-w-0 flex-1" />
                {questionAudioUrl && (
                  <div className="shrink-0">
                    <DuoPlaybackControls compact mediaPlaying={audioPlaying} mediaProgress={audioProgress} onSkip={skipAudio} onToggle={toggleAudio} />
                  </div>
                )}
              </div>
              {passageImage && (
                <img
                  src={mediaProxyUrl("image", passageImage.url)}
                  alt={passage?.title || "Situatie"}
                  className="mt-4 aspect-[4/3] w-full max-w-[26rem] object-cover"
                />
              )}
              {/* The real exam shows one text block under the photo, so the situation and question run together. */}
              <div className="mt-7 max-w-2xl space-y-2 text-[0.95rem] leading-[1.6]">
                {passage?.content_nl && <p className="whitespace-pre-wrap">{passage.content_nl}</p>}
                <p className="whitespace-pre-wrap">{question.question_text}</p>
              </div>
            </section>

            <section className="min-h-0 overflow-y-auto border border-slate-200 bg-white px-7 py-6 text-slate-900 shadow-sm">
              {question.options && (
                <div className="space-y-4">
                  {question.options.map((option, index) => {
                    const selected = answers[question.id] === option;
                    const optionImageUrl = question.option_media_urls?.[index];
                    return (
                      <div
                        key={`${question.id}-${option}`}
                        role="button"
                        tabIndex={0}
                        onClick={() => onAnswerChange(question.id, option)}
                        onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") onAnswerChange(question.id, option); }}
                        className={clsx(
                          "flex w-full cursor-pointer items-center gap-6 rounded-lg px-6 py-5 text-left text-[0.95rem] leading-[1.5] transition",
                          selected ? "border-2 border-[#e08b4c]" : "border border-[#e2e5e8] hover:border-[#c8cfd4]",
                        )}
                      >
                        <span className={clsx("grid h-5 w-5 shrink-0 place-items-center rounded-full border", selected ? "border-[#e08b4c]" : "border-[#9aa8b4]")} aria-hidden="true">
                          {selected && <span className="h-2.5 w-2.5 rounded-full bg-[#e08b4c]" />}
                        </span>
                        <span className="w-4 shrink-0 text-base font-bold">{String.fromCharCode(65 + index)}</span>
                        <span className="min-w-0 flex-1">
                          {!optionImageUrl && option}
                          {optionImageUrl && <img src={mediaProxyUrl("image", optionImageUrl)} alt={option} className="block aspect-[4/3] max-h-40 w-full object-cover" />}
                        </span>
                      </div>
                    );
                  })}
                </div>
              )}
            </section>
          </div>
        )}

        {submitError && <p className="mt-5 text-red-600">{submitError}</p>}
      </main>

      <ExamFooter
        onPrevious={showExamIntroduction ? undefined : goPrevious}
        previousDisabled={currentIndex === 0 && themeIntro !== null}
        primaryLabel={showExamIntroduction ? "Start ›" : isLast && themeIntro === null ? (submitting ? "Inleveren..." : "Inleveren") : "Volgende ›"}
        onPrimary={showExamIntroduction ? () => setShowExamIntroduction(false) : isLast && themeIntro === null ? requestSubmit : goNext}
        primaryDisabled={submitting && isLast && themeIntro === null}
        badge={showExamIntroduction ? null : themeIntro !== null ? "info" : `${currentIndex + 1} / ${questions.length}`}
      >
        {!showExamIntroduction && (
          <>
            <button onClick={() => setQuestionPickerOpen((open) => !open)} className="grid h-10 w-10 place-items-center rounded-md transition hover:bg-white/10" title="Kies een vraag" aria-label="Kies een vraag"><Grid2X2 size={26} strokeWidth={1.8} /></button>
            <button onClick={() => setBookmarkedQuestionIds((ids) => ids.includes(question.id) ? ids.filter((id) => id !== question.id) : [...ids, question.id])} className={clsx("grid h-10 w-10 place-items-center rounded-md transition", bookmarkedQuestionIds.includes(question.id) ? "bg-[#e8863c] text-slate-950" : "hover:bg-white/10")} title="Markeer vraag" aria-label="Markeer vraag"><Bookmark size={26} strokeWidth={1.8} fill={bookmarkedQuestionIds.includes(question.id) ? "currentColor" : "none"} /></button>
            {questionPickerOpen && <KnmQuestionPicker questions={questions} answers={answers} currentIndex={currentIndex} themeIntro={themeIntro} bookmarkedQuestionIds={bookmarkedQuestionIds} onClose={() => setQuestionPickerOpen(false)} onSelect={(index) => { showQuestion(index); setQuestionPickerOpen(false); }} onSelectTheme={(category) => { showThemeIntro(category); setQuestionPickerOpen(false); }} />}
          </>
        )}
      </ExamFooter>

      {showIncompleteConfirmation && <IncompleteDialog count={incompleteQuestionIds.length} onCancel={() => setShowIncompleteConfirmation(false)} onConfirm={() => { setShowIncompleteConfirmation(false); onSubmit(); }} />}
      {showTimeReminder && <TimeReminderDialog onClose={() => setShowTimeReminder(false)} />}
      {showTimeUp && <KnmTimeUpDialog questions={questions} answers={answers} submitting={submitting} onSubmit={onSubmit} />}
    </div>
  );
}

const THEME_LABELS: Record<string, string> = {
  customs: "omgangsvormen, waarden en normen",
  work_income: "werk en inkomen",
  education: "onderwijs en opvoeding",
  healthcare: "gezondheid en gezondheidszorg",
  housing: "wonen",
  institutions: "instanties",
  government: "staatsinrichting en rechtsstaat",
  history_geography: "geschiedenis en geografie",
};

function themeLabel(category: string): string {
  return THEME_LABELS[category] ?? category;
}

function KnmThemeIntroduction({ category }: { category: string }) {
  return (
    <div className="mx-auto h-full min-h-0 w-full max-w-4xl overflow-y-auto border border-slate-200 bg-white px-7 py-6 text-slate-900 shadow-sm">
      <p className="text-[0.95rem] leading-[1.6]">
        De volgende vragen gaan over het thema &lsquo;{themeLabel(category)}&rsquo;. Klik op &lsquo;volgende&rsquo;.
      </p>
    </div>
  );
}

function KnmQuestionPicker({
  questions,
  answers,
  currentIndex,
  themeIntro,
  bookmarkedQuestionIds,
  onClose,
  onSelect,
  onSelectTheme,
}: {
  questions: MockExamTakeDetail["questions"];
  answers: Record<string, string>;
  currentIndex: number;
  themeIntro: string | null;
  bookmarkedQuestionIds: string[];
  onClose: () => void;
  onSelect: (index: number) => void;
  onSelectTheme: (category: string) => void;
}) {
  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-slate-950/55 p-4 backdrop-blur-sm" role="dialog" aria-modal="true" aria-labelledby="knm-overview-title">
      <section className="w-full max-w-3xl rounded bg-white px-7 py-6 text-slate-900 shadow-2xl">
        <header className="flex items-center justify-between gap-6">
          <h2 id="knm-overview-title" className="text-xl font-normal">Overzicht examen</h2>
          <button onClick={onClose} className="grid h-8 w-8 place-items-center rounded-full transition hover:bg-slate-100 focus-visible:bg-slate-100" title="Sluiten" aria-label="Sluiten"><X size={22} strokeWidth={1.75} /></button>
        </header>
        <div className="mt-7 flex flex-wrap gap-2">
          {questions.map((item, index) => (
            <Fragment key={item.id}>
              {item.category && item.category !== questions[index - 1]?.category && (
                <button
                  onClick={() => onSelectTheme(item.category!)}
                  className={clsx("grid h-10 w-14 place-items-center rounded text-slate-950 transition hover:brightness-95", themeIntro === item.category ? "bg-[#e08b4c]" : "bg-[#4d7e91] text-white")}
                  title={`Thema: ${themeLabel(item.category)}`}
                  aria-label={`Thema: ${themeLabel(item.category)}`}
                >
                  <Info size={18} strokeWidth={2.2} aria-hidden="true" />
                </button>
              )}
              <button
                onClick={() => onSelect(index)}
                className={clsx("relative grid h-10 w-14 place-items-center rounded text-sm font-semibold transition hover:brightness-95", index === currentIndex && themeIntro === null ? "bg-[#e08b4c]" : answers[item.id] ? "bg-[#4d7e91] text-white" : "bg-[#dfe3e6]")}
              >
                {index + 1}
                {bookmarkedQuestionIds.includes(item.id) && <Bookmark className="absolute right-0.5 top-0.5 text-[#ffe6c7]" size={12} fill="currentColor" aria-label="Bladwijzer" />}
              </button>
            </Fragment>
          ))}
        </div>
        <ul className="mt-7 flex flex-wrap items-center gap-x-8 gap-y-3 text-sm">
          <li className="flex items-center gap-2"><span className="h-4 w-4 rounded-sm bg-[#e08b4c]" />Geselecteerd</li>
          <li className="flex items-center gap-2"><span className="h-4 w-4 rounded-sm bg-[#dfe3e6]" />Onbeantwoord</li>
          <li className="flex items-center gap-2"><span className="h-4 w-4 rounded-sm bg-[#4d7e91]" />Beantwoord</li>
          <li className="flex items-center gap-2"><Bookmark className="text-[#f0c391]" size={18} fill="currentColor" />Bladwijzers</li>
        </ul>
      </section>
    </div>
  );
}

function KnmTimeUpDialog({
  questions,
  answers,
  submitting,
  onSubmit,
}: {
  questions: MockExamTakeDetail["questions"];
  answers: Record<string, string>;
  submitting: boolean;
  onSubmit: () => void;
}) {
  return <TimeUpDialog questions={questions} isAnswered={(id) => Boolean(answers[id])} submitting={submitting} onSubmit={onSubmit} />;
}

function KnmExamIntroduction({ exam, attempts, examId }: { exam: MockExamTakeDetail; attempts: MockExamAttemptSummary[]; examId: string }) {
  return (
    <IntroLayout
      left={
        <>
          <IntroHeading>Welkom bij het oefenexamen Kennis van de Nederlandse Maatschappij.</IntroHeading>
          <IntroBody>
            <p>U moet in dit oefenexamen {exam.total_questions} vragen beantwoorden.</p>
            <p>Het echte examen KNM bestaat ook uit 40 vragen.</p>
            <p>Wilt u met het examen beginnen, klik dan op &lsquo;start&rsquo;</p>
          </IntroBody>
          <IntroNote>Dit oefenexamen is gemaakt voor KNM-training en volgt de indeling van het DUO oefenexamen.</IntroNote>
        </>
      }
      right={<IntroSidePanel exam={exam} />}
    />
  );
}
