"use client";

import clsx from "clsx";
import { useEffect, useState } from "react";
import { Bookmark, Grid2X2 } from "lucide-react";
import { PassageContent } from "./PassageContent";
import { ExamFooter, ExamHeader, mediaProxyUrl, QuestionPicker } from "./DuoExamChrome";
import type { MockExamAttemptSummary, MockExamTakeDetail } from "@/lib/types";

export function ReadingExam({ exam, answers, onAnswerChange, onSubmit, submitting, submitError }: {
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
	const [currentIndex, setCurrentIndex] = useState(0);
	const [timerVisible, setTimerVisible] = useState(false);
	const [showOverview, setShowOverview] = useState(false);
	const [flagged, setFlagged] = useState<Set<string>>(new Set());
	const [secondsLeft, setSecondsLeft] = useState(exam.time_limit_minutes * 60);
	const question = questions[currentIndex];
	const passage = question?.passage_id ? passageById.get(question.passage_id) : undefined;
	const isLast = currentIndex === questions.length - 1;

	useEffect(() => {
		if (secondsLeft <= 0) return;
		const timer = window.setTimeout(() => setSecondsLeft((current) => Math.max(0, current - 1)), 1000);
		return () => window.clearTimeout(timer);
	}, [secondsLeft]);

	if (!question || !passage) return null;
	const { intro, body } = splitReadingIntro(passage);

	return (
		<div className="-mx-4 -my-8 min-h-[70vh]">
			<ExamHeader title={exam.title} backHref={`/mock-exams/${exam.section}`} timer={{ minutesLeft: Math.max(0, Math.ceil(secondsLeft / 60)), visible: timerVisible, onToggle: () => setTimerVisible((visible) => !visible) }} />
			<div className="grid gap-4 p-4 sm:p-6 md:grid-cols-2">
				<section className="max-h-[60vh] overflow-y-auto border border-slate-200 bg-white px-7 py-6 text-slate-900 shadow-sm">
					{intro && <p className="text-[0.95rem] leading-[1.6]">{intro}</p>}
					<p className={clsx("whitespace-pre-wrap text-[0.95rem] leading-[1.6]", intro && "mt-4")}>{readingDisplayPrompt(passage)}</p>
					<hr className="my-6 border-slate-300" />
					{passage.title && <p className="text-[0.95rem] font-bold">{passage.title}</p>}
					<PassageMedia mediaUrls={passage.media_urls} />
					{body && <div className="mt-4"><PassageContent text={body} /></div>}
				</section>
				<section className="max-h-[60vh] overflow-y-auto border border-slate-200 bg-white px-7 py-6 text-slate-900 shadow-sm">
					<p className="whitespace-pre-wrap text-slate-800">{question.question_text}</p>
					{question.question_type === "multiple_choice" && question.options ? <div className="mt-4 space-y-3">{question.options.map((option, index) => { const selected = answers[question.id] === option; const imageUrl = question.option_media_urls?.[index]; return <button key={option} onClick={() => onAnswerChange(question.id, option)} className={clsx("w-full rounded-xl border-2 p-4 text-left transition", selected ? "border-transparent bg-[#2b4a78] text-white" : "border-slate-200 hover:border-slate-300")}><span className="flex items-center gap-3"><span className={clsx("grid h-5 w-5 shrink-0 place-items-center rounded-full border-2", selected ? "border-[#e8863c] bg-[#e8863c]" : "border-slate-300")} /><span className="font-semibold">{String.fromCharCode(65 + index)}</span>{!imageUrl && <span>{option}</span>}</span>{imageUrl && <img src={mediaProxyUrl("image", imageUrl)} alt={option} className="mt-3 block h-32 w-full rounded border border-slate-200 object-cover" />}</button>; })}</div> : <textarea className="mt-4 w-full rounded-lg border border-slate-200 p-2 text-sm" rows={5} value={answers[question.id] ?? ""} onChange={(event) => onAnswerChange(question.id, event.target.value)} />}
				</section>
			</div>
			{submitError && <p className="px-6 text-red-600">{submitError}</p>}
			<ExamFooter onPrevious={() => setCurrentIndex((index) => Math.max(0, index - 1))} previousDisabled={currentIndex === 0} primaryLabel={isLast ? (submitting ? "Inleveren..." : "Inleveren") : "Volgende ›"} onPrimary={isLast ? onSubmit : () => setCurrentIndex((index) => Math.min(questions.length - 1, index + 1))} primaryDisabled={submitting && isLast} badge={`${currentIndex + 1} / ${questions.length}`}>
				<button onClick={() => setShowOverview((open) => !open)} className="grid h-10 w-10 place-items-center rounded-md transition hover:bg-white/10" title="Kies een vraag" aria-label="Kies een vraag"><Grid2X2 size={26} strokeWidth={1.8} /></button>
				<button onClick={() => setFlagged((current) => { const next = new Set(current); next.has(question.id) ? next.delete(question.id) : next.add(question.id); return next; })} className={clsx("grid h-10 w-10 place-items-center rounded-md transition", flagged.has(question.id) ? "bg-[#e8863c] text-slate-950" : "hover:bg-white/10")} title="Markeer vraag" aria-label="Markeer vraag"><Bookmark size={26} strokeWidth={1.8} fill={flagged.has(question.id) ? "currentColor" : "none"} /></button>
				{showOverview && <QuestionPicker questions={questions} answers={answers} currentIndex={currentIndex} bookmarkedQuestionIds={Array.from(flagged)} onClose={() => setShowOverview(false)} onSelect={(index) => { setCurrentIndex(index); setShowOverview(false); }} />}
			</ExamFooter>
		</div>
	);
}

function readingDisplayPrompt(passage: MockExamTakeDetail["passages"][number]): string { return passage.display_prompt_nl?.trim() || "Lees eerst de vraag.\nLees daarna de tekst."; }

function splitReadingIntro(passage: MockExamTakeDetail["passages"][number]): { intro: string; body: string } {
	const paragraphs = (passage.content_nl ?? "").split(/\n\s*\n/);
	let intro = "";
	if (paragraphs.length > 1 && paragraphs[0].trim().length <= 140 && !paragraphs[0].trim().includes("\n")) intro = paragraphs.shift()!.trim();
	const title = passage.title?.trim().toLowerCase();
	if (title && paragraphs[0]?.trim().toLowerCase() === title) paragraphs.shift();
	return { intro, body: paragraphs.join("\n\n") };
}

function PassageMedia({ mediaUrls }: { mediaUrls: { type: string; url: string }[] }) {
	return mediaUrls.length === 0 ? null : <div className="mb-3 space-y-3">{mediaUrls.map((media) => <div key={media.url}>{media.type === "image" && <img src={mediaProxyUrl("image", media.url)} alt="" className="max-h-64 rounded-lg border border-slate-200" />}{media.type === "audio" && <audio controls className="w-full" src={mediaProxyUrl("audio", media.url)} />}{media.type === "video" && <video controls className="max-h-64 w-full rounded-lg" src={mediaProxyUrl("video", media.url)} />}</div>)}</div>;
}