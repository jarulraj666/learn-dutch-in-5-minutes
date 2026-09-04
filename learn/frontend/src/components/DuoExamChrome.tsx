"use client";

import { useState, type ReactNode } from "react";
import Link from "next/link";
import clsx from "clsx";
import { AlarmClock, Bookmark, Play, TriangleAlert, Volume2, VolumeX, X } from "lucide-react";
import type { MockExamTakeDetail } from "@/lib/types";

/** Shared DUO exam-player chrome used by the listening and KNM exam screens. */

const NAVY = "bg-[#2b4a78]";
const ORANGE = "bg-[#e8863c] hover:bg-[#dc7a30]";

export function ExamHeader({
  title,
  backHref,
  timer,
  volume,
}: {
  title: string;
  backHref: string;
  timer?: { minutesLeft: number; visible: boolean; onToggle: () => void } | null;
  volume?: { value: number; onChange: (value: number) => void } | null;
}) {
  return (
    <header className={clsx(NAVY, "grid grid-cols-[1fr_auto_1fr] items-center gap-4 px-6 py-3 text-white")}>
      <div className="flex min-w-0 items-center gap-3">
        <Link href={backHref} className="text-sm text-white/80 hover:text-white">←</Link>
        <span className="truncate font-medium">{title}</span>
      </div>
      {timer ? (
        <button
          onClick={timer.onToggle}
          className="grid h-11 min-w-11 place-items-center rounded-full px-2 text-white transition hover:bg-white/15 focus-visible:bg-white/15"
          title={timer.visible ? "Toon timerpictogram" : "Toon resterende examentijd"}
          aria-label={timer.visible ? `${timer.minutesLeft} minuten resterend` : "Toon resterende examentijd"}
        >
          {timer.visible
            ? <span className="whitespace-nowrap text-lg font-bold leading-none">{timer.minutesLeft} min</span>
            : <AlarmClock size={30} strokeWidth={1.7} aria-hidden="true" />}
        </button>
      ) : <span />}
      {volume ? (
        <div className="flex items-center justify-end gap-2">
          <button onClick={() => volume.onChange(Math.max(0, volume.value - 1 / 7))} className="grid h-8 w-8 place-items-center rounded-full transition hover:bg-white/15" title="Volume lager" aria-label="Volume lager"><VolumeX size={20} /></button>
          <div className="flex gap-[3px]" aria-label={`Volume ${Math.round(volume.value * 100)}%`}>
            {Array.from({ length: 7 }, (_, index) => <span key={index} className={clsx("h-[7px] w-[7px]", volume.value >= (index + 1) / 7 ? "bg-white" : "bg-white/35")} />)}
          </div>
          <button onClick={() => volume.onChange(Math.min(1, volume.value + 1 / 7))} className="grid h-8 w-8 place-items-center rounded-full transition hover:bg-white/15" title="Volume hoger" aria-label="Volume hoger"><Volume2 size={20} /></button>
        </div>
      ) : <span />}
    </header>
  );
}

export function ExamFooter({
  onPrevious,
  previousDisabled,
  primaryLabel,
  onPrimary,
  primaryDisabled,
  badge,
  children,
}: {
  onPrevious?: () => void;
  previousDisabled?: boolean;
  primaryLabel: string;
  onPrimary: () => void;
  primaryDisabled?: boolean;
  badge?: string | null;
  children?: ReactNode;
}) {
  return (
    <footer className={clsx(NAVY, "shrink-0 px-4 py-5 sm:px-6")}>
      <div className="relative w-full">
        <div className="flex items-center justify-between gap-6">
          {onPrevious ? (
            <button
              onClick={onPrevious}
              disabled={previousDisabled}
              className={clsx(ORANGE, "inline-flex min-w-[11rem] items-center justify-center gap-2 rounded-full px-6 py-2 text-xs font-bold uppercase tracking-[0.12em] text-slate-900 transition disabled:bg-[#8ea6c4] disabled:text-white/80 disabled:hover:bg-[#8ea6c4]")}
            >
              ‹ Vorige
            </button>
          ) : <span className="min-w-[11rem]" />}
          <div className="relative flex items-center gap-8 text-white">{children}</div>
          <button
            onClick={onPrimary}
            disabled={primaryDisabled}
            className={clsx(ORANGE, "inline-flex min-w-[11rem] items-center justify-center gap-2 rounded-full px-6 py-2 text-xs font-bold uppercase tracking-[0.12em] text-slate-900 transition disabled:opacity-60")}
          >
            {primaryLabel}
          </button>
        </div>
        {badge && (
          <span className={clsx(ORANGE, "absolute -bottom-[1.9rem] left-0 rounded-tr-md px-3 py-1 text-xs font-bold text-slate-950")}>{badge}</span>
        )}
      </div>
    </footer>
  );
}

