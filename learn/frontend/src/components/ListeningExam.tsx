"use client";

import { useEffect, useRef, useState, type RefObject } from "react";
import clsx from "clsx";
import { Bookmark, Grid2X2 } from "lucide-react";
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
  QuestionPicker,
  TimeReminderDialog,
  TimeUpDialog,
  mediaProxyUrl,
} from "./DuoExamChrome";
import type { MockExamAttemptSummary, MockExamTakeDetail } from "@/lib/types";

const QUESTION_AUDIO_PLAYBACK_RATE = 1.15;

export function ListeningExam({
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
  const [volume, setVolume] = useState(1);
  const [mediaPlaying, setMediaPlaying] = useState(false);
  const [mediaPlaybackTime, setMediaPlaybackTime] = useState({ current: 0, duration: 0 });
  const [spokenItemKey, setSpokenItemKey] = useState<string | null>(null);
  const [questionPlaybackPlaying, setQuestionPlaybackPlaying] = useState(false);
  const [questionPlaybackProgress, setQuestionPlaybackProgress] = useState(0);
  const audioRef = useRef<HTMLAudioElement>(null);
  const videoRef = useRef<HTMLVideoElement>(null);
  const spokenAudioRef = useRef<HTMLAudioElement | null>(null);
  const questionPlaybackCancelRef = useRef(false);
  const timeUpSubmitRef = useRef(false);

  const question = questions[currentIndex];
  const passage = question?.passage_id ? passageById.get(question.passage_id) : undefined;
  const isLast = currentIndex === questions.length - 1;
  const hasMediaSource = Boolean(passage?.media_urls.some((media) => media.type === "video" || media.type === "audio"));
  const mediaProgress = mediaPlaybackTime.duration > 0
    ? Math.min(100, (mediaPlaybackTime.current / mediaPlaybackTime.duration) * 100)
    : 0;
  const incompleteQuestionIds = questions.filter((item) => !answers[item.id]).map((item) => item.id);

  function activeMediaPlayer() {
    return videoRef.current ?? audioRef.current;
  }

  async function toggleMediaPlayback() {
    const player = activeMediaPlayer();
    if (!player) return;
    if (player.paused) {
      stopQuestionPlayback();
      await player.play();
    } else {
      player.pause();
    }
  }

  function skipMedia(seconds: number) {
    const player = activeMediaPlayer();
    if (!player) return;
    player.currentTime = Math.max(0, Math.min(player.duration || Infinity, player.currentTime + seconds));
  }

  function requestSubmit() {
    if (incompleteQuestionIds.length > 0) {
      setShowIncompleteConfirmation(true);
      return;
    }
    onSubmit();
  }

  function resetPassagePlayback() {
    setMediaPlaybackTime({ current: 0, duration: 0 });
    const player = activeMediaPlayer();
    if (player) {
      player.pause();
      player.currentTime = 0;
      setMediaPlaying(false);
    }
  }

  function showQuestion(index: number) {
    resetPassagePlayback();
    stopQuestionPlayback();
    setCurrentIndex(index);
  }

  function stopQuestionPlayback() {
    questionPlaybackCancelRef.current = true;
    spokenAudioRef.current?.pause();
    spokenAudioRef.current = null;
    setSpokenItemKey(null);
    setQuestionPlaybackPlaying(false);
    setQuestionPlaybackProgress(0);
  }

  function skipQuestionPlayback(seconds: number) {
    const player = spokenAudioRef.current;
    if (!player) return;
    player.currentTime = Math.max(0, Math.min(player.duration || Infinity, player.currentTime + seconds));
  }

  async function playAudioClip(audioUrl: string, key: string, progressStart: number, progressEnd: number) {
    return new Promise<void>((resolve) => {
      const audio = new Audio(mediaProxyUrl("audio", audioUrl));
      audio.playbackRate = QUESTION_AUDIO_PLAYBACK_RATE;
      spokenAudioRef.current = audio;
      setSpokenItemKey(key);
      const syncProgress = () => {
        if (Number.isFinite(audio.duration) && audio.duration > 0) {
          const ratio = Math.min(1, audio.currentTime / audio.duration);
          setQuestionPlaybackProgress(progressStart + (progressEnd - progressStart) * ratio);
        }
      };
      audio.ontimeupdate = syncProgress;
      audio.onloadedmetadata = syncProgress;
      audio.onended = () => resolve();
      audio.onpause = () => resolve();
      audio.onerror = () => resolve();
      audio.play().catch(() => resolve());
    });
  }

  function updateCombinedOptionHighlight(audio: HTMLAudioElement) {
    const cue = question.option_audio_cues?.find((item) => audio.currentTime >= item.start && audio.currentTime <= item.end);
    setSpokenItemKey(cue ? `${question.id}:option:${cue.option_index}` : `${question.id}:question`);
  }

  async function playCombinedQuestionAndOptions(audioUrl: string) {
    return new Promise<void>((resolve) => {
      const audio = new Audio(mediaProxyUrl("audio", audioUrl));
      audio.playbackRate = QUESTION_AUDIO_PLAYBACK_RATE;
      spokenAudioRef.current = audio;
      setSpokenItemKey(`${question.id}:question`);
      const syncProgress = () => {
        if (Number.isFinite(audio.duration) && audio.duration > 0) {
          setQuestionPlaybackProgress(Math.min(100, (audio.currentTime / audio.duration) * 100));
        }
        updateCombinedOptionHighlight(audio);
      };
      audio.ontimeupdate = syncProgress;
      audio.onloadedmetadata = syncProgress;
      audio.onended = () => resolve();
      audio.onpause = () => resolve();
      audio.onerror = () => resolve();
      audio.play().catch(() => resolve());
    });
  }

  async function playQuestionAndOptions() {
    if (questionPlaybackPlaying) {
      stopQuestionPlayback();
      return;
    }
    activeMediaPlayer()?.pause();
    setMediaPlaying(false);
    if (question.question_options_audio_url) {
      questionPlaybackCancelRef.current = false;
      setQuestionPlaybackPlaying(true);
      setQuestionPlaybackProgress(0);
      await playCombinedQuestionAndOptions(question.question_options_audio_url);
      if (!questionPlaybackCancelRef.current) {
        spokenAudioRef.current = null;
        setSpokenItemKey(null);
        setQuestionPlaybackPlaying(false);
        setQuestionPlaybackProgress(100);
      }
      return;
    }
    const clips = [
      ...(question.question_audio_url ? [{ url: question.question_audio_url, key: `${question.id}:question` }] : []),
      ...((question.option_audio_urls ?? [])
        .map((url, index) => url ? { url, key: `${question.id}:option:${index}` } : null)
        .filter((clip): clip is { url: string; key: string } => clip !== null)),
    ];
    if (clips.length === 0) return;
    questionPlaybackCancelRef.current = false;
    setQuestionPlaybackPlaying(true);
    setQuestionPlaybackProgress(0);
    for (let index = 0; index < clips.length; index += 1) {
      if (questionPlaybackCancelRef.current) break;
      const clip = clips[index];
      await playAudioClip(clip.url, clip.key, (index / clips.length) * 100, ((index + 1) / clips.length) * 100);
    }
    if (!questionPlaybackCancelRef.current) {
      spokenAudioRef.current = null;
      setSpokenItemKey(null);
      setQuestionPlaybackPlaying(false);
      setQuestionPlaybackProgress(100);
    }
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
    stopQuestionPlayback();
    activeMediaPlayer()?.pause();
    setShowTimeUp(true);
  }, [showExamIntroduction, examSecondsLeft]);

  useEffect(() => {
    resetPassagePlayback();
    stopQuestionPlayback();
  }, [question?.id]);

  useEffect(() => {
    if (!hasMediaSource) return;
    let animationFrame = 0;
    const syncPlaybackTime = () => {
      const player = activeMediaPlayer();
      if (player && Number.isFinite(player.duration) && player.duration > 0) {
        setMediaPlaybackTime({ current: player.currentTime, duration: player.duration });
      }
      animationFrame = window.requestAnimationFrame(syncPlaybackTime);
    };
    animationFrame = window.requestAnimationFrame(syncPlaybackTime);
    return () => window.cancelAnimationFrame(animationFrame);
  }, [question?.id, hasMediaSource]);

  useEffect(() => {
    if (!hasMediaSource || showExamIntroduction) return;
    void activeMediaPlayer()?.play().catch(() => setMediaPlaying(false));
  }, [question?.id, hasMediaSource, showExamIntroduction]);

  useEffect(() => {
    const player = activeMediaPlayer();
    if (player) player.volume = volume;
    if (spokenAudioRef.current) spokenAudioRef.current.volume = volume;
  }, [volume, question?.id]);

  useEffect(() => {
    stopQuestionPlayback();
  }, [question?.id]);

  useEffect(() => () => {
    spokenAudioRef.current?.pause();
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
          <ListeningExamIntroduction exam={exam} attempts={attempts} examId={examId} />
        ) : (
          <div className="grid h-full min-h-0 gap-4 lg:grid-cols-2">
            <section className="min-h-0 overflow-y-auto border border-slate-200 bg-white px-7 py-6 text-slate-900 shadow-sm">
              <div className="flex items-start justify-between gap-6">
                <div className="min-w-0 flex-1">
                  {passage?.title && <h1 className="text-2xl font-normal leading-tight sm:text-3xl">{passage.title}</h1>}
                </div>
                {hasMediaSource && (
                  <div className="shrink-0">
                    <DuoPlaybackControls mediaPlaying={mediaPlaying} mediaProgress={mediaProgress} onSkip={skipMedia} onToggle={toggleMediaPlayback} />
                  </div>
                )}
              </div>
              {passage ? (
                <>
                  <ListeningPassageMedia mediaUrls={passage.media_urls} videoRef={videoRef} audioRef={audioRef} onPlayStateChange={setMediaPlaying} onPlaybackTimeChange={setMediaPlaybackTime} onEnded={() => void playQuestionAndOptions()} />
                  <p className="mt-6 max-w-3xl whitespace-pre-wrap text-xl leading-8">{listeningDisplayPrompt(passage)}</p>
                </>
              ) : (
                <p className="mt-6 text-xl text-slate-700">Luister naar het fragment en beantwoord de vraag.</p>
              )}
            </section>

            <section className="min-h-0 overflow-y-auto border border-slate-200 bg-white px-7 py-6 text-slate-900 shadow-sm">
              <div className="flex items-start justify-between gap-5">
                <h2 className="min-w-0 flex-1 whitespace-pre-wrap text-2xl font-normal leading-tight sm:text-3xl">{question.question_text}</h2>
                {(question.question_options_audio_url || question.question_audio_url || question.option_audio_urls?.some(Boolean)) && (
                  <div className="shrink-0">
                    <DuoPlaybackControls mediaPlaying={questionPlaybackPlaying} mediaProgress={questionPlaybackProgress} onSkip={skipQuestionPlayback} onToggle={() => void playQuestionAndOptions()} />
                  </div>
                )}
              </div>
              {question.question_type === "multiple_choice" && question.options ? (
                <div className="mt-9 space-y-4">
                  {question.options.map((option, index) => {
                    const selected = answers[question.id] === option;
                    const optionImageUrl = question.option_media_urls?.[index];
                    const optionAudioKey = `${question.id}:option:${index}`;
                    const optionPlaying = spokenItemKey === optionAudioKey;
                    return (
                      <div key={`${question.id}-${option}`} role="button" tabIndex={0} onClick={() => onAnswerChange(question.id, option)} onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") onAnswerChange(question.id, option); }} className={clsx("flex w-full cursor-pointer items-center gap-5 rounded-[0.2rem] border-2 px-5 py-4 text-left text-lg leading-7 transition", optionPlaying ? "border-[#ff9944] bg-[#fff7ed] text-slate-950" : selected ? "border-[#2f5b96] bg-[#2f5b96] text-white" : "border-[#d7dce0] bg-white text-slate-950 hover:border-[#9aa8b4]")}>
                        <span className={clsx("h-7 w-7 shrink-0 rounded-full border-2", selected ? "border-white bg-white ring-[6px] ring-inset ring-[#ff9944]" : "border-[#9aa8b4] bg-white")} aria-hidden="true" />
                        <span className={clsx("shrink-0 text-xl font-medium", selected && !optionPlaying ? "text-white" : "text-slate-900")}>{String.fromCharCode(65 + index)}</span>
                        <span className="min-w-0 flex-1">
                          {!optionImageUrl && option}
                          {optionImageUrl && <img src={mediaProxyUrl("image", optionImageUrl)} alt={option} className="block aspect-[4/3] max-h-44 w-full object-cover" />}
                        </span>
                      </div>
                    );
                  })}
                </div>
              ) : (
                <textarea className="mt-8 min-h-40 w-full border border-slate-300 bg-blue-50 p-4 text-base outline-none focus:border-[#2f5b96]" value={answers[question.id] ?? ""} onChange={(event) => onAnswerChange(question.id, event.target.value)} />
              )}
            </section>
          </div>
        )}

        {submitError && <p className="mt-5 text-red-600">{submitError}</p>}
      </main>

      <ExamFooter
        onPrevious={showExamIntroduction ? undefined : () => showQuestion(Math.max(0, currentIndex - 1))}
        previousDisabled={currentIndex === 0}
        primaryLabel={showExamIntroduction ? "Start ›" : isLast ? (submitting ? "Inleveren..." : "Inleveren") : "Volgende ›"}
        onPrimary={showExamIntroduction ? () => setShowExamIntroduction(false) : isLast ? requestSubmit : () => showQuestion(Math.min(questions.length - 1, currentIndex + 1))}
        primaryDisabled={submitting && isLast}
        badge={showExamIntroduction ? null : `${currentIndex + 1} / ${questions.length}`}
      >
        {!showExamIntroduction && (
          <>
            <button onClick={() => setQuestionPickerOpen((open) => !open)} className="grid h-10 w-10 place-items-center rounded-md transition hover:bg-white/10" title="Kies een vraag" aria-label="Kies een vraag"><Grid2X2 size={26} strokeWidth={1.8} /></button>
            <button onClick={() => setBookmarkedQuestionIds((ids) => ids.includes(question.id) ? ids.filter((id) => id !== question.id) : [...ids, question.id])} className={clsx("grid h-10 w-10 place-items-center rounded-md transition", bookmarkedQuestionIds.includes(question.id) ? "bg-[#e8863c] text-slate-950" : "hover:bg-white/10")} title="Markeer vraag" aria-label="Markeer vraag"><Bookmark size={26} strokeWidth={1.8} fill={bookmarkedQuestionIds.includes(question.id) ? "currentColor" : "none"} /></button>
            {questionPickerOpen && <QuestionPicker questions={questions} answers={answers} currentIndex={currentIndex} bookmarkedQuestionIds={bookmarkedQuestionIds} onClose={() => setQuestionPickerOpen(false)} onSelect={(index) => { showQuestion(index); setQuestionPickerOpen(false); }} />}
          </>
        )}
      </ExamFooter>

      {showIncompleteConfirmation && <IncompleteDialog count={incompleteQuestionIds.length} onCancel={() => setShowIncompleteConfirmation(false)} onConfirm={() => { setShowIncompleteConfirmation(false); onSubmit(); }} />}
      {showTimeReminder && <TimeReminderDialog onClose={() => setShowTimeReminder(false)} />}
      {showTimeUp && <TimeUpDialog questions={questions} isAnswered={(id) => Boolean(answers[id])} submitting={submitting} onSubmit={onSubmit} />}
    </div>
  );
}

