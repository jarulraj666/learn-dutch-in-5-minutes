"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import Image from "next/image";
import clsx from "clsx";
import { ChevronLeft, ChevronRight } from "lucide-react";

export type HeroSlide = {
  id: string;
  eyebrow?: string;
  title: string;
  body: string;
  primaryCta: { label: string; href: string };
  secondaryCta?: { label: string; href: string };
  className: string;
  showLogo?: boolean;
};

const AUTO_ADVANCE_MS = 5000;

/** Scroll-snap hero carousel — same interaction pattern as TestimonialCarousel. */
export function HeroCarousel({ slides }: { slides: HeroSlide[] }) {
  const trackRef = useRef<HTMLDivElement>(null);
  const [active, setActive] = useState(0);
  const [paused, setPaused] = useState(false);
  const activeRef = useRef(0);

  const scrollToIndex = useCallback((index: number) => {
    const track = trackRef.current;
    const slide = track?.children[index] as HTMLElement | undefined;
    if (!track || !slide) return;
    const delta = slide.getBoundingClientRect().left - track.getBoundingClientRect().left;
    track.scrollTo({ left: track.scrollLeft + delta, behavior: "smooth" });
  }, []);

  useEffect(() => {
    activeRef.current = active;
  }, [active]);

  useEffect(() => {
    if (slides.length <= 1 || paused) return;
    const id = setInterval(() => {
      const next = (activeRef.current + 1) % slides.length;
      setActive(next);
      scrollToIndex(next);
    }, AUTO_ADVANCE_MS);
    return () => clearInterval(id);
  }, [slides.length, paused, scrollToIndex]);

  useEffect(() => {
    const track = trackRef.current;
    if (!track) return;

    function onScroll() {
      const items = Array.from(track!.children) as HTMLElement[];
      let closest = 0;
      let closestDist = Infinity;
      items.forEach((item, i) => {
        const dist = Math.abs(item.offsetLeft - track!.scrollLeft);
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

  function go(dir: 1 | -1) {
    const next = (active + dir + slides.length) % slides.length;
    setActive(next);
    scrollToIndex(next);
  }

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
        className="flex snap-x snap-mandatory overflow-x-auto scroll-smooth rounded-3xl [-ms-overflow-style:none] [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
      >
        {slides.map((slide) => (
          <section
            key={slide.id}
            className={clsx(
              "w-full shrink-0 snap-start px-6 py-16 text-center text-white sm:px-12",
              slide.className,
            )}
          >
            {slide.showLogo && (
              <Image
                src="/logo.png"
                alt=""
                width={112}
                height={112}
                priority
                className="mx-auto mb-6 rounded-full shadow-lg ring-4 ring-white/30"
              />
            )}
            {slide.eyebrow && (
              <span className="mb-4 inline-block rounded-full bg-white/15 px-4 py-1 text-xs font-semibold uppercase tracking-wide">
                {slide.eyebrow}
              </span>
            )}
            <h1 className="mx-auto max-w-3xl text-4xl font-bold leading-tight sm:text-5xl">
              {slide.title}
            </h1>
            <p className="mx-auto mt-4 max-w-2xl text-lg opacity-90">{slide.body}</p>
            <div className="mt-8 flex flex-wrap justify-center gap-4">
              <Link
                href={slide.primaryCta.href}
                className="rounded-full bg-white px-8 py-3 font-semibold text-brand-700 transition hover:-translate-y-0.5"
              >
                {slide.primaryCta.label}
              </Link>
              {slide.secondaryCta && (
                <Link
                  href={slide.secondaryCta.href}
                  className="rounded-full border border-white/60 px-8 py-3 font-semibold transition hover:bg-white/10"
                >
                  {slide.secondaryCta.label}
                </Link>
              )}
            </div>
          </section>
        ))}
      </div>

      {slides.length > 1 && (
        <>
          <button
            type="button"
            aria-label="Previous slide"
            onClick={() => go(-1)}
            className="absolute left-2 top-1/2 hidden -translate-y-1/2 rounded-full bg-white/90 p-2 text-slate-700 shadow-md sm:flex"
          >
            <ChevronLeft size={18} />
          </button>
          <button
            type="button"
            aria-label="Next slide"
            onClick={() => go(1)}
            className="absolute right-2 top-1/2 hidden -translate-y-1/2 rounded-full bg-white/90 p-2 text-slate-700 shadow-md sm:flex"
          >
            <ChevronRight size={18} />
          </button>

          <div className="mt-4 flex justify-center gap-1.5">
            {slides.map((slide, i) => (
              <button
                key={slide.id}
                type="button"
                aria-label={`Go to slide ${i + 1}`}
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
