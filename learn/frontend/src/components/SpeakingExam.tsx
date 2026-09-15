"use client";

import { useEffect, useRef, useState } from "react";
import clsx from "clsx";
import { Bookmark, Grid2X2, Info, LoaderCircle, Mic, MicOff, Pause, Play, Square, Trash2, X } from "lucide-react";
import { DuoPlaybackControls } from "./DuoPlaybackControls";
import { ExamFooter, ExamHeader, IntroBody, IntroHeading, IntroLayout, IntroNote, IntroSidePanel, TimeUpDialog, mediaProxyUrl } from "./DuoExamChrome";
import type { MockExamAttemptSummary, MockExamTakeDetail } from "@/lib/types";

export function SpeakingExam({
  exam,
  examId,
  attempts,
  onAnswerChange,
  onRecordingReady,
  onSubmit,
  submitting,
  submitError,
}: {
  exam: MockExamTakeDetail;
  examId: string;
  attempts: MockExamAttemptSummary[];
  onAnswerChange: (questionId: string, answer: string) => void;
  onRecordingReady: (questionId: string, recording: Blob) => void;
  onSubmit: () => void;
  submitting: boolean;
  submitError: string | null;
}) {
  const questions = exam.questions.slice().sort((a, b) => a.order_index - b.order_index);
  const passageById = new Map(exam.passages.map((passage) => [passage.id, passage]));
  const [currentIndex, setCurrentIndex] = useState(0);
  const [showExamIntroduction, setShowExamIntroduction] = useState(true);
  const [partIntroduction, setPartIntroduction] = useState<number | null>(() => questions[0]?.part_number ?? null);
  const [recordingQuestionId, setRecordingQuestionId] = useState<string | null>(null);
  const [secondsLeft, setSecondsLeft] = useState<number | null>(null);
  const [recordings, setRecordings] = useState<Record<string, string>>({});
  const [recordingError, setRecordingError] = useState<string | null>(null);
  const [deleteConfirmId, setDeleteConfirmId] = useState<string | null>(null);
  const [showIncompleteConfirmation, setShowIncompleteConfirmation] = useState(false);
  const [playingRecordingId, setPlayingRecordingId] = useState<string | null>(null);
  const [recordingPlaybackTime, setRecordingPlaybackTime] = useState<Record<string, { current: number; duration: number }>>({});
  const [questionPickerOpen, setQuestionPickerOpen] = useState(false);
  const [bookmarkedQuestionIds, setBookmarkedQuestionIds] = useState<string[]>([]);
  const [mediaPlaying, setMediaPlaying] = useState(false);
  const [mediaPlaybackTime, setMediaPlaybackTime] = useState({ current: 0, duration: 0 });
  const [microphoneLevel, setMicrophoneLevel] = useState(0);
  const [examSecondsLeft, setExamSecondsLeft] = useState(exam.time_limit_minutes * 60);
  const [showExamTime, setShowExamTime] = useState(false);
  const [showTimeReminder, setShowTimeReminder] = useState(false);
  const [showTimeUp, setShowTimeUp] = useState(false);
  const [microphonePermission, setMicrophonePermission] = useState<"checking" | "granted" | "denied">("checking");
  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const streamRef = useRef<MediaStream | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const meterFrameRef = useRef<number | null>(null);
  const timeUpSubmitRef = useRef(false);
  const recordingUrlsRef = useRef<string[]>([]);
  const videoRef = useRef<HTMLVideoElement>(null);
  const audioRef = useRef<HTMLAudioElement>(null);

  const question = questions[currentIndex];
  const passage = question?.passage_id ? passageById.get(question.passage_id) : undefined;
  const onePicturePrompt = passage?.passage_type === "one_picture"
    ? splitOnePicturePrompt(question?.question_text ?? "")
    : null;
  const twoPicturePrompt = passage?.passage_type === "two_picture"
    ? splitPicturePrompt(question?.question_text ?? "")
    : null;
  const threePicturePrompt = passage?.passage_type === "three_picture"
    ? splitPicturePrompt(question?.question_text ?? "")
    : null;
  const threePictureInstruction = threePicturePrompt
    ? splitAllPicturesInstruction(threePicturePrompt.instruction)
    : null;
  const isRecording = recordingQuestionId === question?.id;
  const isLast = currentIndex === questions.length - 1;
  const hasMediaSource = Boolean(passage?.media_urls.some((media) => media.type === "video" || media.type === "audio"));
  const mediaProgress = mediaPlaybackTime.duration > 0
    ? Math.min(100, (mediaPlaybackTime.current / mediaPlaybackTime.duration) * 100)
    : 0;
  const incompleteQuestionIds = questions.filter((item) => !recordings[item.id]).map((item) => item.id);

  function requestSubmit() {
    if (incompleteQuestionIds.length > 0) {
      setShowIncompleteConfirmation(true);
      return;
    }
    onSubmit();
  }

  function showQuestion(index: number) {
    activeMediaPlayer()?.pause();
    document.querySelectorAll<HTMLAudioElement>("audio").forEach((audio) => audio.pause());
    setCurrentIndex(index);
    setPartIntroduction(null);
  }

  function showPartIntroduction(partNumber: number | null) {
    const firstQuestionIndex = questions.findIndex((item) => item.part_number === partNumber);
    if (firstQuestionIndex < 0 || partNumber === null) return;
    activeMediaPlayer()?.pause();
    document.querySelectorAll<HTMLAudioElement>("audio").forEach((audio) => audio.pause());
    setCurrentIndex(firstQuestionIndex);
    setPartIntroduction(partNumber);
  }

  function goNext() {
    if (partIntroduction !== null) {
      setPartIntroduction(null);
      return;
    }
    const nextIndex = Math.min(questions.length - 1, currentIndex + 1);
    const nextPart = questions[nextIndex]?.part_number;
    activeMediaPlayer()?.pause();
    document.querySelectorAll<HTMLAudioElement>("audio").forEach((audio) => audio.pause());
    setCurrentIndex(nextIndex);
    if (nextPart !== question.part_number) setPartIntroduction(nextPart ?? null);
  }

  function goPrevious() {
    if (partIntroduction !== null) {
      const previousIndex = Math.max(0, currentIndex - 1);
      activeMediaPlayer()?.pause();
      document.querySelectorAll<HTMLAudioElement>("audio").forEach((audio) => audio.pause());
      setCurrentIndex(previousIndex);
      setPartIntroduction(null);
      return;
    }
    if (currentIndex === 0) {
      activeMediaPlayer()?.pause();
      document.querySelectorAll<HTMLAudioElement>("audio").forEach((audio) => audio.pause());
      setPartIntroduction(question.part_number);
      return;
    }
    const previousIndex = Math.max(0, currentIndex - 1);
    const previousPart = questions[previousIndex]?.part_number;
    if (previousPart !== question.part_number) {
      activeMediaPlayer()?.pause();
      document.querySelectorAll<HTMLAudioElement>("audio").forEach((audio) => audio.pause());
      setCurrentIndex(questions.findIndex((item) => item.part_number === previousPart));
      setPartIntroduction(previousPart ?? null);
      return;
    }
    activeMediaPlayer()?.pause();
    document.querySelectorAll<HTMLAudioElement>("audio").forEach((audio) => audio.pause());
    setCurrentIndex(previousIndex);
  }

  function activeMediaPlayer() {
    return videoRef.current ?? audioRef.current;
  }

  async function toggleMediaPlayback() {
    const player = activeMediaPlayer();
    if (!player) return;
    if (player.paused) await player.play();
    else player.pause();
  }

  function skipMedia(seconds: number) {
    const player = activeMediaPlayer();
    if (!player) return;
    player.currentTime = Math.max(0, Math.min(player.duration || Infinity, player.currentTime + seconds));
  }

  function stopRecording() {
    if (recorderRef.current?.state === "recording") recorderRef.current.stop();
  }

  function stopMicrophoneMeter() {
    if (meterFrameRef.current !== null) window.cancelAnimationFrame(meterFrameRef.current);
    meterFrameRef.current = null;
    void audioContextRef.current?.close();
    audioContextRef.current = null;
    setMicrophoneLevel(0);
  }

  function startMicrophoneMeter(stream: MediaStream) {
    stopMicrophoneMeter();
    const audioContext = new AudioContext();
    const analyser = audioContext.createAnalyser();
    analyser.fftSize = 256;
    audioContext.createMediaStreamSource(stream).connect(analyser);
    const samples = new Uint8Array(analyser.fftSize);
    audioContextRef.current = audioContext;
    const updateLevel = () => {
      analyser.getByteTimeDomainData(samples);
      const average = samples.reduce((total, sample) => total + Math.abs(sample - 128), 0) / samples.length;
      setMicrophoneLevel(Math.min(1, average / 24));
      meterFrameRef.current = window.requestAnimationFrame(updateLevel);
    };
    updateLevel();
  }

  function deleteRecording(questionId: string) {
    if (recordings[questionId]) {
      URL.revokeObjectURL(recordings[questionId]);
      setRecordings((current) => {
        const updated = { ...current };
        delete updated[questionId];
        return updated;
      });
      onAnswerChange(questionId, "");
    }
    setDeleteConfirmId(null);
  }

  async function requestMicrophonePermission() {
    if (!navigator.mediaDevices?.getUserMedia) {
      setMicrophonePermission("denied");
      return false;
    }
    setMicrophonePermission("checking");
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      stream.getTracks().forEach((track) => track.stop());
      setMicrophonePermission("granted");
      return true;
    } catch {
      setMicrophonePermission("denied");
      return false;
    }
  }

  async function startRecording() {
    if (!question || isRecording) return;
    setRecordingError(null);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      setMicrophonePermission("granted");
      const recorder = new MediaRecorder(stream);
      chunksRef.current = [];
      streamRef.current = stream;
      startMicrophoneMeter(stream);
      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) chunksRef.current.push(event.data);
      };
      recorder.onstop = () => {
        stream.getTracks().forEach((track) => track.stop());
        stopMicrophoneMeter();
        const recording = new Blob(chunksRef.current, { type: recorder.mimeType });
        const recordingUrl = URL.createObjectURL(recording);
        recordingUrlsRef.current.push(recordingUrl);
        setRecordings((current) => ({ ...current, [question.id]: recordingUrl }));
        onRecordingReady(question.id, recording);
        onAnswerChange(question.id, "audio-recording");
        setRecordingQuestionId(null);
        setSecondsLeft(null);
        recorderRef.current = null;
        streamRef.current = null;
      };
      recorderRef.current = recorder;
      recorder.start();
      setRecordingQuestionId(question.id);
      setSecondsLeft(60);
    } catch {
      setMicrophonePermission("denied");
      setRecordingError("De microfoon is niet beschikbaar. Geef toestemming en probeer opnieuw.");
    }
  }

  useEffect(() => {
    void requestMicrophonePermission();
  }, []);

  useEffect(() => {
    if (!recordingQuestionId || secondsLeft === null) return;
    if (secondsLeft === 0) {
      stopRecording();
      return;
    }
    const timer = window.setTimeout(() => setSecondsLeft((seconds) => Math.max(0, (seconds ?? 0) - 1)), 1000);
    return () => window.clearTimeout(timer);
  }, [recordingQuestionId, secondsLeft]);

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
    if (isRecording) {
      stopRecording();
      return;
    }
    timeUpSubmitRef.current = true;
    setShowTimeUp(true);
  }, [showExamIntroduction, examSecondsLeft, isRecording]);

  useEffect(() => {
    setMediaPlaybackTime({ current: 0, duration: 0 });
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
    if (!hasMediaSource) return;
    void activeMediaPlayer()?.play().catch(() => setMediaPlaying(false));
  }, [question?.id, hasMediaSource]);

  useEffect(() => () => {
    if (recorderRef.current?.state === "recording") recorderRef.current.stop();
    streamRef.current?.getTracks().forEach((track) => track.stop());
    stopMicrophoneMeter();
    recordingUrlsRef.current.forEach((url) => URL.revokeObjectURL(url));
  }, []);

  if (!question) return null;

  return (
    <div className="-mx-4 -my-8 min-h-[70vh] bg-[#f5f6f8] sm:-mx-6">
      <ExamHeader
        title={exam.title}
        backHref={`/mock-exams/${exam.section}`}
        timer={showExamIntroduction ? null : { minutesLeft: Math.ceil(examSecondsLeft / 60), visible: showExamTime, onToggle: () => setShowExamTime((show) => !show) }}
      />

      <main className={clsx("px-4 py-6 sm:px-6", showExamIntroduction ? "w-full" : "mx-auto max-w-4xl")}>
        {showExamIntroduction ? (
          <SpeakingExamIntroduction exam={exam} />
        ) : partIntroduction !== null ? (
          <SpeakingPartIntroduction partNumber={partIntroduction} />
        ) : (
          <>
        <section className="border border-slate-200 bg-white px-7 py-6 text-slate-900 shadow-sm">
          {onePicturePrompt?.setup && (
            <div className="mb-5 flex items-center justify-between gap-4">
              <p className="max-w-2xl text-[0.95rem] leading-[1.6]">
                {onePicturePrompt.setup}
              </p>
            </div>
          )}
          {twoPicturePrompt?.setup && (
            <p className="mb-5 max-w-2xl text-[0.95rem] leading-[1.6]">
              {twoPicturePrompt.setup}
            </p>
          )}
          {threePicturePrompt?.setup && (
            <p className="mb-5 max-w-2xl text-[0.95rem] leading-[1.6]">
              {threePicturePrompt.setup}
            </p>
          )}
          {passage?.content_nl && passage.passage_type !== "video" && passage.passage_type === "text" && (
            <p className="mb-6 max-w-2xl whitespace-pre-wrap text-[0.95rem] leading-[1.6]">{passage.content_nl}</p>
          )}
          {passage?.passage_type === "video" ? (
            <div className="flex items-start gap-3 sm:gap-5">
              <div className="min-w-0 flex-1"><SpeakingPassageMedia passageType={passage.passage_type} mediaUrls={passage.media_urls} videoRef={videoRef} audioRef={audioRef} onPlayStateChange={setMediaPlaying} onPlaybackTimeChange={setMediaPlaybackTime} /></div>
              <DuoPlaybackControls compact mediaPlaying={mediaPlaying} mediaProgress={mediaProgress} onSkip={skipMedia} onToggle={toggleMediaPlayback} />
            </div>
          ) : passage ? (
            <div className={clsx("gap-3 sm:gap-5", hasMediaSource && "flex items-start")}>
              <div className={clsx(hasMediaSource && "min-w-0 flex-1")}><SpeakingPassageMedia passageType={passage.passage_type} mediaUrls={passage.media_urls} videoRef={videoRef} audioRef={audioRef} onPlayStateChange={setMediaPlaying} onPlaybackTimeChange={setMediaPlaybackTime} /></div>
              {hasMediaSource && <DuoPlaybackControls compact mediaPlaying={mediaPlaying} mediaProgress={mediaProgress} onSkip={skipMedia} onToggle={toggleMediaPlayback} />}
            </div>
          ) : null}
          {passage?.passage_type !== "video" && (
            <p className="mt-5 max-w-2xl whitespace-pre-wrap text-[0.95rem] leading-[1.6]">
              {passage?.passage_type === "one_picture"
                ? onePicturePrompt?.instruction
                : passage?.passage_type === "two_picture"
                  ? twoPicturePrompt?.instruction
                  : passage?.passage_type === "three_picture"
                    ? threePictureInstruction?.task
                : question.question_text}
            </p>
          )}
          {passage?.passage_type === "three_picture" && threePictureInstruction?.reminder && (
            <p className="mt-5 text-[0.95rem] leading-[1.6]">{threePictureInstruction.reminder}</p>
          )}
          {passage?.passage_type === "one_picture" && !question.question_text.endsWith("Gebruik het plaatje.") && (
            <p className="mt-5 text-[0.95rem] leading-[1.6]">Gebruik het plaatje.</p>
          )}
          {passage?.passage_type === "two_picture" && <p className="mt-5 text-[0.95rem] leading-[1.6]">Kies <u>een</u> van de plaatjes.</p>}
        </section>

        <section className="mt-6 border border-slate-200 bg-white px-7 py-6 text-slate-900 shadow-sm">
          <div>
            {microphonePermission === "checking" ? (
              <div className="flex items-center gap-3 border border-slate-300 bg-slate-50 p-5 text-lg text-slate-800" role="status">
                <LoaderCircle className="animate-spin text-[#21446e]" size={24} aria-hidden="true" />
                Microfoontoestemming wordt gevraagd.
              </div>
            ) : microphonePermission === "denied" ? (
              <div className="border border-slate-300 bg-slate-50 p-5 text-lg leading-8 text-slate-900">
                <p>Toestemming om de microfoon te gebruiken is geweigerd. Geef toestemming om de microfoon te gebruiken en probeer opnieuw.</p>
                <button onClick={() => void requestMicrophonePermission()} className="mt-5 inline-flex items-center gap-3 border border-[#cd6b2a] bg-[#e8863c] px-5 py-3 font-semibold text-white hover:bg-[#dc7a30]">
                  <MicOff size={19} /> Microfoon toestaan
                </button>
              </div>
            ) : null}
            {microphonePermission === "granted" && (
              <>
                {recordingError && <p className="mt-3 text-sm text-red-700">{recordingError}</p>}
                {isRecording || recordings[question.id] ? (
                  // Duo-style recording bar (when recording or already recorded)
                  <div className="relative mt-4 flex h-16 w-full max-w-[30rem] items-center rounded-[0.55rem] bg-[#2f5b96] px-6 text-white">
                    <div className="flex w-full items-center gap-4">
                      {recordings[question.id] && !isRecording ? (
                        // Playback controls when recording exists
                        <>
                          <button
                            onClick={() => setDeleteConfirmId(question.id)}
                            className="flex h-10 w-10 flex-shrink-0 items-center justify-center text-[#f1533f] transition hover:text-[#ff725f]"
                            title="Verwijder opname"
                          >
                            <Trash2 size={38} strokeWidth={2.75} />
                          </button>
                          <audio
                            src={recordings[question.id]}
                            onPlay={() => setPlayingRecordingId(question.id)}
                            onPause={() => setPlayingRecordingId(null)}
                            onTimeUpdate={(e) => {
                              const audio = e.currentTarget;
                              setRecordingPlaybackTime((prev) => ({
                                ...prev,
                                [question.id]: {
                                  current: audio.currentTime,
                                  duration: audio.duration || 0,
                                },
                              }));
                            }}
                            onLoadedMetadata={(e) => {
                              const audio = e.currentTarget;
                              setRecordingPlaybackTime((prev) => ({
                                ...prev,
                                [question.id]: {
                                  current: prev[question.id]?.current ?? 0,
                                  duration: audio.duration || 0,
                                },
                              }));
                            }}
                            style={{ display: "none" }}
                          />
                          <div className="flex flex-1 items-center gap-6">
                            <button
                              onClick={() => {
                                const audio = document.querySelector(`audio[src="${recordings[question.id]}"]`) as HTMLAudioElement;
                                if (audio) {
                                  if (audio.paused) {
                                    void audio.play();
                                  } else {
                                    audio.pause();
                                  }
                                }
                              }}
                              className="flex h-11 w-11 flex-shrink-0 items-center justify-center text-white transition hover:text-slate-200"
                              title={playingRecordingId === question.id ? "Pauze" : "Afspelen"}
                            >
                              {playingRecordingId === question.id ? (
                                <Pause size={31} fill="currentColor" />
                              ) : (
                                <Play size={36} fill="currentColor" />
                              )}
                            </button>

                            <span className="flex-shrink-0 whitespace-nowrap text-[2rem] font-light leading-none">
                              {String(Math.floor((recordingPlaybackTime[question.id]?.current ?? 0) / 60)).padStart(2, "0")}:
                              {String(Math.floor((recordingPlaybackTime[question.id]?.current ?? 0) % 60)).padStart(2, "0")}
                            </span>

                            {/* Progress bar */}
                            <div className="flex-1">
                              <input
                                type="range"
                                min="0"
                                max={recordingPlaybackTime[question.id]?.duration ?? 0}
                                value={recordingPlaybackTime[question.id]?.current ?? 0}
                                onChange={(e) => {
                                  const audio = document.querySelector(`audio[src="${recordings[question.id]}"]`) as HTMLAudioElement;
                                  if (audio) {
                                    audio.currentTime = parseFloat(e.currentTarget.value);
                                  }
                                }}
                                className="h-5 w-full cursor-pointer appearance-none bg-transparent [&::-webkit-slider-runnable-track]:h-5 [&::-webkit-slider-runnable-track]:bg-[#6689b9] [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:h-0 [&::-webkit-slider-thumb]:w-0"
                              />
                            </div>

                            <span className="flex-shrink-0 whitespace-nowrap text-[2rem] font-light leading-none">
                              {String(Math.floor((recordingPlaybackTime[question.id]?.duration ?? 0) / 60)).padStart(2, "0")}:
                              {String(Math.floor((recordingPlaybackTime[question.id]?.duration ?? 0) % 60)).padStart(2, "0")}
                            </span>
                          </div>

                        </>
                      ) : (
                        // Recording state
                        <>
                          <button
                            onClick={stopRecording}
                            className="flex h-11 w-11 flex-shrink-0 items-center justify-center rounded-full bg-[#f85232] hover:bg-[#ff6a4c] transition"
                            title="Stop opname"
                          >
                            {isRecording ? <Square size={20} fill="white" /> : <Mic size={20} />}
                          </button>

                          {/* Audio level visualization */}
                          <div className="flex h-12 w-6 flex-shrink-0 flex-col justify-center gap-0.5">
                            {Array.from({ length: 12 }).map((_, i) => (
                              <div
                                key={i}
                                className={clsx(
                                  "h-1 w-6 transition-all",
                                  isRecording && microphoneLevel >= (i + 1) / 12 ? "bg-emerald-400" : "bg-[#6385b5]"
                                )}
                              />
                            ))}
                          </div>

                          {/* Timer display */}
                          <div className="flex-1 text-center text-[2rem] font-light leading-none">
                            <span>
                              {String(Math.floor((secondsLeft ?? 0) / 60)).padStart(2, "0")}:
                              {String((secondsLeft ?? 0) % 60).padStart(2, "0")}
                            </span>
                            <span className="mx-2 text-xs opacity-75">/</span>
                            <span>01:00</span>
                          </div>
                        </>
                      )}
                    </div>
                    {deleteConfirmId === question.id && (
                      <div className="absolute left-16 top-[4.5rem] z-10 w-[45rem] bg-[#ff9944] px-6 py-5 text-slate-950 shadow-none">
                        <p className="text-[1.2rem] font-normal">Weet je zeker dat je de opname wilt verwijderen?</p>
                        <div className="mt-5 flex items-center gap-12">
                          <button onClick={() => setDeleteConfirmId(null)} className="rounded-full border-2 border-slate-900 bg-[#dfe5e9] px-6 py-3 text-lg tracking-[0.15em] text-slate-800 hover:bg-white">
                            ANNULEREN
                          </button>
                          <button onClick={() => deleteRecording(question.id)} className="text-lg tracking-[0.15em] text-slate-950 hover:opacity-70">
                            VERWIJDEREN
                          </button>
                        </div>
                      </div>
                    )}
                  </div>
                ) : (
                  // Duo-style recording bar (when idle)
                  <div className="mt-4 flex h-16 w-full max-w-[30rem] items-center gap-4 rounded-[0.55rem] bg-[#2f5b96] px-6 text-white">
                    <button
                      onClick={startRecording}
                      className="h-11 w-11 flex-shrink-0 rounded-full bg-[#f85232] transition hover:bg-[#ff6a4c]"
                      title="Start opname"
                    />

                    <div className="flex h-12 w-6 flex-shrink-0 flex-col justify-center gap-0.5" aria-hidden="true">
                      {Array.from({ length: 12 }).map((_, index) => (
                        <div key={index} className="h-1 w-6 bg-[#6385b5]" />
                      ))}
                    </div>

                    <span className="text-[2rem] font-light leading-none">00:00</span>
                    <div className="h-4 min-w-12 flex-1 bg-[#4b73a8]" aria-hidden="true" />
                    <span className="text-[2rem] font-light leading-none">01:00</span>
                  </div>
                )}
              </>
            )}
          </div>
        </section>
          </>
        )}

        {submitError && <p className="mt-5 text-red-600">{submitError}</p>}
      </main>

      <ExamFooter
        onPrevious={showExamIntroduction ? undefined : goPrevious}
        previousDisabled={(currentIndex === 0 && partIntroduction !== null) || isRecording}
        primaryLabel={showExamIntroduction ? "Start ›" : isLast && partIntroduction === null ? (submitting ? "Inleveren..." : "Inleveren") : "Volgende ›"}
        onPrimary={showExamIntroduction ? () => setShowExamIntroduction(false) : isLast && partIntroduction === null ? requestSubmit : goNext}
        primaryDisabled={isRecording || (submitting && isLast && partIntroduction === null)}
        badge={showExamIntroduction ? null : partIntroduction !== null ? "info" : `${currentIndex + 1} / ${questions.length}`}
      >
            {!showExamIntroduction && <>
            <button onClick={() => setQuestionPickerOpen((open) => !open)} disabled={isRecording} className="grid h-10 w-10 place-items-center rounded-md transition hover:bg-white/10" title="Kies een vraag" aria-label="Kies een vraag"><Grid2X2 size={26} strokeWidth={1.8} /><span className="sr-only">Kies een vraag</span></button>
            <button onClick={() => setBookmarkedQuestionIds((ids) => ids.includes(question.id) ? ids.filter((id) => id !== question.id) : [...ids, question.id])} className={clsx("grid h-10 w-10 place-items-center rounded-md transition", bookmarkedQuestionIds.includes(question.id) ? "bg-[#e8863c] text-slate-950" : "hover:bg-white/10")} title="Markeer vraag" aria-label="Markeer vraag"><Bookmark size={26} strokeWidth={1.8} fill={bookmarkedQuestionIds.includes(question.id) ? "currentColor" : "none"} /><span className="sr-only">Markeer vraag</span></button>
            {questionPickerOpen && (
              <div className="fixed inset-0 z-50 grid place-items-center bg-slate-950/55 p-4 backdrop-blur-sm" role="dialog" aria-modal="true" aria-labelledby="exam-overview-title">
                <section className="w-full max-w-3xl rounded bg-white px-7 py-6 text-slate-900 shadow-2xl">
                  <header className="flex items-center justify-between gap-6">
                    <h2 id="exam-overview-title" className="text-xl font-normal">Overzicht examen</h2>
                    <button onClick={() => setQuestionPickerOpen(false)} className="grid h-8 w-8 place-items-center rounded-full transition hover:bg-slate-100 focus-visible:bg-slate-100" title="Sluiten" aria-label="Sluiten"><X size={22} strokeWidth={1.75} /></button>
                  </header>
                  <div className="mt-7 flex flex-wrap gap-2">
                    {questions.map((item, index) => (
                      <div key={item.id} className="contents">
                        {(index === 0 || item.part_number !== questions[index - 1]?.part_number) && (
                          <button onClick={() => { showPartIntroduction(item.part_number); setQuestionPickerOpen(false); }} className={clsx("grid h-10 w-14 place-items-center rounded transition hover:brightness-95", partIntroduction === item.part_number ? "bg-[#e8863c] text-slate-950" : "bg-[#4d7e91] text-white")} title={`${speakingPartLabel(item.part_number)}: informatie`} aria-label={`${speakingPartLabel(item.part_number)}: informatie`}><Info size={18} strokeWidth={2.2} aria-hidden="true" /></button>
                        )}
                        <button onClick={() => { showQuestion(index); setQuestionPickerOpen(false); }} className={clsx("relative grid h-10 w-14 place-items-center rounded text-sm font-semibold transition hover:brightness-95", index === currentIndex && partIntroduction === null ? "bg-[#e8863c]" : recordings[item.id] ? "bg-[#4d7e91] text-white" : "bg-[#dfe3e6]")}>
                          {index + 1}
                          {bookmarkedQuestionIds.includes(item.id) && <Bookmark className="absolute right-0.5 top-0.5 text-[#ffe6c7]" size={12} fill="currentColor" aria-label="Bladwijzer" />}
                        </button>
                      </div>
                    ))}
                  </div>
                  <ul className="mt-7 flex flex-wrap items-center gap-x-8 gap-y-3 text-sm">
                    <li className="flex items-center gap-2"><span className="h-4 w-4 rounded-sm bg-[#e8863c]" />Geselecteerd</li>
                    <li className="flex items-center gap-2"><span className="h-4 w-4 rounded-sm bg-[#dfe3e6]" />Onbeantwoord</li>
                    <li className="flex items-center gap-2"><span className="h-4 w-4 rounded-sm bg-[#4d7e91]" />Beantwoord</li>
                    <li className="flex items-center gap-2"><Bookmark className="text-[#f0c391]" size={18} fill="currentColor" />Bladwijzers</li>
                  </ul>
                </section>
              </div>
            )}
            </>}
      </ExamFooter>
      {showIncompleteConfirmation && (
        <div className="fixed inset-0 z-50 grid place-items-center bg-slate-950/40 p-4" role="dialog" aria-modal="true" aria-labelledby="speaking-incomplete-title">
          <div className="w-full max-w-md border border-slate-300 bg-white p-6 shadow-xl">
            <h2 id="speaking-incomplete-title" className="text-xl font-bold">Niet alle antwoorden zijn ingevuld</h2>
            <p className="mt-3 text-slate-700">
              {incompleteQuestionIds.length === 1
                ? "Er is nog 1 opdracht niet ingevuld. Deze opdracht staat rood gemarkeerd."
                : `Er zijn nog ${incompleteQuestionIds.length} opdrachten niet ingevuld. Deze opdrachten staan rood gemarkeerd.`}
            </p>
            <p className="mt-2 text-sm text-slate-600">Wilt u toch inleveren?</p>
            <div className="mt-6 flex justify-end gap-3">
              <button onClick={() => setShowIncompleteConfirmation(false)} className="btn-secondary">Terug naar examen</button>
              <button onClick={() => { setShowIncompleteConfirmation(false); onSubmit(); }} className="btn-primary">Toch inleveren</button>
            </div>
          </div>
        </div>
      )}
      {showTimeReminder && (
        <div className="fixed inset-0 z-50 grid place-items-center bg-slate-950/40 p-4" role="dialog" aria-modal="true" aria-labelledby="time-reminder-title">
          <div className="w-full max-w-md border border-slate-300 bg-white p-6 shadow-xl">
            <h2 id="time-reminder-title" className="text-xl font-bold">Nog 15 minuten</h2>
            <p className="mt-3 text-slate-700">U heeft nog 15 minuten om het examen af te maken.</p>
            <div className="mt-6 flex justify-end"><button onClick={() => setShowTimeReminder(false)} className="btn-primary">Verder met examen</button></div>
          </div>
        </div>
      )}
      {showTimeUp && (
        <TimeUpDialog
          questions={questions}
          isAnswered={(id) => Boolean(recordings[id])}
          submitting={submitting}
          onSubmit={onSubmit}
        />
      )}
      {submitting && (
        <div className="fixed inset-0 z-[60] grid place-items-center bg-slate-950/55 p-4" role="status" aria-live="polite">
          <div className="w-full max-w-md border border-slate-300 bg-white p-7 text-center shadow-xl">
            <LoaderCircle className="mx-auto animate-spin text-[#2b4a78]" size={36} aria-hidden="true" />
            <h2 className="mt-4 text-xl font-bold text-slate-950">Your recordings are being reviewed</h2>
            <p className="mt-3 text-slate-700">We are analysing your spoken answers and preparing your feedback. Your results should be ready within 5 minutes.</p>
            <p className="mt-3 text-sm text-slate-600">You can return later and view completed feedback from View attempts.</p>
            <p className="mt-5 border-t border-slate-200 pt-4 text-left text-sm leading-6 text-slate-600">The real speaking exam is assessed by people. We provide practice feedback on how you did, so this score and feedback may differ from the official exam result.</p>
          </div>
        </div>
      )}
    </div>
  );
}

