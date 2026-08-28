"use client";

import { useEffect, useState } from "react";
import { callApi } from "@/lib/format";
import type { FlashcardDue } from "@/lib/types";

// SM-2 recall qualities exposed as four buttons.
const RATINGS = [
  { quality: 1, label: "Again", className: "bg-rose-100 text-rose-700 hover:bg-rose-200" },
  { quality: 3, label: "Hard", className: "bg-amber-100 text-amber-700 hover:bg-amber-200" },
  { quality: 4, label: "Good", className: "bg-sky-100 text-sky-700 hover:bg-sky-200" },
  { quality: 5, label: "Easy", className: "bg-emerald-100 text-emerald-700 hover:bg-emerald-200" },
];

export default function FlashcardsPage() {
  const [cards, setCards] = useState<FlashcardDue[] | null>(null);
  const [index, setIndex] = useState(0);
  const [revealed, setRevealed] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    callApi<FlashcardDue[]>("flashcards/due?limit=30")
      .then(setCards)
      .catch((e: Error) => setError(e.message));
  }, []);

  if (error) return <p className="text-sm text-rose-600">{error}</p>;
  if (!cards) return <p className="text-slate-500">Loading your flashcards…</p>;

  if (cards.length === 0) {
    return (
      <div className="card p-10 text-center">
        <h1 className="text-2xl font-bold">Nothing due right now</h1>
        <p className="mt-2 text-slate-600">
          Flashcards are built from the vocabulary of lessons you have completed. Finish a
          lesson to start collecting words.
        </p>
      </div>
    );
  }

  if (index >= cards.length) {
    return (
      <div className="card p-10 text-center">
        <h1 className="text-2xl font-bold">Session complete</h1>
        <p className="mt-2 text-slate-600">You reviewed {cards.length} words. Goed gedaan!</p>
      </div>
    );
  }

  const card = cards[index];

  async function rate(quality: number) {
    setRevealed(false);
    setIndex((i) => i + 1);
    try {
      await callApi("flashcards/review", {
        method: "POST",
        body: JSON.stringify({ vocab_id: card.vocab_id, quality }),
      });
    } catch {
      // A failed review must not block the session; the card stays due.
    }
  }

  return (
    <div className="mx-auto max-w-2xl">
      <p className="mb-4 text-center text-sm text-slate-500">
        Card {index + 1} of {cards.length}
      </p>

      <div className="card flex min-h-[16rem] flex-col items-center justify-center p-10 text-center">
        <p className="text-3xl font-bold">{card.nl}</p>
        {revealed ? (
          <p className="mt-4 text-xl text-brand-700">{card.en}</p>
        ) : (
          <button onClick={() => setRevealed(true)} className="btn-secondary mt-6">
            Show translation
          </button>
        )}
        <p className="mt-6 text-xs text-slate-400">From: {card.lesson_title}</p>
      </div>

      {revealed && (
        <div className="mt-5 grid grid-cols-4 gap-2">
          {RATINGS.map((rating) => (
            <button
              key={rating.quality}
              onClick={() => rate(rating.quality)}
              className={`rounded-lg py-3 text-sm font-medium transition ${rating.className}`}
            >
              {rating.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
