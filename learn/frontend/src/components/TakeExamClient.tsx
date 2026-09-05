"use client";
import { useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import clsx from "clsx";
import { AlarmClock, Bookmark, Clock3, Grid2X2, Info, LoaderCircle, Mail, Mic, MicOff, Minus, Pause, Play, Printer, Send, Square, Trash2, Volume2, VolumeX, X } from "lucide-react";
import { callApi, formatDate } from "@/lib/format";
import { PassageContent } from "./PassageContent";
import { DuoPlaybackControls } from "./DuoPlaybackControls";
import { ListeningExam } from "./ListeningExam";
import { KnmExam } from "./KnmExam";
import { TimeUpDialog, ExamFooter, ExamHeader, IntroBody, IntroHeading, IntroLayout, IntroNote, IntroSidePanel, QuestionPicker } from "./DuoExamChrome";
import type {
  MockExamAttemptResult,
  MockExamAttemptSummary,
  MockExamTakeDetail,
} from "@/lib/types";

// Colors match the official DUO/Optimum Assessment exam player exactly (navy header/footer, orange accent).
const NAVY = "bg-[#2b4a78]";
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
  const prefix = `${greeting}\n\n`;
  const suffix = `\n\n${closing}`;
  if (answer.startsWith(prefix) && answer.endsWith(suffix)) {
    return answer.slice(prefix.length, -suffix.length);
  }
  return answer;
}