function SpeakingExamIntroduction({ exam }: { exam: MockExamTakeDetail }) {
  return (
    <IntroLayout
      left={
        <>
          <IntroHeading>Welkom bij het oefenexamen Spreken A2.</IntroHeading>
          <IntroBody>
            <p>Het examen heeft vier soorten vragen:</p>
            <p>1. vragen met een video</p>
            <p>2. vragen met 1 plaatje</p>
            <p>3. vragen met 2 plaatjes</p>
            <p>4. vragen met 3 plaatjes</p>
            <p className="pt-4">U mag {exam.time_limit_minutes} minuten over het examen doen. Veel succes!</p>
            <p>Klik op &lsquo;start&rsquo; om onderdeel 1 te starten.</p>
          </IntroBody>
          <IntroNote>Dit oefenexamen is gemaakt voor spreektraining en volgt de indeling van het DUO oefenexamen.</IntroNote>
        </>
      }
      right={<IntroSidePanel exam={exam} />}
    />
  );
}

function SpeakingPartIntroduction({ partNumber }: { partNumber: number }) {
  const description = speakingPartDescription(partNumber);
  return (
    <section className="border border-slate-200 bg-white px-7 py-6 text-slate-900 shadow-sm">
      {partNumber > 1 && (
        <>
          <p className="text-[0.95rem] font-bold leading-[1.6]">Einde onderdeel {partNumber - 1}</p>
          <p className="mt-5 max-w-2xl text-[0.95rem] leading-[1.6]">U bent klaar met onderdeel {partNumber - 1}.</p>
          <p className="mt-2 max-w-2xl text-[0.95rem] leading-[1.6]">Wilt u nog terug naar de vragen? Klik dan op de nummers van de vragen.</p>
        </>
      )}
      <p className={clsx("text-[0.95rem] font-bold leading-[1.6]", partNumber > 1 && "mt-8")}>{speakingPartLabel(partNumber)}</p>
      <p className="mt-5 max-w-2xl whitespace-pre-line text-[0.95rem] leading-[1.6]">{description}</p>
    </section>
  );
}

