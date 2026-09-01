"use client";
import { useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import clsx from "clsx";
import { Clock3, LoaderCircle, Mail, Mic, Minus, Printer, Send, Square, X } from "lucide-react";
import { callApi, formatDate } from "@/lib/format";
import { PassageContent } from "./PassageContent";
import type {
  MockExamAttemptResult,
  MockExamAttemptSummary,
  MockExamTakeDetail,
} from "@/lib/types";

// Colors match the official DUO/Optimum Assessment exam player exactly (navy header/footer, orange accent).
const NAVY = "bg-[#2b4a78]";
const NAVY_TEXT = "text-[#2b4a78]";
const ORANGE = "bg-[#e8863c] hover:bg-[#dc7a30]";
const WRITING_STUDY_TARGET = 25;

const WRITING_CRITERION_LABELS: Record<string, string> = {
  adequacy_understandability: "Adequacy & understandability",
  grammar: "Grammar",
  spelling: "Spelling",
  vocabulary: "Vocabulary",
  cohesion: "Cohesion",
};

function AnswerLines({ count }: { count: number }) {
  return (
    <div className="mt-5 space-y-6" aria-hidden="true">
      {Array.from({ length: count }, (_, index) => (
        <div key={index} className="border-b border-slate-400" />
      ))}
    </div>
  );
}

function emailRecipient(questionText: string): string | null {
  const match = questionText.match(/^E-mail aan\s+([^\n]+)/im) ?? questionText.match(/U schrijft een e-mail aan\s+([^\.]+)\./i);
  return match?.[1]?.trim() ?? null;
}

function noteRecipient(questionText: string): string | null {
  const match = questionText.match(/^Briefje voor\s+([^\n]+)/im) ?? questionText.match(/Schrijf een briefje voor\s+([^\.]+)\./i);
  return match?.[1]?.replace(/^(collega|mijn collega)\s+/i, "").trim() ?? null;
}

function emailAddress(recipient: string): string {
  const localPart = recipient
    .replace(/^(docent|mevrouw|meneer|collega)\s+/i, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, ".")
    .replace(/^\.|\.$/g, "");
  return `${localPart || "ontvanger"}@mail.nl`;
}

function emailSubject(questionText: string): string {
  const firstLine = questionText.split("\n").find((line) => line.trim())?.trim() ?? "Bericht";
  return /^e-?mail aan /i.test(firstLine) ? "Bericht" : firstLine;
}

function emailTemplate(recipient: string) {
  return {
    greeting: `Beste ${recipient},`,
    closing: "Vriendelijke groet,",
  };
}

function emailBody(answer: string, greeting: string, closing: string): string {
  if (!answer) return "";
  const withoutGreeting = answer.startsWith(greeting) ? answer.slice(greeting.length).trimStart() : answer;
  return withoutGreeting.endsWith(closing) ? withoutGreeting.slice(0, -closing.length).trimEnd() : withoutGreeting;
}

function EmailPaperAnswer({
  questionId,
  recipient,
  subject,
  answer,
  answerLines,
  disabled,
  onChange,
}: {
  questionId: string;
  recipient: string;
  subject: string;
  answer: string;
  answerLines: number;
  disabled: boolean;
  onChange: (answer: string) => void;
}) {
  const { greeting, closing } = emailTemplate(recipient);
  return (
    <div className="mt-5 overflow-hidden border-2 border-[#2563eb] bg-white text-base leading-6">
      <div className="flex h-8 items-center border-b border-slate-300 px-2 text-slate-500">
        <Mail size={14} className="text-[#2563eb]" aria-hidden="true" />
        <div className="ml-auto flex items-center gap-4">
          <Minus size={15} aria-hidden="true" />
          <Square size={13} aria-hidden="true" />
          <X size={15} aria-hidden="true" />
        </div>
      </div>
      <div className="grid grid-cols-[6.25rem_minmax(0,1fr)] border-b border-slate-300">
        <div className="flex min-h-28 flex-col items-center justify-center border-r border-slate-300 text-sm font-semibold text-slate-700">
          <Send size={23} className="mb-2 text-[#2563eb]" aria-hidden="true" />
          Verzenden
        </div>
        <div className="min-w-0 p-2 text-sm">
          <div className="grid grid-cols-[5.5rem_minmax(0,1fr)] gap-x-2 gap-y-1">
            <span className="border border-slate-400 bg-slate-50 px-2 py-1 text-center font-semibold">Aan...</span>
            <span className="border border-slate-400 px-2 py-1 font-semibold">{emailAddress(recipient)}</span>
            <span className="border border-slate-400 bg-slate-50 px-2 py-1 text-center font-semibold">CC...</span>
            <span className="border border-slate-400 px-2 py-1" />
            <span className="col-start-1 font-semibold text-slate-700">Onderwerp</span>
            <span className="border border-slate-400 px-2 py-1 font-semibold">{subject}</span>
          </div>
        </div>
      </div>
      <div className="flex min-h-[20rem] flex-col border-x border-slate-300 p-4">
        <p>{greeting}</p>
        <label htmlFor={`answer-${questionId}`} className="sr-only">Uw e-mailtekst</label>
        <textarea
          id={`answer-${questionId}`}
          className="my-3 min-h-32 flex-1 resize-y bg-[repeating-linear-gradient(to_bottom,#eff6ff_0,#eff6ff_29px,#bfdbfe_30px)] px-0 py-1 leading-6 outline-none focus:bg-blue-100 disabled:cursor-not-allowed disabled:bg-slate-100"
          rows={Math.max(4, answerLines - 4)}
          value={emailBody(answer, greeting, closing)}
          onChange={(event) => onChange(`${greeting}\n\n${event.target.value.trim()}\n\n${closing}`)}
          placeholder="Schrijf hier uw e-mail."
          disabled={disabled}
        />
        <p>{closing}</p>
      </div>
    </div>
  );
}

function isWijkkrantTask(questionText: string): boolean {
  return /U krijgt elke week een wijkkrant/i.test(questionText);
}

function formLines(content: string): string[] {
  return content.split("\n").map((line) => line.trim()).filter(Boolean);
}

function isFormHeading(line: string, nextLine: string | undefined): boolean {
  return line.toLowerCase() === "persoonsgegevens" || /^O\s+/i.test(nextLine ?? "");
}

function isLongFormField(label: string): boolean {
  return /^(wat |waarom |hoe |in welke |omschrijving)/i.test(label);
}

function FormPaperAnswer({
  questionId,
  content,
  answer,
  disabled,
  onChange,
}: {
  questionId: string;
  content: string;
  answer: string;
  disabled: boolean;
  onChange: (answer: string) => void;
}) {
  const lines = formLines(content);
  const title = lines.shift() ?? "Formulier";
  const hasPersonalDetailsHeading = lines.some((line) => line.toLowerCase() === "persoonsgegevens");
  const [values, setValues] = useState<Record<string, string>>(() => {
    const parsed: Record<string, string> = {};
    for (const line of answer.split("\n")) {
      const separator = line.indexOf(": ");
      if (separator > 0) parsed[line.slice(0, separator)] = line.slice(separator + 2);
    }
    return parsed;
  });
  const update = (key: string, value: string) => {
    const next = { ...values, [key]: value };
    setValues(next);
    onChange(Object.entries(next).filter(([, item]) => item).map(([label, item]) => `${label}: ${item}`).join("\n"));
  };

  return (
    <div className="mt-5 border border-slate-600 bg-white text-base">
      <p className="border-b border-slate-600 px-3 py-1 text-lg font-bold">{title}</p>
      {!hasPersonalDetailsHeading && (
        <p className="border-b border-slate-600 bg-slate-300 px-3 py-1 text-lg font-bold">Persoonsgegevens</p>
      )}
      <div>
        {lines.map((line, index) => {
          const nextLine = lines[index + 1];
          const inlineOptions = line.match(/^(?:\d+\.\s*)?(.+?)\s+O\s+(.+?)\s*\/\s*O\s+(.+)$/i);
          const option = line.match(/^(?:O|0)\s+(.+)/i);
          const label = line.replace(/^\d+\.\s*/, "").replace(/:$/, "");
          const field = !inlineOptions && !option && !isFormHeading(label, nextLine);
          if (inlineOptions) {
            const [, fieldLabel, firstOption, secondOption] = inlineOptions;
            return (
              <div key={`${line}-${index}`} className="grid grid-cols-[minmax(10rem,38%)_1fr] border-b border-slate-600">
                <span className="border-r border-slate-600 px-3 py-1">{fieldLabel}</span>
                <div className="flex items-center gap-5 px-3 py-1">
                  {[firstOption, secondOption].map((choice) => (
                    <label key={choice} className="flex items-center gap-2">
                      <input className="accent-[#2563eb]" type="radio" name={`${questionId}-${fieldLabel}`} checked={values[fieldLabel] === choice} onChange={() => update(fieldLabel, choice)} disabled={disabled} />
                      {choice}
                    </label>
                  ))}
                </div>
              </div>
            );
          }
          if (option) {
            const label = option[1];
            return (
              <label key={`${line}-${index}`} className="flex items-center gap-2 border-b border-slate-300 px-3 py-1">
                <input className="accent-[#2563eb]" type="checkbox" checked={values[label] === "ja"} onChange={(event) => update(label, event.target.checked ? "ja" : "")} disabled={disabled} />
                {label}
              </label>
            );
          }
          if (!field) {
            return <p key={`${line}-${index}`} className="border-b border-slate-600 bg-slate-300 px-3 py-1 text-lg font-bold">{line}</p>;
          }
          if (isLongFormField(label)) {
            return (
              <label key={`${line}-${index}`} className="block border-b border-slate-600 px-3 py-2">
                <span className="block">{label}</span>
                <textarea
                  className="mt-2 min-h-24 w-full resize-y border border-slate-300 bg-blue-50 p-2 leading-6 outline-none focus:border-[#2b4a78] focus:bg-blue-100 disabled:bg-slate-100"
                  rows={label.toLowerCase().startsWith("omschrijving") ? 5 : 3}
                  value={values[label] ?? ""}
                  onChange={(event) => update(label, event.target.value)}
                  disabled={disabled}
                />
              </label>
            );
          }
          return (
            <label key={`${line}-${index}`} className="grid grid-cols-[minmax(10rem,38%)_1fr] border-b border-slate-600">
              <span className="border-r border-slate-600 px-3 py-1">{label}</span>
              <input
                className="min-w-0 bg-blue-50 px-3 py-1 outline-none focus:bg-blue-100 disabled:bg-slate-100"
                value={values[label] ?? ""}
                onChange={(event) => update(label, event.target.value)}
                disabled={disabled}
              />
            </label>
          );
        })}
      </div>
    </div>
  );
}

function CompositionPaperAnswer({
  questionId,
  topic,
  answer,
  answerLines,
  disabled,
  onChange,
}: {
  questionId: string;
  topic: string;
  answer: string;
  answerLines: number;
  disabled: boolean;
  onChange: (answer: string) => void;
}) {
  return (
    <div className="mt-5">
      <p className="mb-3 text-lg font-bold">Dit is mijn tekst over {topic.toLowerCase()}:</p>
      <label htmlFor={`answer-${questionId}`} className="sr-only">Uw tekst</label>
      <textarea
        id={`answer-${questionId}`}
        className="min-h-72 w-full resize-y border border-slate-600 bg-blue-50 p-3 text-base leading-6 outline-none focus:border-[#2b4a78] focus:bg-blue-100 focus:ring-1 focus:ring-[#2b4a78] disabled:cursor-not-allowed disabled:bg-slate-100"
        rows={Math.max(10, answerLines)}
        value={answer}
        onChange={(event) => onChange(event.target.value)}
        disabled={disabled}
      />
    </div>
  );
}

function NotePaperAnswer({
  questionId,
  recipient,
  answer,
  answerLines,
  disabled,
  onChange,
}: {
  questionId: string;
  recipient: string;
  answer: string;
  answerLines: number;
  disabled: boolean;
  onChange: (answer: string) => void;
}) {
  const greeting = `Hallo ${recipient},`;
  const closing = "Alvast bedankt!\nGroeten,";
  return (
    <div className="mt-5 border border-slate-600 bg-white p-4 text-base leading-6">
      <p>{greeting}</p>
      <label htmlFor={`answer-${questionId}`} className="sr-only">Uw briefje</label>
      <textarea
        id={`answer-${questionId}`}
        className="my-3 w-full resize-y bg-[repeating-linear-gradient(to_bottom,#eff6ff_0,#eff6ff_29px,#bfdbfe_30px)] px-0 py-1 leading-6 outline-none focus:bg-blue-100 disabled:cursor-not-allowed disabled:bg-slate-100"
        rows={Math.max(5, answerLines - 3)}
        value={emailBody(answer, greeting, closing)}
        onChange={(event) => onChange(`${greeting}\n\n${event.target.value.trim()}\n\n${closing}`)}
        placeholder="Schrijf hier uw briefje."
        disabled={disabled}
      />
      <p className="whitespace-pre-wrap">{closing}</p>
    </div>
  );
}

function WritingPaper({
  exam,
  answers,
  onAnswerChange,
  onSubmit,
  submitting,
  submitError,
}: {
  exam: MockExamTakeDetail;
  answers: Record<string, string>;
  onAnswerChange: (questionId: string, answer: string) => void;
  onSubmit: () => void;
  submitting: boolean;
  submitError: string | null;
}) {
  const passageById = new Map(exam.passages.map((passage) => [passage.id, passage]));
  const questions = exam.questions.slice().sort((a, b) => a.order_index - b.order_index);
  const [started, setStarted] = useState(false);
  const [secondsLeft, setSecondsLeft] = useState(exam.time_limit_minutes * 60);
  const [showIncompleteConfirmation, setShowIncompleteConfirmation] = useState(false);
  const timeUp = started && secondsLeft === 0;
  const minutes = Math.floor(secondsLeft / 60);
  const seconds = secondsLeft % 60;
  const incompleteQuestionIds = questions
    .filter((question) => !answers[question.id]?.trim())
    .map((question) => question.id);

  function requestSubmit() {
    if (incompleteQuestionIds.length > 0) {
      setShowIncompleteConfirmation(true);
      return;
    }
    onSubmit();
  }

  useEffect(() => {
    if (!started || secondsLeft <= 0) return;
    const timer = window.setTimeout(() => setSecondsLeft((current) => Math.max(0, current - 1)), 1000);
    return () => window.clearTimeout(timer);
  }, [started, secondsLeft]);

  return (
    <div className="mx-auto max-w-3xl space-y-5 print:max-w-none">
      <div className="flex items-center justify-between print:hidden">
        <Link href={`/mock-exams/${exam.section}`} className="text-sm text-brand-700 hover:underline">
          ← Terug naar schrijfexamens
        </Link>
        <div className="flex items-center gap-3">
          {started && (
            <div className={clsx("flex items-center gap-2 border px-3 py-2 text-sm font-semibold tabular-nums", timeUp ? "border-red-700 bg-red-50 text-red-800" : "border-[#2b4a78] text-[#2b4a78]")}>
              <Clock3 size={16} aria-hidden="true" />
              {String(minutes).padStart(2, "0")}:{String(seconds).padStart(2, "0")}
            </div>
          )}
          <button onClick={() => window.print()} className="btn-secondary gap-2 text-sm">
            <Printer size={16} aria-hidden="true" />
            Print examen
          </button>
        </div>
      </div>

      <article className="border border-slate-500 bg-white px-7 py-8 text-slate-950 shadow-sm print:border-0 print:px-10 print:py-0 print:shadow-none">
        <header className="border-b-2 border-slate-950 pb-5">
          <p className="text-sm font-semibold uppercase">Inburgeringsexamen A2 · Oefenmateriaal</p>
          <h1 className="mt-1 text-3xl font-bold">Schrijven</h1>
          <div className="mt-4 flex justify-between text-sm font-semibold">
            <span>{exam.title}</span>
            <span>Tijd: {exam.time_limit_minutes} minuten</span>
          </div>
          <p className="mt-4 text-sm leading-6">
            Maak alle vier de opdrachten in het Nederlands. De digitale antwoordvakken lijken op de schrijfruimte op het examenpapier.
          </p>
        </header>

        {!started ? (
          <div className="my-12 border-y border-slate-400 py-8 text-center print:hidden">
            <p className="text-lg font-semibold">U heeft {exam.time_limit_minutes} minuten voor 4 opdrachten.</p>
            <p className="mt-2 text-sm text-slate-600">Na het starten loopt de tijd. Uw antwoorden zijn daarna niet meer te wijzigen.</p>
            <button onClick={() => setStarted(true)} className={clsx(ORANGE, "mt-6 rounded-full px-6 py-3 font-semibold text-white")}>
              Start schrijfexamen
            </button>
          </div>
        ) : (
          <>
            {timeUp && (
              <div className="mt-6 border border-red-500 bg-red-50 px-4 py-3 text-sm font-semibold text-red-900 print:hidden">
                De tijd is om. Uw antwoorden zijn afgesloten. Lever uw examen in voor feedback.
              </div>
            )}

        <div className="mt-7 space-y-10">
          {questions.map((question, index) => {
            const passage = question.passage_id ? passageById.get(question.passage_id) : undefined;
            const answerLines = index === 0 ? 6 : index === 1 ? 8 : index === 2 ? 11 : 14;
            const recipient = emailRecipient(question.question_text);
            const noteTo = noteRecipient(question.question_text);
            const wijkkrantTask = isWijkkrantTask(question.question_text);
            const topic = question.question_text.split("\n").find((line) => line.trim())?.trim() ?? "deze tekst";
            const incomplete = incompleteQuestionIds.includes(question.id);
            return (
              <section key={question.id} className={clsx("break-inside-avoid border-b border-slate-300 pb-8 last:border-b-0", incomplete && "border border-red-500 bg-red-50 px-4 pt-4")}>
                <h2 className="text-lg font-bold">Opdracht {index + 1}</h2>
                {passage && (
                  <div className="mt-4 border border-slate-500 px-4 py-3">
                    {passage.title && <p className="mb-2 font-semibold">{passage.title}</p>}
                    <PassageMedia mediaUrls={passage.media_urls} />
                    <PassageContent text={passage.content_nl} />
                  </div>
                )}
                <p className="mt-4 whitespace-pre-wrap leading-6">{question.question_text}</p>
                <div className="mt-5 print:hidden">
                  {passage?.passage_type === "text" ? (
                    <FormPaperAnswer
                      questionId={question.id}
                      content={passage.content_nl}
                      answer={answers[question.id] ?? ""}
                      disabled={timeUp}
                      onChange={(answer) => onAnswerChange(question.id, answer)}
                    />
                  ) : recipient ? (
                    <EmailPaperAnswer
                      questionId={question.id}
                      recipient={recipient}
                      subject={emailSubject(question.question_text)}
                      answer={answers[question.id] ?? ""}
                      answerLines={answerLines}
                      disabled={timeUp}
                      onChange={(answer) => onAnswerChange(question.id, answer)}
                    />
                  ) : wijkkrantTask ? (
                    <CompositionPaperAnswer
                      questionId={question.id}
                      topic={topic}
                      answer={answers[question.id] ?? ""}
                      answerLines={answerLines}
                      disabled={timeUp}
                      onChange={(answer) => onAnswerChange(question.id, answer)}
                    />
                  ) : noteTo ? (
                    <NotePaperAnswer
                      questionId={question.id}
                      recipient={noteTo}
                      answer={answers[question.id] ?? ""}
                      answerLines={answerLines}
                      disabled={timeUp}
                      onChange={(answer) => onAnswerChange(question.id, answer)}
                    />
                  ) : (
                    <>
                      <label htmlFor={`answer-${question.id}`} className="text-sm font-semibold">
                        Uw antwoord
                      </label>
                      <textarea
                        id={`answer-${question.id}`}
                        className="mt-2 w-full resize-y border border-slate-500 bg-[repeating-linear-gradient(to_bottom,#eff6ff_0,#eff6ff_29px,#bfdbfe_30px)] p-3 text-base leading-6 outline-none focus:border-[#2b4a78] focus:bg-blue-100 focus:ring-1 focus:ring-[#2b4a78] disabled:cursor-not-allowed disabled:bg-slate-100"
                        rows={answerLines}
                        value={answers[question.id] ?? ""}
                        onChange={(event) => onAnswerChange(question.id, event.target.value)}
                        placeholder="Schrijf hier uw antwoord in het Nederlands."
                        disabled={timeUp}
                      />
                    </>
                  )}
                </div>
                <div className="hidden print:block">
                  <AnswerLines count={answerLines} />
                </div>
              </section>
            );
          })}
        </div>
        <div className="mt-8 border-t border-slate-300 pt-6 print:hidden">
          {submitError && <p className="mb-3 text-sm text-red-700">{submitError}</p>}
          {submitting && (
            <div className="mb-4 flex items-center gap-3 border border-blue-200 bg-blue-50 px-4 py-3 text-sm text-blue-950" role="status">
              <LoaderCircle className="animate-spin text-[#2563eb]" size={20} aria-hidden="true" />
              <div>
                <p className="font-semibold">Your answers are being reviewed by AI</p>
                <p className="mt-1 text-blue-800">Your results will be available shortly.</p>
              </div>
            </div>
          )}
          <button
            onClick={requestSubmit}
            disabled={submitting}
            className="btn-primary disabled:cursor-not-allowed disabled:opacity-50"
          >
            {submitting ? "Verifying with AI..." : "Stuur antwoorden voor feedback"}
          </button>
        </div>
        {showIncompleteConfirmation && (
          <div className="fixed inset-0 z-50 grid place-items-center bg-slate-950/40 p-4 print:hidden" role="dialog" aria-modal="true" aria-labelledby="incomplete-title">
            <div className="w-full max-w-md border border-slate-300 bg-white p-6 shadow-xl">
              <h2 id="incomplete-title" className="text-xl font-bold">Niet alle antwoorden zijn ingevuld</h2>
              <p className="mt-3 text-slate-700">
                {incompleteQuestionIds.length === 1
                  ? "Er is nog 1 opdracht niet ingevuld. Deze opdracht staat rood gemarkeerd."
                  : `Er zijn nog ${incompleteQuestionIds.length} opdrachten niet ingevuld. Deze opdrachten staan rood gemarkeerd.`}
              </p>
              <p className="mt-2 text-sm text-slate-600">Wilt u toch inleveren?</p>
              <div className="mt-6 flex justify-end gap-3">
                <button onClick={() => setShowIncompleteConfirmation(false)} className="btn-secondary">Terug naar examen</button>
                <button onClick={onSubmit} className="btn-primary">Toch inleveren</button>
              </div>
            </div>
          </div>
        )}
          </>
        )}
      </article>
    </div>
  );
}

function SpeakingExam({
  exam,
  onAnswerChange,
  onSubmit,
  submitting,
  submitError,
}: {
  exam: MockExamTakeDetail;
  onAnswerChange: (questionId: string, answer: string) => void;
  onSubmit: () => void;
  submitting: boolean;
  submitError: string | null;
}) {
  const questions = exam.questions.slice().sort((a, b) => a.order_index - b.order_index);
  const passageById = new Map(exam.passages.map((passage) => [passage.id, passage]));
  const [currentIndex, setCurrentIndex] = useState(0);
  const [recordingQuestionId, setRecordingQuestionId] = useState<string | null>(null);
  const [secondsLeft, setSecondsLeft] = useState<number | null>(null);
  const [recordings, setRecordings] = useState<Record<string, string>>({});
  const [recordingError, setRecordingError] = useState<string | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const streamRef = useRef<MediaStream | null>(null);
  const recordingUrlsRef = useRef<string[]>([]);

  const question = questions[currentIndex];
  const passage = question?.passage_id ? passageById.get(question.passage_id) : undefined;
  const isRecording = recordingQuestionId === question?.id;
  const isLast = currentIndex === questions.length - 1;

  function stopRecording() {
    if (recorderRef.current?.state === "recording") recorderRef.current.stop();
  }

  async function startRecording() {
    if (!question || isRecording) return;
    setRecordingError(null);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const recorder = new MediaRecorder(stream);
      chunksRef.current = [];
      streamRef.current = stream;
      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) chunksRef.current.push(event.data);
      };
      recorder.onstop = () => {
        stream.getTracks().forEach((track) => track.stop());
        const recordingUrl = URL.createObjectURL(new Blob(chunksRef.current, { type: recorder.mimeType }));
        recordingUrlsRef.current.push(recordingUrl);
        setRecordings((current) => ({ ...current, [question.id]: recordingUrl }));
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
      setRecordingError("De microfoon is niet beschikbaar. Geef toestemming en probeer opnieuw.");
    }
  }

  useEffect(() => {
    if (!recordingQuestionId || secondsLeft === null) return;
    if (secondsLeft === 0) {
      stopRecording();
      return;
    }
    const timer = window.setTimeout(() => setSecondsLeft((seconds) => Math.max(0, (seconds ?? 0) - 1)), 1000);
    return () => window.clearTimeout(timer);
  }, [recordingQuestionId, secondsLeft]);

  useEffect(() => () => {
    if (recorderRef.current?.state === "recording") recorderRef.current.stop();
    streamRef.current?.getTracks().forEach((track) => track.stop());
    recordingUrlsRef.current.forEach((url) => URL.revokeObjectURL(url));
  }, []);

  if (!question) return null;

  return (
    <div className="-mx-4 -my-8 min-h-[70vh]">
      <div className={clsx(NAVY, "flex items-center justify-between px-6 py-4 text-white")}>
        <div className="flex items-center gap-3">
          <Link href={`/mock-exams/${exam.section}`} className="text-sm text-white/80 hover:text-white">←</Link>
          <span className="font-medium">{exam.title}</span>
        </div>
        <span className={clsx("rounded border px-3 py-1 text-sm font-semibold", isRecording ? "border-[#e8863c] bg-[#e8863c]" : "border-white/40")}>
          {isRecording && secondsLeft !== null ? `Antwoordtijd: ${secondsLeft}s` : "Antwoordtijd: 1 min"}
        </span>
      </div>

      <div className="grid gap-6 p-6 md:grid-cols-2">
        <div className="card max-h-[60vh] overflow-y-auto p-6">
          <p className="mb-3 text-sm font-semibold text-slate-500">Deel {question.part_number} · Vraag {currentIndex + 1} van {questions.length}</p>
          {passage?.title && <p className="font-semibold">{passage.title}</p>}
          {passage && <PassageMedia mediaUrls={passage.media_urls} />}
          {passage?.content_nl && <div className="mt-2"><PassageContent text={passage.content_nl} /></div>}
        </div>

        <div className="card flex min-h-[26rem] flex-col p-6">
          <p className="whitespace-pre-wrap text-lg leading-8 text-slate-800">{question.question_text}</p>
          <div className="mt-auto pt-6">
            {recordings[question.id] ? (
              <div className="border border-emerald-300 bg-emerald-50 p-4 text-sm text-emerald-900">
                <p className="font-semibold">Uw opname is klaar.</p>
                <audio controls className="mt-3 w-full" src={recordings[question.id]} />
              </div>
            ) : (
              <p className="text-sm text-slate-600">Klik op de microfoon en spreek uw antwoord in. De opname stopt automatisch na 1 minuut.</p>
            )}
            {recordingError && <p className="mt-3 text-sm text-red-700">{recordingError}</p>}
            <button onClick={isRecording ? stopRecording : startRecording} className={clsx("mt-4 inline-flex items-center gap-2 rounded-full px-5 py-3 font-semibold text-white", isRecording ? "bg-red-700 hover:bg-red-800" : ORANGE)}>
              {isRecording ? <Square size={17} fill="currentColor" /> : <Mic size={17} />}
              {isRecording ? "Stop opname" : recordings[question.id] ? "Neem opnieuw op" : "Start antwoord"}
            </button>
          </div>
        </div>
      </div>

      {submitError && <p className="px-6 text-red-600">{submitError}</p>}
      <div className={clsx(NAVY, "flex items-center justify-between px-6 py-4")}>
        <button onClick={() => setCurrentIndex((index) => Math.max(0, index - 1))} disabled={currentIndex === 0 || isRecording} className="rounded-full bg-white/20 px-5 py-2.5 font-semibold text-white disabled:opacity-40">← Vorige</button>
        {isLast ? (
          <button onClick={onSubmit} disabled={submitting || isRecording} className={clsx(ORANGE, "rounded-full px-6 py-2.5 font-semibold text-white disabled:opacity-60")}>{submitting ? "Inleveren..." : "Inleveren"}</button>
        ) : (
          <button onClick={() => setCurrentIndex((index) => Math.min(questions.length - 1, index + 1))} disabled={isRecording} className={clsx(ORANGE, "rounded-full px-6 py-2.5 font-semibold text-white disabled:opacity-60")}>Volgende →</button>
        )}
      </div>
    </div>
  );
}

