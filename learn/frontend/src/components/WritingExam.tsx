"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import clsx from "clsx";
import { Clock3, LoaderCircle, Mail, Minus, Printer, Send, Square, X } from "lucide-react";
import { formatDate } from "@/lib/format";
import { PassageContent } from "./PassageContent";
import { mediaProxyUrl } from "./DuoExamChrome";
import type { MockExamAttemptSummary, MockExamTakeDetail } from "@/lib/types";

const ORANGE = "bg-[#e8863c] hover:bg-[#dc7a30]";

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

export function WritingExam({
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

function PassageMedia({ mediaUrls }: { mediaUrls: { type: string; url: string }[] }) {
  if (mediaUrls.length === 0) return null;
  return (
    <div className="mb-3 space-y-3">
      {mediaUrls.map((media) => (
        <div key={media.url}>
          {media.type === "image" && <img src={mediaProxyUrl("image", media.url)} alt="" className="max-h-64 rounded-lg border border-slate-200" />}
          {media.type === "audio" && <audio controls className="w-full" src={mediaProxyUrl("audio", media.url)} />}
          {media.type === "video" && <video controls className="max-h-64 w-full rounded-lg" src={mediaProxyUrl("video", media.url)} />}
        </div>
      ))}
    </div>
  );
}