function speakingPartLabel(partNumber: number | null): string {
  if (partNumber === 1) return "Onderdeel 1 - vragen met een video";
  if (partNumber === 2) return "Onderdeel 2 - vragen met 1 plaatje";
  if (partNumber === 3) return "Onderdeel 3 - vragen met 2 plaatjes";
  if (partNumber === 4) return "Onderdeel 4 - vragen met 3 plaatjes";
  return "Spreekopdracht";
}

function speakingPartDescription(partNumber: number): string {
  if (partNumber === 1) return "U gaat naar vier video's kijken. Een man of vrouw vraagt iets in elke video. U moet antwoord geven.";
  if (partNumber === 2) return "U ziet vier vragen met één plaatje. Geef antwoord op de vragen. Gebruik steeds het plaatje.";
  if (partNumber === 3) return "U ziet vier vragen met twee plaatjes. Geef antwoord op de vragen. U kiest steeds één plaatje.";
  if (partNumber === 4) return "U ziet vier vragen met drie plaatjes. Geef antwoord op de vraag. Gebruik steeds alles plaatjes. Vertel iets bij elk plaatje.";
  return "Lees de opdracht goed. Daarna spreekt u uw antwoord in.";
}

function splitOnePicturePrompt(questionText: string): { setup: string; instruction: string } {
  return splitPicturePrompt(questionText);
}

