"use client";

import { useState } from "react";
import { BookOpenText, Headphones, Landmark, Mic, PenLine } from "lucide-react";
import { CheckoutButton } from "@/components/CheckoutButton";
import type { MockExamSection } from "@/lib/types";

const LEVEL_TABS = ["A2", "B1", "B2", "C1", "C2"] as const;

const SECTION_CARDS = [
  {
    key: "reading",
    label: "Lezen",
    sub: "Reading",
    icon: BookOpenText,
    questions: "25 questions",
    minutes: "65 min",
    format: "Multiple-choice on real-life texts — emails, notices, articles",
  },
  {
    key: "listening",
    label: "Luisteren",
    sub: "Listening",
    icon: Headphones,
    questions: "25 questions",
    minutes: "45 min",
    format: "Multiple-choice on audio clips — conversations, announcements",
  },
  {
    key: "writing",
    label: "Schrijven",
    sub: "Writing",
    icon: PenLine,
    questions: "4 tasks",
    minutes: "40 min",
    format: "Open writing — emails, notes and forms, with AI feedback",
  },
  {
    key: "speaking",
    label: "Spreken",
    sub: "Speaking",
    icon: Mic,
    questions: "16 tasks · 4 parts",
    minutes: "35 min",
    format: "Spoken answers to picture and video prompts, with feedback",
  },
  {
    key: "knm",
    label: "KNM",
    sub: "Dutch Society",
    icon: Landmark,
    questions: "40 questions",
    minutes: "45 min",
    format: "Multiple-choice on everyday Dutch society scenarios",
  },
] as const;

/** Level-tabbed pricing grid for single-section unlocks; only A2 has exams today. */
export function SectionPricingTabs({ examCountBySection }: { examCountBySection: Record<string, number> }) {
  const [level, setLevel] = useState<(typeof LEVEL_TABS)[number]>("A2");

  return (
    <section className="mx-auto max-w-6xl">
      <h2 className="text-center text-2xl font-bold">Or unlock just one section</h2>
      <p className="mx-auto mt-2 max-w-2xl text-center text-sm text-slate-600">
        3 months of unlimited retakes — on the real exam interface, with the same variety of question formats
        (multiple-choice, audio, picture prompts, open writing and speaking) you&apos;ll face on exam day.
      </p>

      <div className="mx-auto mt-6 flex max-w-md justify-center gap-2">
        {LEVEL_TABS.map((tab) => (
          <button
            key={tab}
            onClick={() => setLevel(tab)}
            className={`rounded-full px-4 py-1.5 text-sm font-semibold transition ${
              level === tab
                ? "bg-brand-700 text-white"
                : "bg-slate-100 text-slate-600 hover:bg-slate-200"
            }`}
          >
            {tab}
          </button>
        ))}
      </div>

      {level === "A2" ? (
        <div className="mt-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
          {SECTION_CARDS.map(({ key, label, sub, icon: Icon, questions, minutes, format }) => {
            const examCount = examCountBySection[key] ?? 0;
            return (
              <article key={key} className="card p-6 text-center">
                <span className="mx-auto grid h-11 w-11 place-items-center rounded-xl bg-brand-50 text-brand-700">
                  <Icon size={20} />
                </span>
                <h3 className="mt-3 font-semibold">{label}</h3>
                <p className="text-xs text-slate-500">{sub}</p>
                {examCount > 0 && (
                  <p className="mt-2 text-xs font-semibold text-brand-700">
                    {examCount} exam{examCount > 1 ? "s" : ""} available
                  </p>
                )}
                <p className="mt-2 text-sm font-medium text-slate-700">
                  {questions} · {minutes}
                </p>
                <p className="mt-2 text-xs text-slate-500">{format}</p>
                <p className="mt-4">
                  <span className="text-sm text-slate-400 line-through">€13</span>{" "}
                  <span className="text-2xl font-bold text-emerald-600">€7</span>{" "}
                  <span className="rounded-full bg-emerald-50 px-2 py-0.5 text-xs font-bold text-emerald-600">-46%</span>
                </p>
                <CheckoutButton
                  product="section"
                  section={key as MockExamSection}
                  label="Unlock"
                  className="btn-primary mt-4 w-full px-5 py-2 text-sm"
                />
              </article>
            );
          })}
        </div>
      ) : (
        <div className="mx-auto mt-8 max-w-md text-center">
          <p className="text-sm font-medium text-slate-500">{level} practice exams are coming soon.</p>
        </div>
      )}
    </section>
  );
}