export function mediaProxyUrl(type: "image" | "audio" | "video", path: string): string {
  if (path.startsWith("https://") || path.startsWith("http://")) return path;
  return `/api/backend/mock-exams/media/${type}?path=${encodeURIComponent(path)}`;
}

export function StatTile({ value, label }: { value: number; label: string }) {
  return (
    <div className="w-[8.5rem] overflow-hidden rounded-b-xl border-2 border-[#e08b4c] text-center">
      <p className="grid h-24 place-items-center text-[2.6rem] font-light leading-none">{value}</p>
      <p className="bg-[#e08b4c] px-2 py-3 text-xs font-bold uppercase tracking-[0.08em] text-slate-900">{label}</p>
    </div>
  );
}

/** Left/right panel layout of the DUO welcome screen. */
export function IntroLayout({ left, right }: { left: ReactNode; right: ReactNode }) {
  return (
    <div className="grid h-full min-h-0 gap-4 lg:grid-cols-2">
      <section className="min-h-0 overflow-y-auto border border-slate-200 bg-white px-8 py-9 text-slate-950 shadow-sm sm:px-10">{left}</section>
      <section className="min-h-0 overflow-y-auto border border-slate-200 bg-white px-8 py-9 text-slate-950 shadow-sm sm:px-10">{right}</section>
    </div>
  );
}

export function IntroHeading({ children }: { children: ReactNode }) {
  return <p className="text-[0.95rem] font-bold leading-[1.5]">{children}</p>;
}

export function IntroBody({ children }: { children: ReactNode }) {
  return <div className="mt-6 max-w-2xl space-y-1 text-[0.95rem] leading-[1.5]">{children}</div>;
}

export function IntroNote({ children }: { children: ReactNode }) {
  return <p className="mt-10 max-w-2xl text-sm italic leading-[1.5] text-slate-700">{children}</p>;
}

export function IntroSidePanel({
  exam,
  showAudioTest = true,
}: {
  exam: MockExamTakeDetail;
  showAudioTest?: boolean;
}) {
  return (
    <>
      <h2 className="text-2xl font-bold leading-tight">{exam.title}</h2>
      <div className="mt-8 flex gap-8">
        <StatTile value={exam.total_questions} label="VRAGEN" />
        <StatTile value={exam.time_limit_minutes} label="MINUTEN" />
      </div>
      {showAudioTest && (
        <div className="mt-8 border-t-2 border-slate-900 pt-7">
          <h3 className="text-lg font-bold">Audiovolume testen</h3>
          <AudioVolumeTest />
        </div>
      )}
    </>
  );
}