function mediaProxyUrl(type: "image" | "audio" | "video", path: string): string {
  return `/api/backend/mock-exams/media/${type}?path=${encodeURIComponent(path)}`;
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
  const scoreColor =
    result.percent >= 90
      ? "border-emerald-200 bg-emerald-50 text-emerald-800"
      : result.percent >= 60
        ? "border-sky-200 bg-sky-50 text-sky-800"
        : "border-amber-200 bg-amber-50 text-amber-800";

  return (
    <div className="space-y-6">
      <Link href={`/mock-exams/${exam.section}`} className="text-sm text-brand-700 hover:underline">
        ← Back to {exam.section} exams
      </Link>
      <div className={clsx("rounded-xl border p-6 text-center", scoreColor)}>
        <p className="text-3xl font-bold">{result.label}</p>
        <p className="mt-2 text-lg">
          {result.score} / {result.total} {exam.section === "writing" ? "points" : "correct"} ({result.percent}%)
        </p>
        {exam.section === "writing" && (
          <p className="mt-1 text-sm">Study target: {WRITING_STUDY_TARGET}/37 points (about 68%). This is not an official DUO pass mark.</p>
        )}
        {exam.pass_threshold != null && (
          <p className="mt-1 text-sm">Pass mark: {exam.pass_threshold}/{exam.max_score}</p>
        )}
        <p className="mt-1 text-xs text-slate-500">
          Attempt #{result.attempt_no} · {formatDate(result.created_at)}
        </p>
      </div>

      <div className="space-y-4">
        {result.results
          .filter((r) => r.graded || exam.section === "writing")
          .map((r) => {
            const question = exam.questions.find((q) => q.id === r.id);
            return (
              <div key={r.id} className="card p-4">
                <p className="font-medium">{question?.question_text}</p>
                {r.writing_feedback ? (
                  <>
                    <p className="mt-2 text-sm font-semibold text-slate-800">
                      Score: {r.writing_feedback.score}/{r.writing_feedback.max_score}
                    </p>
                    <p className="mt-2 text-sm font-semibold text-slate-700">Feedback</p>
                    <p className="mt-2 whitespace-pre-wrap text-sm text-slate-700">{r.writing_feedback.feedback}</p>
                    {r.writing_feedback.criterion_scores.length > 0 && (
                      <div className="mt-4 grid gap-x-5 gap-y-1 text-sm sm:grid-cols-2">
                        {r.writing_feedback.criterion_scores.map((criterion) => (
                          <p key={criterion.criterion} className="flex justify-between border-b border-slate-200 py-1 text-slate-700">
                            <span>{WRITING_CRITERION_LABELS[criterion.criterion] ?? criterion.criterion}</span>
                            <span className="font-semibold">{criterion.score}</span>
                          </p>
                        ))}
                      </div>
                    )}
                    {r.writing_feedback.possible_answer && (
                      <div className="mt-4 border-l-4 border-[#2563eb] bg-blue-50 px-4 py-3">
                        <p className="text-sm font-semibold text-slate-800">Possible answer (Dutch)</p>
                        <p className="mt-2 whitespace-pre-wrap text-sm text-slate-700">{r.writing_feedback.possible_answer}</p>
                      </div>
                    )}
                  </>
                ) : exam.section === "writing" && !r.given ? (
                  <p className="mt-2 text-sm font-semibold text-slate-500">Not filled / skipped</p>
                ) : exam.section === "writing" ? (
                  <p className="mt-2 text-sm text-slate-500">Not evaluated</p>
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

export function TakeExamClient({ examId, viewAttemptNo }: { examId: string; viewAttemptNo?: number }) {
  const [exam, setExam] = useState<MockExamTakeDetail | null>(null);
  const [attempts, setAttempts] = useState<MockExamAttemptSummary[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [answers, setAnswers] = useState<Record<string, string>>({});
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
    if (viewAttemptNo) {
      callApi<MockExamAttemptResult>(`mock-exams/${examId}/attempts/${viewAttemptNo}`)
        .then(setResult)
        .catch((e) => setLoadError(e instanceof Error ? e.message : "Could not load this attempt"));
    } else {
      callApi<MockExamAttemptSummary[]>(`mock-exams/${examId}/attempts`)
        .then(setAttempts)
        .catch(() => {
          // Attempt history is a nice-to-have; don't block the exam if it fails to load.
        });
    }
  }, [examId, viewAttemptNo]);

  const submit = async () => {
    setSubmitting(true);
    setSubmitError(null);
    try {
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

  if (loadError) return <p className="text-red-600">{loadError}</p>;
  if (!exam || (viewAttemptNo && !result)) return <p className="text-slate-500">Loading…</p>;
  if (result) return <ResultView exam={exam} result={result} />;
  if (exam.section === "writing") {
    return (
      <WritingPaper
        exam={exam}
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
      <SpeakingExam
        exam={exam}
        onAnswerChange={(questionId, answer) => setAnswers((current) => ({ ...current, [questionId]: answer }))}
        onSubmit={submit}
        submitting={submitting}
        submitError={submitError}
      />
    );
  }

  const minutesLeft = secondsLeft !== null ? Math.max(0, Math.ceil(secondsLeft / 60)) : null;

  const header = (
    <div className={clsx(NAVY, "flex items-center justify-between px-6 py-4 text-white")}>
      <div className="flex items-center gap-3">
        <Link href={`/mock-exams/${exam.section}`} className="text-sm text-white/80 hover:text-white">
          ←
        </Link>
        <span className="font-medium">{exam.title}</span>
      </div>
      {phase === "question" && (
        <button
          onClick={() => setTimerVisible((v) => !v)}
          className="rounded-full p-2 text-white/90 hover:bg-white/10"
          title="Toon/verberg de resterende tijd"
        >
          {timerVisible && minutesLeft !== null ? (
            <span className="font-semibold">{timeUp ? "Time's up" : `${minutesLeft} min`}</span>
          ) : (
            "⏰"
          )}
        </button>
      )}
    </div>
  );

  if (phase === "intro") {
    return (
      <div className="-mx-4 -my-8 min-h-[70vh]">
        {header}
        <div className="grid gap-6 p-6 md:grid-cols-2">
          <div className="card max-h-[60vh] overflow-y-auto p-6">
            <p className="font-semibold">Welkom bij het examen {exam.title}</p>
            <p className="mt-3 text-slate-700">
              {exam.instructions || `U moet in dit examen ${exam.total_questions} vragen beantwoorden.`}
            </p>
            <p className="mt-3 text-slate-700">Wilt u met het examen beginnen, klik dan op &quot;start&quot;.</p>
          </div>
          <div className="card p-6">
            <h1 className="text-2xl font-bold">{exam.title}</h1>
            <div className="mt-4 flex gap-3">
              <div className={clsx("rounded-xl border-2 px-4 py-2 text-center", NAVY_TEXT, "border-current")}>
                <p className="text-xl font-bold">{exam.total_questions}</p>
                <p className="text-xs">Vragen</p>
              </div>
              <div className={clsx("rounded-xl border-2 px-4 py-2 text-center", NAVY_TEXT, "border-current")}>
                <p className="text-xl font-bold">{exam.time_limit_minutes}</p>
                <p className="text-xs">Minuten</p>
              </div>
            </div>

            {attempts.length > 0 && (
              <div className="mt-6">
                <p className="text-sm font-semibold">Your previous attempts</p>
                <ul className="mt-2 space-y-1 text-sm">
                  {attempts.map((a) => (
                    <li key={a.attempt_no}>
                      <Link
                        href={`/mock-exams/${exam.section}/${examId}/attempts/${a.attempt_no}`}
                        className="text-brand-700 hover:underline"
                      >
                        Attempt #{a.attempt_no} — {a.label} ({a.score}/{a.total}, {a.percent}%)
                      </Link>{" "}
                      <span className="text-slate-500">· {formatDate(a.created_at)}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        </div>
        <div className={clsx(NAVY, "flex justify-end px-6 py-4")}>
          <button
            onClick={() => setPhase("question")}
            className={clsx(ORANGE, "rounded-full px-6 py-2.5 font-semibold text-white")}
          >
            Start →
          </button>
        </div>
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
        <div className="border-b border-red-200 bg-red-50 px-6 py-2 text-center text-sm text-red-800">
          ⏰ Time&apos;s up! On the real exam this would end now — you can still answer and submit.
        </div>
      )}

      <div className="grid gap-6 p-6 md:grid-cols-2">
        <div className="card max-h-[55vh] overflow-y-auto p-6">
          {passage ? (
            <>
              {passage.title && <p className="font-semibold">{passage.title}</p>}
              <PassageMedia mediaUrls={passage.media_urls} />
              {passage.content_nl && (
                <div className="mt-2">
                  <PassageContent text={passage.content_nl} />
                </div>
              )}
            </>
          ) : (
            <p className="text-slate-400">No reading text for this question.</p>
          )}
        </div>

        <div className="card max-h-[55vh] overflow-y-auto p-6">
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
        </div>
      </div>

      {submitError && <p className="px-6 text-red-600">{submitError}</p>}

      <div className={clsx(NAVY, "relative flex items-center justify-between px-6 py-4")}>
        <button
          onClick={() => setCurrentIndex((i) => Math.max(0, i - 1))}
          disabled={isFirst}
          className="flex items-center gap-1 rounded-full bg-white/20 px-5 py-2.5 font-semibold text-white disabled:opacity-40"
        >
          ← Vorige
        </button>

        <div className="flex items-center gap-4">
          <button
            onClick={() => setShowOverview((v) => !v)}
            className="rounded p-2 text-white/90 hover:bg-white/10"
            title="Overzicht"
          >
            ▦
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
              "rounded p-2 hover:bg-white/10",
              question && flagged.has(question.id) ? "text-[#e8863c]" : "text-white/90",
            )}
            title="Markeer voor later"
          >
            🔖
          </button>
        </div>

        {isLast ? (
          <button
            onClick={submit}
            disabled={submitting}
            className={clsx(ORANGE, "rounded-full px-6 py-2.5 font-semibold text-white disabled:opacity-60")}
          >
            {submitting ? "Submitting…" : "Submit exam"}
          </button>
        ) : (
          <button
            onClick={() => setCurrentIndex((i) => Math.min(sortedQuestions.length - 1, i + 1))}
            className={clsx(ORANGE, "rounded-full px-6 py-2.5 font-semibold text-white")}
          >
            Volgende →
          </button>
        )}

        <span className={clsx(ORANGE, "absolute -bottom-3 left-6 rounded px-2 py-0.5 text-sm font-bold text-white")}>
          {currentIndex + 1} / {sortedQuestions.length}
        </span>

        {showOverview && (
          <div className="absolute bottom-14 left-1/2 grid w-80 -translate-x-1/2 grid-cols-8 gap-1 rounded-xl bg-white p-3 shadow-lg">
            {sortedQuestions.map((q, i) => (
              <button
                key={q.id}
                onClick={() => {
                  setCurrentIndex(i);
                  setShowOverview(false);
                }}
                className={clsx(
                  "grid h-8 w-8 place-items-center rounded text-xs font-semibold",
                  i === currentIndex
                    ? clsx(NAVY, "text-white")
                    : answers[q.id]
                      ? "bg-emerald-100 text-emerald-800"
                      : "bg-slate-100 text-slate-600",
                  flagged.has(q.id) && "ring-2 ring-[#e8863c]",
                )}
              >
                {i + 1}
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

