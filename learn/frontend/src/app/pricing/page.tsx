import Link from "next/link";
import { Check, Lock } from "lucide-react";
import { CheckoutButton } from "@/components/CheckoutButton";
import { SectionCheckoutCard } from "@/components/SectionCheckoutCard";

export const metadata = { title: "Pricing · Learn Dutch in 5 Minutes" };

const FREE_FEATURES = [
  "All video courses, A1 through B2",
  "Vocabulary, transcripts, grammar notes and quizzes",
  "Flashcards with spaced repetition",
  "Certificates of completion",
  "One free inburgering exam per section (reading, listening, writing, speaking, KNM)",
];

const SECTION_FEATURES = [
  "Every exam in one section, unlocked for 3 months",
  "Reading, listening, writing, speaking or KNM — your choice",
];

const FULL_FEATURES = [
  "Every inburgering exam, every section, unlocked for 3 months",
  "AI feedback on writing and speaking answers",
  "Full attempt history and score tracking",
];

export default function PricingPage({ searchParams }: { searchParams: { checkout?: string } }) {
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
          Video courses stay free for everyone. Unlock inburgering practice exams for 3 months at a
          time — pay once, no auto-renewal.
        </p>
      </section>

      <section className="mx-auto grid max-w-6xl gap-6 sm:grid-cols-3">
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

        <article className="card p-8">
          <h2 className="text-xl font-semibold">Single Section</h2>
          <p className="mt-1 text-sm text-slate-600">For learners focused on one skill.</p>
          <p className="mt-4 text-3xl font-bold">
            €9 <span className="text-base font-normal text-slate-500">/ 3 months</span>
          </p>
          <ul className="mt-6 space-y-3 text-sm text-slate-600">
            {SECTION_FEATURES.map((f) => (
              <li key={f} className="flex items-start gap-2">
                <Check size={16} className="mt-0.5 shrink-0 text-emerald-600" />
                {f}
              </li>
            ))}
          </ul>
          <SectionCheckoutCard />
        </article>

        <article className="card border-brand-200 p-8">
          <span className="inline-flex items-center gap-1 rounded-full bg-brand px-3 py-1 text-xs font-semibold text-white">
            <Lock size={12} />
            Best value
          </span>
          <h2 className="mt-3 text-xl font-semibold">Complete Package</h2>
          <p className="mt-1 text-sm text-slate-600">For learners preparing to sit the exam.</p>
          <p className="mt-4 text-3xl font-bold">
            €25 <span className="text-base font-normal text-slate-500">/ 3 months</span>
          </p>
          <ul className="mt-6 space-y-3 text-sm text-slate-600">
            {FULL_FEATURES.map((f) => (
              <li key={f} className="flex items-start gap-2">
                <Check size={16} className="mt-0.5 shrink-0 text-emerald-600" />
                {f}
              </li>
            ))}
          </ul>
          <CheckoutButton product="full" label="Unlock everything — €25" className="btn-primary mt-8 px-5 py-2 text-sm" />
        </article>
      </section>
    </div>
  );
}