function ListeningExamIntroduction({ exam, attempts, examId }: { exam: MockExamTakeDetail; attempts: MockExamAttemptSummary[]; examId: string }) {
  return (
    <IntroLayout
      left={
        <>
          <IntroHeading>Welkom bij het oefenexamen Luisteren A2.</IntroHeading>
          <IntroBody>
            <p>U moet in dit oefenexamen {exam.total_questions} vragen beantwoorden.</p>
            <p>U hoort bij elke vraag een fragment. Lees eerst de vraag.</p>
            <p>Wilt u met het examen beginnen, klik dan op &lsquo;start&rsquo;</p>
          </IntroBody>
          <IntroNote>Dit oefenexamen is gemaakt voor luistertraining en volgt de indeling van het DUO oefenexamen.</IntroNote>
        </>
      }
      right={<IntroSidePanel exam={exam} />}
    />
  );
}

function ListeningPassageMedia({
  mediaUrls,
  videoRef,
  audioRef,
  onPlayStateChange,
  onPlaybackTimeChange,
  onEnded,
}: {
  mediaUrls: { type: string; url: string }[];
  videoRef: RefObject<HTMLVideoElement>;
  audioRef: RefObject<HTMLAudioElement>;
  onPlayStateChange: (playing: boolean) => void;
  onPlaybackTimeChange: (time: { current: number; duration: number }) => void;
  onEnded?: () => void;
}) {
  const video = mediaUrls.find((media) => media.type === "video");
  const audio = mediaUrls.find((media) => media.type === "audio");
  const images = mediaUrls.filter((media) => media.type === "image");
  return (
    <div className="mt-6 space-y-5">
      {video && <video ref={videoRef} autoPlay className="aspect-video w-full max-w-[34rem] bg-slate-950 object-cover" src={mediaProxyUrl("video", video.url)} onCanPlay={(event) => { void event.currentTarget.play().catch(() => onPlayStateChange(false)); }} onLoadedMetadata={(event) => onPlaybackTimeChange({ current: event.currentTarget.currentTime, duration: event.currentTarget.duration || 0 })} onTimeUpdate={(event) => onPlaybackTimeChange({ current: event.currentTarget.currentTime, duration: event.currentTarget.duration || 0 })} onPlay={() => onPlayStateChange(true)} onPause={() => onPlayStateChange(false)} onEnded={() => { onPlayStateChange(false); onEnded?.(); }} />}
      {images.length > 0 && <div className="grid gap-5 sm:grid-cols-2">{images.map((image, index) => <img key={image.url} src={mediaProxyUrl("image", image.url)} alt={`Afbeelding ${index + 1}`} className="aspect-video max-h-[18rem] w-full object-cover" />)}</div>}
      {audio && <audio ref={audioRef} autoPlay src={mediaProxyUrl("audio", audio.url)} onCanPlay={(event) => { onPlaybackTimeChange({ current: event.currentTarget.currentTime, duration: event.currentTarget.duration || 0 }); void event.currentTarget.play().catch(() => onPlayStateChange(false)); }} onLoadedMetadata={(event) => onPlaybackTimeChange({ current: event.currentTarget.currentTime, duration: event.currentTarget.duration || 0 })} onDurationChange={(event) => onPlaybackTimeChange({ current: event.currentTarget.currentTime, duration: event.currentTarget.duration || 0 })} onTimeUpdate={(event) => onPlaybackTimeChange({ current: event.currentTarget.currentTime, duration: event.currentTarget.duration || 0 })} onPlay={(event) => { onPlayStateChange(true); onPlaybackTimeChange({ current: event.currentTarget.currentTime, duration: event.currentTarget.duration || 0 }); }} onPause={() => onPlayStateChange(false)} onEnded={(event) => { onPlayStateChange(false); onPlaybackTimeChange({ current: event.currentTarget.duration || 0, duration: event.currentTarget.duration || 0 }); onEnded?.(); }} />}
      {!video && !audio && images.length === 0 && <p className="text-xl text-slate-700">Het luisterfragment wordt hier afgespeeld.</p>}
    </div>
  );
}

function listeningDisplayPrompt(passage: MockExamTakeDetail["passages"][number]): string {
  if (passage.display_prompt_nl?.trim()) return passage.display_prompt_nl;
  const mediaWord = passage.passage_type === "video" ? "video" : "fragment";
  return `U hoort een ${mediaWord}: ${passage.title || "dit fragment"}.\n\nLees eerst de vraag.\nLuister daarna naar het ${mediaWord}.`;
}

