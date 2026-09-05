import Link from "next/link";
import { Check, Clock, Lock, MonitorCheck, RefreshCw } from "lucide-react";
import { CheckoutButton } from "@/components/CheckoutButton";
import { SectionPricingTabs } from "@/components/SectionPricingTabs";
import { api } from "@/lib/api";
import type { MockExamSummary } from "@/lib/types";

export const metadata = { title: "Pricing · Learn Dutch in 5 Minutes" };

const BENEFITS = [
  {
    icon: MonitorCheck,
    title: "The real exam interface",
    body: "Practice on the same screen you'll see on exam day — same layout, navigation and question types as the official Staatsexamen NT2.",
  },
  {
    icon: Clock,
    title: "Real time pressure",
    body: "Every exam runs on the official time limit, so you learn to pace yourself before it counts.",
  },
  {
    icon: RefreshCw,
    title: "Practice until you're confident",
    body: "Retake unlocked exams as many times as you like for 3 months — track your score and walk in ready.",
  },
];

const FREE_FEATURES = [
  "All video courses, A1 through B2",
  "Vocabulary, transcripts, grammar notes and quizzes",
  "Flashcards with spaced repetition",
  "Certificates of completion",
  "One free exam per section, on the real exam interface",
];

const FULL_FEATURES = [
  "Every inburgering exam, every section, unlocked for 3 months",
  "Unlimited retakes on the real exam interface",
  "AI feedback on writing and speaking answers",
  "Full attempt history and score tracking",
];

const SECTION_KEYS = ["reading", "listening", "writing", "speaking", "knm"] as const;
const SECTION_LABELS: Record<(typeof SECTION_KEYS)[number], string> = {
  reading: "Reading",
  listening: "Listening",
  writing: "Writing",
  speaking: "Speaking",
  knm: "KNM",
};

export default async function PricingPage({ searchParams }: { searchParams: { checkout?: string } }) {
  let mockExams: MockExamSummary[] = [];
  try {
    mockExams = await api<MockExamSummary[]>("/api/mock-exams", { authenticated: false });
  } catch {
    // Pricing page must still render even if the API is unavailable.
  }
  const examCountBySection = mockExams.reduce<Record<string, number>>((counts, exam) => {
    counts[exam.section] = (counts[exam.section] ?? 0) + 1;
    return counts;
  }, {});

  return (
    <div className="space-y-10">
      {searchParams.checkout === "pending" && (
        <div className="mx-auto max-w-2xl rounded-xl bg-emerald-50 px-4 py-3 text-center text-sm font-medium text-emerald-700">
          Thanks! We&apos;re confirming your payment — access unlocks within a minute of it clearing.
        </div>
      )}

      <section className="text-center">
        <h1 className="text-4xl font-bold">Simple, honest pricing</h1>
        <p className="mx-auto mt-4 max-w-2xl text-slate-600">
          Video courses stay free for everyone. Pay once to unlock inburgering practice exams for 3
          months — a one-time payment, no subscription, no auto-renewal.
        </p>
        <span className="mt-4 inline-block rounded-full bg-brand-50 px-3 py-1 text-xs font-semibold text-brand-700">
          Exams currently available for <span className="text-emerald-600">A2</span> — B1, B2, C1 and C2 coming soon
        </span>
      </section>

      <section className="mx-auto grid max-w-5xl gap-6 sm:grid-cols-3">
        {BENEFITS.map(({ icon: Icon, title, body }) => (
          <article key={title} className="text-center">
            <span className="mx-auto grid h-12 w-12 place-items-center rounded-xl bg-brand-50 text-brand-700">
              <Icon size={22} />
            </span>
            <h3 className="mt-3 font-semibold">{title}</h3>
            <p className="mt-1 text-sm text-slate-600">{body}</p>
          </article>
        ))}
      </section>

      <section className="mx-auto grid max-w-4xl gap-6 sm:grid-cols-2">
        <article className="card p-8">
          <h2 className="text-xl font-semibold">Free</h2>
          <p className="mt-1 text-sm text-slate-600">Everything you need to learn Dutch.</p>
          <p className="mt-4 text-3xl font-bold">€0</p>
          <ul className="mt-6 space-y-3 text-sm text-slate-600">
            {FREE_FEATURES.map((f) => (
              <li key={f} className="flex items-start gap-2">
                <Check size={16} className="mt-0.5 shrink-0 text-emerald-600" />
                {f}
              </li>
            ))}
          </ul>
          <Link href="/courses" className="btn-secondary mt-8 block w-fit px-5 py-2 text-sm">
            Start learning
          </Link>
        </article>

        <article className="card relative border-brand-200 p-8">
          <span className="absolute right-6 top-6 rounded-full bg-emerald-50 px-3 py-1 text-base font-bold text-emerald-600">
            A2
          </span>
          <span className="inline-flex items-center gap-1 rounded-full bg-brand px-3 py-1 text-xs font-semibold text-white">
            <Lock size={12} />
            Best value
          </span>
          <h2 className="mt-3 text-xl font-semibold">Complete Package</h2>
          <p className="mt-1 text-sm text-slate-600">For learners preparing to sit the exam.</p>
          <p className="mt-4">
            <span className="text-lg text-slate-400 line-through">€45</span>{" "}
            <span className="text-3xl font-bold">€25</span>{" "}
            <span className="text-base font-normal text-slate-500">one-time / 3 months</span>
          </p>
          <ul className="mt-6 space-y-3 text-sm text-slate-600">
            {FULL_FEATURES.map((f) => (
              <li key={f} className="flex items-start gap-2">
                <Check size={16} className="mt-0.5 shrink-0 text-emerald-600" />
                {f}
              </li>
            ))}
          </ul>
          <div className="mt-6 grid grid-cols-2 gap-x-4 gap-y-2 border-t border-slate-200 pt-4 text-xs text-slate-600 sm:grid-cols-3">
            {SECTION_KEYS.map((key) => {
              const examCount = examCountBySection[key] ?? 0;
              return (
                <p key={key}>
                  <span className="font-semibold text-slate-800">{SECTION_LABELS[key]}:</span>{" "}
                  {examCount} exam{examCount === 1 ? "" : "s"}
                </p>
              );
            })}
          </div>
          <CheckoutButton product="full" label="Unlock everything — €25" className="btn-primary mt-6 px-5 py-2 text-sm" />
        </article>
      </section>

      <SectionPricingTabs examCountBySection={examCountBySection} />
    </div>
  );
}

