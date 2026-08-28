"use client";

import Link from "next/link";
import { useState } from "react";
import clsx from "clsx";
import { CheckCircle2, ChevronDown, Circle, PlayCircle } from "lucide-react";
import type { ModuleDetail } from "@/lib/types";
import { formatDuration } from "@/lib/format";

type Props = {
  courseId: string;
  modules: ModuleDetail[];
  currentLessonId?: string;
  completedIds?: Set<string>;
};

export function PlaylistSidebar({ courseId, modules, currentLessonId, completedIds }: Props) {
  const initiallyOpen = modules.find((m) =>
    m.lessons.some((l) => l.id === currentLessonId),
  )?.id;
  const [open, setOpen] = useState<Record<string, boolean>>(
    Object.fromEntries(modules.map((m) => [m.id, m.id === (initiallyOpen ?? modules[0]?.id)])),
  );

  const total = modules.reduce(
    (n, m) => (m.is_optional ? n : n + m.lessons.length),
    0,
  );
  const done = modules.reduce(
    (n, m) =>
      m.is_optional
        ? n
        : n + m.lessons.filter((l) => completedIds?.has(l.id) ?? l.completed).length,
    0,
  );

  return (
    <aside className="card overflow-hidden">
      <div className="border-b border-slate-200 px-4 py-3">
        <p className="text-sm font-semibold">Course content</p>
        <p className="mt-1 text-xs text-slate-500">
          {done} of {total} core lessons complete
        </p>
        <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-slate-200">
          <div
            className="h-full rounded-full bg-brand"
            style={{ width: `${total ? Math.round((done * 100) / total) : 0}%` }}
          />
        </div>
      </div>

      <div className="max-h-[70vh] overflow-y-auto">
        {modules.map((module, moduleIndex) => {
          const number = module.is_optional ? null : moduleIndex + 1;
          return (
          <section key={module.id} className="border-b border-slate-100 last:border-0">
            <button
              onClick={() => setOpen((s) => ({ ...s, [module.id]: !s[module.id] }))}
              className="flex w-full items-center justify-between px-4 py-3 text-left hover:bg-slate-50"
            >
              <span className="min-w-0">
                <span className="text-sm font-semibold">
                  {number !== null && <span className="text-slate-400">{number}. </span>}
                  {module.title}
                </span>
                <span className="ml-2 text-xs text-slate-400">{module.lessons.length}</span>
                {module.is_optional && (
                  <span className="mt-1 block text-[11px] font-medium uppercase tracking-wide text-brand-600">
                    Optional add-on
                  </span>
                )}
              </span>
              <ChevronDown
                size={16}
                className={clsx("shrink-0 transition", open[module.id] && "rotate-180")}
              />
            </button>

            {open[module.id] && (
              <ul>
                {module.lessons.map((lesson, lessonIndex) => {
                  const isCurrent = lesson.id === currentLessonId;
                  const isDone = completedIds?.has(lesson.id) ?? lesson.completed;
                  return (
                    <li key={lesson.id}>
                      <Link
                        href={`/courses/${courseId}/lessons/${lesson.id}`}
                        className={clsx(
                          "flex items-start gap-3 px-4 py-2.5 text-sm transition",
                          isCurrent
                            ? "bg-brand-50 font-medium text-brand-800"
                            : "text-slate-600 hover:bg-slate-50",
                        )}
                      >
                        {isDone ? (
                          <CheckCircle2 size={16} className="mt-0.5 shrink-0 text-emerald-500" />
                        ) : isCurrent ? (
                          <PlayCircle size={16} className="mt-0.5 shrink-0 text-brand-600" />
                        ) : (
                          <Circle size={16} className="mt-0.5 shrink-0 text-slate-300" />
                        )}
                        <span className="flex-1">
                          <span className="line-clamp-2">
                            <span className="text-slate-400">
                              {number === null ? lessonIndex + 1 : `${number}.${lessonIndex + 1}`}{" "}
                            </span>
                            {lesson.title_nl || lesson.title}
                          </span>
                          {lesson.title_en && (
                            <span className="mt-0.5 block truncate text-xs text-slate-400">
                              {lesson.title_en}
                            </span>
                          )}
                          <span className="mt-0.5 block text-xs text-slate-400">
                            {formatDuration(lesson.duration_sec)}
                          </span>
                        </span>
                      </Link>
                    </li>
                  );
                })}
              </ul>
            )}
          </section>
          );
        })}
      </div>
    </aside>
  );
}
