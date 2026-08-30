"use client";

import { useState } from "react";
import clsx from "clsx";
import { Star } from "lucide-react";
import { callApi } from "@/lib/format";

export function FeedbackForm() {
  const [rating, setRating] = useState(0);
  const [hovered, setHovered] = useState(0);
  const [comment, setComment] = useState("");
  const [state, setState] = useState<"idle" | "saving" | "saved" | "error">("idle");
  const [error, setError] = useState<string | null>(null);

  async function submit() {
    setState("saving");
    setError(null);
    try {
      await callApi("feedback", {
        method: "POST",
        body: JSON.stringify({ rating, comment }),
      });
      setState("saved");
      setRating(0);
      setComment("");
    } catch (e) {
      setState("error");
      setError(e instanceof Error ? e.message : "Could not submit your feedback");
    }
  }

  if (state === "saved") {
    return (
      <div className="card p-6 text-center">
        <p className="font-semibold text-emerald-700">Thanks for your feedback!</p>
        <p className="mt-1 text-sm text-slate-500">
          Our team reviews every submission before it appears on the site.
        </p>
        <button onClick={() => setState("idle")} className="btn-secondary mt-4 text-sm">
          Leave more feedback
        </button>
      </div>
    );
  }

  return (
    <div className="card space-y-4 p-6">
      <div>
        <p className="mb-2 text-sm font-semibold">Your rating</p>
        <div className="flex gap-1">
          {[1, 2, 3, 4, 5].map((value) => (
            <button
              key={value}
              type="button"
              aria-label={`${value} star${value > 1 ? "s" : ""}`}
              onClick={() => setRating(value)}
              onMouseEnter={() => setHovered(value)}
              onMouseLeave={() => setHovered(0)}
            >
              <Star
                size={28}
                className={clsx(
                  (hovered || rating) >= value
                    ? "fill-amber-400 text-amber-400"
                    : "fill-transparent text-slate-300",
                )}
              />
            </button>
          ))}
        </div>
      </div>

      <label className="block">
        <span className="text-sm font-semibold">Your comment</span>
        <textarea
          value={comment}
          onChange={(e) => setComment(e.target.value)}
          rows={4}
          maxLength={2000}
          placeholder="Tell us what you liked or what we could improve…"
          className="mt-2 w-full rounded-xl border border-slate-200 p-3 text-sm focus:border-brand-400 focus:outline-none"
        />
      </label>

      {error && <p className="text-sm text-rose-600">{error}</p>}

      <button
        onClick={submit}
        disabled={state === "saving" || rating === 0 || comment.trim().length === 0}
        className="btn-primary px-5 py-2 text-sm disabled:opacity-50"
      >
        {state === "saving" ? "Sending…" : "Submit feedback"}
      </button>
    </div>
  );
}