function emailAnswerParts(answer: string, greeting: string, closing: string) {
  if (!answer) return { body: "", senderName: "" };
  const prefix = `${greeting}\n\n`;
  const closingMarker = `\n\n${closing}\n`;
  const content = answer.startsWith(prefix) ? answer.slice(prefix.length) : answer;
  const closingIndex = content.lastIndexOf(closingMarker);
  if (closingIndex < 0) return { body: content, senderName: "" };
  return {
    body: content.slice(0, closingIndex),
    senderName: content.slice(closingIndex + closingMarker.length),
  };
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
  const { body, senderName } = emailAnswerParts(answer, greeting, closing);
  const assembleAnswer = (nextBody: string, nextSenderName: string) =>
    `${greeting}\n\n${nextBody}\n\n${closing}\n${nextSenderName}`;
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
          value={body}
          onChange={(event) => onChange(assembleAnswer(event.target.value, senderName))}
          placeholder="Schrijf hier uw e-mail."
          disabled={disabled}
        />
        <p>{closing}</p>
        <label htmlFor={`answer-name-${questionId}`} className="sr-only">Uw naam</label>
        <input
          id={`answer-name-${questionId}`}
          className="mt-2 w-full max-w-xs border-b border-[#2563eb] bg-blue-50 px-2 py-1 outline-none focus:bg-blue-100 disabled:cursor-not-allowed disabled:bg-slate-100"
          value={senderName}
          onChange={(event) => onChange(assembleAnswer(body, event.target.value))}
          placeholder="Uw naam"
          disabled={disabled}
        />
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
          const combinedOptions = line.match(/^(?:O|0)\s+(.+?)\s*\/\s*(?:O|0)\s+(.+)$/i);
          const option = line.match(/^(?:O|0)\s+(.+)/i);
          const label = line.replace(/^\d+\.\s*/, "").replace(/:$/, "");
          const field = !inlineOptions && !combinedOptions && !option && !isFormHeading(label, nextLine);
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
          if (combinedOptions) {
            const groupLabel = (lines[index - 1] ?? "Keuze").replace(/^\d+\.\s*/, "").replace(/:$/, "");
            return (
              <div key={`${line}-${index}`} className="flex items-center gap-5 border-b border-slate-600 bg-blue-50 px-3 py-2">
                {combinedOptions.slice(1).map((choice) => (
                  <label key={choice} className="flex items-center gap-2">
                    <input
                      className="accent-[#2563eb]"
                      type="radio"
                      name={`${questionId}-${groupLabel}`}
                      checked={values[groupLabel] === choice}
                      onChange={() => update(groupLabel, choice)}
                      disabled={disabled}
                    />
                    {choice}
                  </label>
                ))}
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
  const { body, senderName } = emailAnswerParts(answer, greeting, closing);
  const assembleAnswer = (nextBody: string, nextSenderName: string) =>
    `${greeting}\n\n${nextBody}\n\n${closing}\n${nextSenderName}`;
  return (
    <div className="mt-5 border border-slate-600 bg-white p-4 text-base leading-6">
      <p>{greeting}</p>
      <label htmlFor={`answer-${questionId}`} className="sr-only">Uw briefje</label>
      <textarea
        id={`answer-${questionId}`}
        className="my-3 w-full resize-y bg-[repeating-linear-gradient(to_bottom,#eff6ff_0,#eff6ff_29px,#bfdbfe_30px)] px-0 py-1 leading-6 outline-none focus:bg-blue-100 disabled:cursor-not-allowed disabled:bg-slate-100"
        rows={Math.max(5, answerLines - 3)}
        value={body}
        onChange={(event) => onChange(assembleAnswer(event.target.value, senderName))}
        placeholder="Schrijf hier uw briefje."
        disabled={disabled}
      />
      <p className="whitespace-pre-wrap">{closing}</p>
      <label htmlFor={`answer-name-${questionId}`} className="sr-only">Uw naam</label>
      <input
        id={`answer-name-${questionId}`}
        className="mt-2 w-full max-w-xs border-b border-[#2563eb] bg-blue-50 px-2 py-1 outline-none focus:bg-blue-100 disabled:cursor-not-allowed disabled:bg-slate-100"
        value={senderName}
        onChange={(event) => onChange(assembleAnswer(body, event.target.value))}
        placeholder="Uw naam"
        disabled={disabled}
      />
    </div>
  );
}

function WritingPaper({
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

  function updateAnswer(questionId: string, answer: string) {
    setShowIncompleteConfirmation(false);
    onAnswerChange(questionId, answer);
  }

  function confirmIncompleteSubmit() {
    setShowIncompleteConfirmation(false);
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

      {attempts.length > 0 && (
        <details className="border border-slate-300 bg-white px-4 py-3 shadow-sm print:hidden">
          <summary className="cursor-pointer text-sm font-semibold text-[#2b4a78]">
            Previous attempts ({attempts.length})
          </summary>
          <ul className="mt-3 divide-y divide-slate-200 text-sm">
            {attempts.map((attempt) => (
              <li key={attempt.attempt_no} className="flex flex-wrap items-center justify-between gap-2 py-2">
                <Link
                  href={`/mock-exams/${exam.section}/${examId}/attempts/${attempt.attempt_no}`}
                  className="font-semibold text-brand-700 hover:underline"
                >
                  Attempt #{attempt.attempt_no}
                </Link>
                <span className="text-slate-600">
                  {attempt.score}/{attempt.total} points ({attempt.percent}%) · {formatDate(attempt.created_at)}
                </span>
              </li>
            ))}
          </ul>
        </details>
      )}

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
                      onChange={(answer) => updateAnswer(question.id, answer)}
                    />
                  ) : recipient ? (
                    <EmailPaperAnswer
                      questionId={question.id}
                      recipient={recipient}
                      subject={emailSubject(question.question_text)}
                      answer={answers[question.id] ?? ""}
                      answerLines={answerLines}
                      disabled={timeUp}
                      onChange={(answer) => updateAnswer(question.id, answer)}
                    />
                  ) : wijkkrantTask ? (
                    <CompositionPaperAnswer
                      questionId={question.id}
                      topic={topic}
                      answer={answers[question.id] ?? ""}
                      answerLines={answerLines}
                      disabled={timeUp}
                      onChange={(answer) => updateAnswer(question.id, answer)}
                    />
                  ) : noteTo ? (
                    <NotePaperAnswer
                      questionId={question.id}
                      recipient={noteTo}
                      answer={answers[question.id] ?? ""}
                      answerLines={answerLines}
                      disabled={timeUp}
                      onChange={(answer) => updateAnswer(question.id, answer)}
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
                        onChange={(event) => updateAnswer(question.id, event.target.value)}
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
                <button onClick={confirmIncompleteSubmit} className="btn-primary">Toch inleveren</button>
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
          <p className="mt-1 text-sm">Study target: {WRITING_STUDY_TARGET}/37 points (about 68%). This is not an official DUO pass mark.</p>
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
                            <span>{WRITING_CRITERION_LABELS[criterion.criterion] ?? criterion.criterion}</span>
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

export function TakeExamClient({ examId, viewAttemptNo }: { examId: string; viewAttemptNo?: number }) {
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

  if (loadError) return <p className="text-red-600">{loadError}</p>;
  if (!exam || (viewAttemptNo && !result)) return <p className="text-slate-500">Loading…</p>;
  if (result) return <ResultView exam={exam} result={result} />;
  if (exam.section === "writing") {
    return (
      <WritingPaper
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
      <SpeakingExam
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