function AudioVolumeTest() {
  const [volume, setVolume] = useState(0.5);
  function playAudioTest() {
    const audioContext = new AudioContext();
    const oscillator = audioContext.createOscillator();
    const gain = audioContext.createGain();
    oscillator.frequency.value = 440;
    gain.gain.value = volume * 0.12;
    oscillator.connect(gain).connect(audioContext.destination);
    oscillator.start();
    oscillator.stop(audioContext.currentTime + 0.7);
    oscillator.onended = () => void audioContext.close();
  }
  return (
    <div className="mt-6 flex h-[4.5rem] w-[13.6rem] items-center rounded-xl bg-[#2f5b96] text-white">
      <button onClick={playAudioTest} className="grid h-full w-[3.9rem] shrink-0 place-items-center rounded-l-xl border-r border-white/70 transition hover:bg-white/10" title="Test audio" aria-label="Test audio"><Play size={17} fill="currentColor" /></button>
      <div className="flex flex-1 items-center justify-center gap-2 px-2">
        <button onClick={() => setVolume((current) => Math.max(0, current - 1 / 7))} className="grid h-7 w-7 place-items-center rounded-full transition hover:bg-white/10" title="Volume lager" aria-label="Volume lager"><VolumeX size={17} /></button>
        <div className="flex gap-[3px]" aria-label={`Audiovolume ${Math.round(volume * 100)}%`}>
          {Array.from({ length: 7 }, (_, index) => <span key={index} className={clsx("h-[7px] w-[7px]", volume >= (index + 1) / 7 ? "bg-white" : "bg-[#6689b9]")} />)}
        </div>
        <button onClick={() => setVolume((current) => Math.min(1, current + 1 / 7))} className="grid h-7 w-7 place-items-center rounded-full transition hover:bg-white/10" title="Volume hoger" aria-label="Volume hoger"><Volume2 size={17} /></button>
      </div>
    </div>
  );
}