function splitPicturePrompt(questionText: string): { setup: string; instruction: string } {
  const match = questionText.match(/^([\s\S]+?[.!?])\s+([\s\S]+)$/);
  if (!match) return { setup: "", instruction: questionText };
  return { setup: match[1], instruction: match[2] };
}

function splitAllPicturesInstruction(instruction: string): { task: string; reminder: string } {
  const match = instruction.match(/^([\s\S]*?)\s*((?:Gebruik|Vertel iets over) alle plaatjes\.)$/);
  if (!match) return { task: instruction, reminder: "" };
  return { task: match[1].trim(), reminder: match[2] };
}

function SpeakingPassageMedia({
  passageType,
  mediaUrls,
  videoRef,
  audioRef,
  onPlayStateChange,
  onPlaybackTimeChange,
}: {
  passageType: MockExamTakeDetail["passages"][number]["passage_type"];
  mediaUrls: { type: string; url: string }[];
  videoRef: React.RefObject<HTMLVideoElement>;
  audioRef: React.RefObject<HTMLAudioElement>;
  onPlayStateChange: (playing: boolean) => void;
  onPlaybackTimeChange: (time: { current: number; duration: number }) => void;
}) {
  const video = mediaUrls.find((media) => media.type === "video");
  const audio = mediaUrls.find((media) => media.type === "audio");
  const images = mediaUrls.filter((media) => media.type === "image");
  if (!video && !audio && images.length === 0 && passageType === "video") return <p className="text-sm text-slate-500">De video wordt hier getoond.</p>;
  const multiplePictures = passageType === "two_picture" || passageType === "three_picture";
  const imageColumns = passageType === "three_picture" ? "grid-cols-1 sm:grid-cols-3" : passageType === "two_picture" ? "grid-cols-1 sm:grid-cols-2" : "grid-cols-1";
  return (
    <div className="space-y-3">
      {video ? <video ref={videoRef} autoPlay className="aspect-[4/3] h-auto max-h-[14.75rem] w-full max-w-[20rem] bg-slate-900 object-cover" src={mediaProxyUrl("video", video.url)} onCanPlay={(event) => { void event.currentTarget.play().catch(() => onPlayStateChange(false)); }} onLoadedMetadata={(event) => onPlaybackTimeChange({ current: event.currentTarget.currentTime, duration: event.currentTarget.duration || 0 })} onTimeUpdate={(event) => onPlaybackTimeChange({ current: event.currentTarget.currentTime, duration: event.currentTarget.duration || 0 })} onPlay={() => onPlayStateChange(true)} onPause={() => onPlayStateChange(false)} onEnded={() => onPlayStateChange(false)} /> : images.length > 0 && <div className={clsx("grid", imageColumns, passageType === "three_picture" ? "gap-1 max-w-[47rem]" : passageType === "two_picture" ? "gap-4 max-w-[44rem]" : "gap-4 max-w-[25.5rem]")}>{images.map((image, index) => <img key={image.url} src={mediaProxyUrl("image", image.url)} alt={`Afbeelding ${index + 1}`} className="aspect-[4/3] w-full object-cover" />)}</div>}
      {audio && <audio ref={audioRef} autoPlay src={mediaProxyUrl("audio", audio.url)} onCanPlay={(event) => { onPlaybackTimeChange({ current: event.currentTarget.currentTime, duration: event.currentTarget.duration || 0 }); void event.currentTarget.play().catch(() => onPlayStateChange(false)); }} onLoadedMetadata={(event) => onPlaybackTimeChange({ current: event.currentTarget.currentTime, duration: event.currentTarget.duration || 0 })} onDurationChange={(event) => onPlaybackTimeChange({ current: event.currentTarget.currentTime, duration: event.currentTarget.duration || 0 })} onProgress={(event) => onPlaybackTimeChange({ current: event.currentTarget.currentTime, duration: event.currentTarget.duration || 0 })} onTimeUpdate={(event) => onPlaybackTimeChange({ current: event.currentTarget.currentTime, duration: event.currentTarget.duration || 0 })} onPlay={(event) => { onPlayStateChange(true); onPlaybackTimeChange({ current: event.currentTarget.currentTime, duration: event.currentTarget.duration || 0 }); }} onPause={() => onPlayStateChange(false)} onEnded={(event) => { onPlayStateChange(false); onPlaybackTimeChange({ current: event.currentTarget.duration || 0, duration: event.currentTarget.duration || 0 }); }} />}
    </div>
  );
}
