"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import clsx from "clsx";
import { ChevronLeft, ChevronRight, Star } from "lucide-react";
import type { FeedbackPublic } from "@/lib/types";

const AUTO_ADVANCE_MS = 5000;

/** Scroll-snap carousel — swipeable on mobile by default, with arrows/dots on larger screens. */
export function TestimonialCarousel({ items }: { items: FeedbackPublic[] }) {
  const trackRef = useRef<HTMLDivElement>(null);
  const [active, setActive] = useState(0);
  const [paused, setPaused] = useState(false);
  const activeRef = useRef(0);

  const scrollToIndex = useCallback((index: number) => {
    const track = trackRef.current;
    const card = track?.children[index] as HTMLElement | undefined;
    if (!track || !card) return;
    // Scroll only the track horizontally — scrollIntoView would also move the page vertically.
    const delta = card.getBoundingClientRect().left - track.getBoundingClientRect().left;
    track.scrollTo({ left: track.scrollLeft + delta, behavior: "smooth" });
  }, []);

  function go(dir: 1 | -1) {
    const next = Math.min(Math.max(active + dir, 0), items.length - 1);
    setActive(next);
    scrollToIndex(next);
  }

  useEffect(() => {
    activeRef.current = active;
  }, [active]);

  // Loops back to the first card; pauses while the visitor is interacting with the carousel.
  useEffect(() => {
    if (items.length <= 1 || paused) return;
    const id = setInterval(() => {
      const next = (activeRef.current + 1) % items.length;
      setActive(next);
      scrollToIndex(next);
    }, AUTO_ADVANCE_MS);
    return () => clearInterval(id);
  }, [items.length, paused, scrollToIndex]);

  useEffect(() => {
    const track = trackRef.current;
    if (!track) return;

    function onScroll() {
      const cards = Array.from(track!.children) as HTMLElement[];
      let closest = 0;
      let closestDist = Infinity;
      cards.forEach((card, i) => {
        const dist = Math.abs(card.offsetLeft - track!.scrollLeft);
        if (dist < closestDist) {
          closestDist = dist;
          closest = i;
        }
      });
      setActive(closest);
    }

    track.addEventListener("scroll", onScroll, { passive: true });
    return () => track.removeEventListener("scroll", onScroll);
  }, []);

  return (
    <div
      className="relative"
      onMouseEnter={() => setPaused(true)}
      onMouseLeave={() => setPaused(false)}
      onTouchStart={() => setPaused(true)}
      onTouchEnd={() => setPaused(false)}
    >
      <div
        ref={trackRef}
        className="flex snap-x snap-mandatory gap-6 overflow-x-auto scroll-smooth px-1 pb-2 [-ms-overflow-style:none] [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
      >
        {items.map((item) => (
          <article
            key={item.id}
            className="card w-[85%] shrink-0 snap-start p-6 sm:w-[45%] lg:w-[31%]"
          >
            <div className="flex gap-0.5">
              {Array.from({ length: 5 }, (_, i) => (
                <Star
                  key={i}
                  size={16}
                  className={
                    i < item.rating
                      ? "fill-amber-400 text-amber-400"
                      : "fill-transparent text-slate-300"
                  }
                />
              ))}
            </div>
            <p className="mt-3 text-sm text-slate-600">&ldquo;{item.comment}&rdquo;</p>
            <p className="mt-4 text-sm font-semibold">{item.name}</p>
          </article>
        ))}
      </div>

      {items.length > 1 && (
        <>
          <button
            type="button"
            aria-label="Previous feedback"
            onClick={() => go(-1)}
            disabled={active === 0}
            className="absolute -left-4 top-1/2 hidden -translate-y-1/2 rounded-full bg-white p-2 shadow-md disabled:opacity-30 sm:flex"
          >
            <ChevronLeft size={18} />
          </button>
          <button
            type="button"
            aria-label="Next feedback"
            onClick={() => go(1)}
            disabled={active === items.length - 1}
            className="absolute -right-4 top-1/2 hidden -translate-y-1/2 rounded-full bg-white p-2 shadow-md disabled:opacity-30 sm:flex"
          >
            <ChevronRight size={18} />
          </button>

          <div className="mt-4 flex justify-center gap-1.5">
            {items.map((item, i) => (
              <button
                key={item.id}
                type="button"
                aria-label={`Go to feedback ${i + 1}`}
                onClick={() => {
                  setActive(i);
                  scrollToIndex(i);
                }}
                className={clsx(
                  "h-1.5 rounded-full transition-all",
                  i === active ? "w-6 bg-brand-600" : "w-1.5 bg-slate-300",
                )}
              />
            ))}
          </div>
        </>
      )}
    </div>
  );
}
