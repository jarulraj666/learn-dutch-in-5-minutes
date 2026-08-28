"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { callApi } from "@/lib/format";

// Minimal surface of the YouTube IFrame API that we rely on.
type YTPlayer = {
  getCurrentTime(): number;
  getDuration(): number;
  seekTo(seconds: number, allowSeekAhead: boolean): void;
  destroy(): void;
};

declare global {
  interface Window {
    YT?: {
      Player: new (el: HTMLElement, opts: Record<string, unknown>) => YTPlayer;
      PlayerState: { PLAYING: number; ENDED: number };
    };
    onYouTubeIframeAPIReady?: () => void;
  }
}

let apiPromise: Promise<void> | null = null;

function loadIframeApi(): Promise<void> {
  if (window.YT?.Player) return Promise.resolve();
  if (apiPromise) return apiPromise;

  apiPromise = new Promise<void>((resolve) => {
    window.onYouTubeIframeAPIReady = () => resolve();
    const script = document.createElement("script");
    script.src = "https://www.youtube.com/iframe_api";
    document.head.appendChild(script);
  });
  return apiPromise;
}

const REPORT_INTERVAL_MS = 5000;

type Props = {
  lessonId: string;
  videoId: string;
  durationSec: number | null;
  startAtSec: number;
  initialPercent: number;
  onProgress?: (percent: number, completed: boolean) => void;
};

export function YouTubePlayer({
  lessonId,
  videoId,
  durationSec,
  startAtSec,
  initialPercent,
  onProgress,
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const playerRef = useRef<YTPlayer | null>(null);
  const watchedRef = useRef(Math.round((initialPercent / 100) * (durationSec ?? 0)));
  const lastTimeRef = useRef(startAtSec);
  const [percent, setPercent] = useState(initialPercent);

  const report = useCallback(async () => {
    const player = playerRef.current;
    if (!player) return;
    const position = Math.floor(player.getCurrentTime());
    const duration = Math.floor(player.getDuration()) || durationSec || 0;

    // Count only forward playback so scrubbing cannot inflate watch time.
    const delta = position - lastTimeRef.current;
    if (delta > 0 && delta < REPORT_INTERVAL_MS / 1000 + 2) {
      watchedRef.current += delta;
    }
    lastTimeRef.current = position;

    try {
      const result = await callApi<{ percent: number; completed: boolean }>("progress", {
        method: "POST",
        body: JSON.stringify({
          lesson_id: lessonId,
          position_sec: position,
          watched_sec: Math.min(watchedRef.current, duration || watchedRef.current),
          duration_sec: duration || null,
        }),
      });
      setPercent(result.percent);
      onProgress?.(result.percent, result.completed);
    } catch {
      // Progress is best-effort; a failed report must never interrupt playback.
    }
  }, [durationSec, lessonId, onProgress]);

  useEffect(() => {
    let timer: ReturnType<typeof setInterval> | null = null;
    let cancelled = false;

    loadIframeApi().then(() => {
      if (cancelled || !containerRef.current || !window.YT) return;

      playerRef.current = new window.YT.Player(containerRef.current, {
        videoId,
        playerVars: {
          rel: 0,
          modestbranding: 1,
          start: startAtSec > 5 ? startAtSec : 0,
          cc_lang_pref: "en",
        },
        events: {
          onStateChange: (event: { data: number }) => {
            if (event.data === window.YT?.PlayerState.PLAYING) {
              if (!timer) timer = setInterval(report, REPORT_INTERVAL_MS);
            } else {
              if (timer) {
                clearInterval(timer);
                timer = null;
              }
              void report();
            }
          },
        },
      });
    });

    return () => {
      cancelled = true;
      if (timer) clearInterval(timer);
      playerRef.current?.destroy();
      playerRef.current = null;
    };
  }, [report, startAtSec, videoId]);

  return (
    <div>
      <div className="aspect-video w-full overflow-hidden rounded-2xl bg-black shadow-lg">
        <div ref={containerRef} className="h-full w-full" />
      </div>
      <div className="mt-3 flex items-center gap-3">
        <div className="h-2 flex-1 overflow-hidden rounded-full bg-slate-200">
          <div
            className="h-full rounded-full bg-brand transition-all"
            style={{ width: `${percent}%` }}
          />
        </div>
        <span className="w-12 text-right text-sm tabular-nums text-slate-500">{percent}%</span>
      </div>
    </div>
  );
}
