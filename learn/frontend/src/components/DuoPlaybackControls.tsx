"use client";

import clsx from "clsx";
import { Pause, Play, RotateCcw, RotateCw } from "lucide-react";

export function DuoPlaybackControls({
  mediaPlaying,
  mediaProgress,
  onSkip,
  onToggle,
  compact = false,
}: {
  mediaPlaying: boolean;
  mediaProgress: number;
  onSkip: (seconds: number) => void;
  onToggle: () => void;
  compact?: boolean;
}) {
  const skipIcon = compact ? 24 : 31;
  return (
    <div className={clsx("ml-auto flex shrink-0 items-center text-slate-950", compact ? "gap-1" : "gap-1 sm:gap-3 sm:pt-1")}>
      <button onClick={() => onSkip(-10)} className={clsx("relative grid shrink-0 place-items-center rounded-full transition-colors hover:bg-slate-200 focus-visible:bg-slate-200", compact ? "h-8 w-8" : "h-10 w-10")} title="10 seconden terug" aria-label="10 seconden terug">
        <RotateCcw size={skipIcon} strokeWidth={2.25} />
        <span className="absolute pt-0.5 text-[0.55rem] font-bold leading-none">10</span>
      </button>
      <button onClick={onToggle} className={clsx("relative grid shrink-0 place-items-center rounded-full p-1 text-[#e8863c] shadow-sm transition-transform hover:scale-105 focus-visible:scale-105", compact ? "h-11 w-11" : "h-16 w-16")} style={{ background: `conic-gradient(from -90deg, #e8863c ${mediaProgress}%, #e5e7eb ${mediaProgress}% 100%)` }} title={mediaPlaying ? "Pauze" : "Afspelen"} aria-label={mediaPlaying ? "Pauze" : "Afspelen"}>
        <span className="absolute inset-1 grid place-items-center rounded-full bg-white" aria-hidden="true" />
        {mediaPlaying ? <Pause className="relative" size={compact ? 18 : 28} fill="currentColor" /> : <Play className="relative ml-0.5" size={compact ? 20 : 31} fill="currentColor" />}
      </button>
      <button onClick={() => onSkip(10)} className={clsx("relative grid shrink-0 place-items-center rounded-full transition-colors hover:bg-slate-200 focus-visible:bg-slate-200", compact ? "h-8 w-8" : "h-10 w-10")} title="10 seconden vooruit" aria-label="10 seconden vooruit">
        <RotateCw size={skipIcon} strokeWidth={2.25} />
        <span className="absolute pt-0.5 text-[0.55rem] font-bold leading-none">10</span>
      </button>
    </div>
  );
}