export function QuestionPicker({ questions, answers, currentIndex, bookmarkedQuestionIds, onClose, onSelect }: { questions: MockExamTakeDetail["questions"]; answers: Record<string, string>; currentIndex: number; bookmarkedQuestionIds: string[]; onClose: () => void; onSelect: (index: number) => void }) {
  // The real player boxes the questions of one text/fragment together.
  const groups: { index: number; question: MockExamTakeDetail["questions"][number] }[][] = [];
  questions.forEach((question, index) => {
    const last = groups[groups.length - 1];
    if (last && last[0].question.passage_id === question.passage_id) last.push({ index, question });
    else groups.push([{ index, question }]);
  });
  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-slate-950/55 p-4 backdrop-blur-sm" role="dialog" aria-modal="true" aria-labelledby="duo-overview-title">
      <section className="w-full max-w-3xl rounded bg-white px-7 py-6 text-slate-900 shadow-2xl">
        <header className="flex items-center justify-between gap-6">
          <h2 id="duo-overview-title" className="text-xl font-normal">Overzicht examen</h2>
          <button onClick={onClose} className="grid h-8 w-8 place-items-center rounded-full transition hover:bg-slate-100 focus-visible:bg-slate-100" title="Sluiten" aria-label="Sluiten"><X size={22} strokeWidth={1.75} /></button>
        </header>
        <div className="mt-7 flex flex-wrap gap-2">
          {groups.map((group) => (
            <div key={group[0].question.id} className="flex gap-1 rounded-md border border-[#c8cfd4] p-1">
              {group.map(({ index, question }) => (
                <button
                  key={question.id}
                  onClick={() => onSelect(index)}
                  className={clsx(
                    "relative grid h-10 w-14 place-items-center rounded text-sm font-semibold transition hover:brightness-95",
                    index === currentIndex ? "bg-[#e08b4c]" : answers[question.id] ? "bg-[#4d7e91] text-white" : "bg-[#dfe3e6]",
                  )}
                >
                  {index + 1}
                  {bookmarkedQuestionIds.includes(question.id) && <Bookmark className="absolute right-0.5 top-0.5 text-[#ffe6c7]" size={12} fill="currentColor" aria-label="Bladwijzer" />}
                </button>
              ))}
            </div>
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

export function IncompleteDialog({ count, onCancel, onConfirm }: { count: number; onCancel: () => void; onConfirm: () => void }) {
  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-slate-950/40 p-4" role="dialog" aria-modal="true" aria-labelledby="duo-incomplete-title">
      <div className="w-full max-w-md border border-slate-300 bg-white p-6 shadow-xl">
        <h2 id="duo-incomplete-title" className="text-xl font-bold">Niet alle antwoorden zijn ingevuld</h2>
        <p className="mt-3 text-slate-700">{count === 1 ? "Er is nog 1 vraag niet ingevuld. Deze vraag staat rood gemarkeerd." : `Er zijn nog ${count} vragen niet ingevuld. Deze vragen staan rood gemarkeerd.`}</p>
        <p className="mt-2 text-sm text-slate-600">Wilt u toch inleveren?</p>
        <div className="mt-6 flex justify-end gap-3"><button onClick={onCancel} className="btn-secondary">Terug naar examen</button><button onClick={onConfirm} className="btn-primary">Toch inleveren</button></div>
      </div>
    </div>
  );
}

export function TimeReminderDialog({ onClose }: { onClose: () => void }) {
  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-slate-950/40 p-4" role="dialog" aria-modal="true" aria-labelledby="duo-time-reminder-title">
      <div className="w-full max-w-md border border-slate-300 bg-white p-6 shadow-xl">
        <h2 id="duo-time-reminder-title" className="text-xl font-bold">Nog 15 minuten</h2>
        <p className="mt-3 text-slate-700">U heeft nog 15 minuten om het examen af te maken.</p>
        <div className="mt-6 flex justify-end"><button onClick={onClose} className="btn-primary">Verder met examen</button></div>
      </div>
    </div>
  );
}

/** DUO end-of-time screen: no way out except handing the exam in. */
export function TimeUpDialog({
  questions,
  isAnswered,
  submitting,
  onSubmit,
}: {
  questions: MockExamTakeDetail["questions"];
  isAnswered: (questionId: string) => boolean;
  submitting: boolean;
  onSubmit: () => void;
}) {
  const unanswered = questions.filter((item) => !isAnswered(item.id)).length;
  return (
    <div className="fixed inset-0 z-[60] grid place-items-center bg-slate-950/55 p-4 backdrop-blur-sm" role="dialog" aria-modal="true" aria-labelledby="duo-time-up-title">
      <section className="max-h-full w-full max-w-3xl overflow-y-auto bg-white px-6 py-7 text-slate-900 shadow-2xl sm:px-10 sm:py-9">
        <h2 id="duo-time-up-title" className="text-3xl font-normal sm:text-4xl">Je tijd is om</h2>
        <p className="mt-8 flex items-center gap-4 text-xl sm:text-2xl">
          <AlarmClock size={34} strokeWidth={1.8} aria-hidden="true" />
          Je hebt 0 minuten en 0 seconden over.
        </p>
        {unanswered > 0 && (
          <p className="mt-4 flex items-center gap-4 text-xl sm:text-2xl">
            <TriangleAlert size={34} strokeWidth={1.8} className="text-[#e05b4a]" aria-hidden="true" />
            {unanswered === 1 ? "Je hebt 1 vraag niet ingevuld." : `Je hebt ${unanswered} vragen niet ingevuld.`}
          </p>
        )}
        <div className="mt-9 grid grid-cols-6 gap-3 md:grid-cols-8 md:gap-4">
          {questions.map((item, index) => (
            <span
              key={item.id}
              className={clsx(
                "grid aspect-[1.35] place-items-center rounded-md text-xl font-semibold",
                isAnswered(item.id) ? "bg-[#4d7e91] text-white" : "border border-[#c8cfd4] bg-[#eceff1] text-slate-500",
              )}
            >
              {index + 1}
            </span>
          ))}
        </div>
        <div className="mt-10 flex justify-end">
          <button
            onClick={onSubmit}
            disabled={submitting}
            className="inline-flex min-w-44 items-center justify-center rounded-full bg-[#ff9944] px-8 py-3 font-medium tracking-[0.12em] text-slate-900 transition hover:bg-[#f18e3d] disabled:opacity-60"
          >
            {submitting ? "INLEVEREN..." : "DEFINITIEF INLEVEREN"}
          </button>
        </div>
      </section>
    </div>
  );
}
