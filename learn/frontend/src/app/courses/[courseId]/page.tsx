import Link from "next/link";
import { notFound } from "next/navigation";
import { CheckCircle2, Circle, PlayCircle } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { formatDuration } from "@/lib/format";
import type { CourseDetail, ModuleDetail } from "@/lib/types";

export default async function CoursePage({ params }: { params: { courseId: string } }) {
  let course: CourseDetail;
  try {
    course = await api<CourseDetail>(`/api/courses/${params.courseId}`);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) notFound();
    throw error;
  }

  const percent = course.lesson_count
    ? Math.round((course.completed_count * 100) / course.lesson_count)
    : 0;

  const required = course.modules.filter((m) => !m.is_optional);
  const optional = course.modules.filter((m) => m.is_optional);

  return (
    <div className="space-y-8">
      <header className="rounded-2xl bg-brand p-8 text-white">
        <p className="text-sm uppercase tracking-widest opacity-80">{course.subtitle}</p>
        <h1 className="mt-1 text-3xl font-bold">{course.title}</h1>
        <p className="mt-2 max-w-3xl opacity-90">{course.description}</p>

        <div className="mt-6 flex flex-wrap items-center gap-4">
          {course.next_lesson_id && (
            <Link
              href={`/courses/${course.id}/lessons/${course.next_lesson_id}`}
              className="rounded-full bg-white px-6 py-3 font-semibold text-brand-700 transition hover:-translate-y-0.5"
            >
              {course.completed_count > 0 ? "Continue learning" : "Start learning"}
            </Link>
          )}
          <div className="min-w-[12rem] flex-1">
            <div className="h-2 overflow-hidden rounded-full bg-white/30">
              <div className="h-full rounded-full bg-white" style={{ width: `${percent}%` }} />
            </div>
            <p className="mt-1 text-sm opacity-90">
              {course.completed_count} of {course.lesson_count} core lessons complete
            </p>
          </div>
        </div>
      </header>

      {required.map((module, index) => (
        <ModuleSection
          key={module.id}
          courseId={course.id}
          module={module}
          number={index + 1}
          eyebrow={module.category === "start_here" ? "Begin here" : `Unit ${index + 1}`}
        />
      ))}

      {optional.length > 0 && (
        <section className="space-y-6 rounded-2xl border border-dashed border-brand-300 bg-brand-50/40 p-5">
          <div>
            <span className="rounded-full bg-brand-100 px-3 py-1 text-xs font-semibold text-brand-700">
              Optional add-on
            </span>
            <h2 className="mt-2 text-xl font-semibold">Practice with real conversations</h2>
            <p className="mt-1 max-w-2xl text-sm text-slate-600">
              These lessons are not required for the course or your certificate. Take them
              whenever you want to hear the grammar and vocabulary used in natural Dutch.
            </p>
          </div>

          {optional.map((module) => (
            <ModuleSection
              key={module.id}
              courseId={course.id}
              module={module}
              number={null}
              eyebrow="Optional"
            />
          ))}
        </section>
      )}
    </div>
  );
}

function ModuleSection({
  courseId,
  module,
  number,
  eyebrow,
}: {
  courseId: string;
  module: ModuleDetail;
  number: number | null;
  eyebrow: string;
}) {
  return (
    <section className="card overflow-hidden">
      <div className="border-b border-slate-200 px-5 py-4">
        <p className="text-xs uppercase tracking-widest text-slate-400">{eyebrow}</p>
        <h2 className="text-lg font-semibold">
          {number !== null && <span className="text-slate-400">{number}. </span>}
          {module.title}
        </h2>
        {module.description && (
          <p className="mt-1 text-sm text-slate-500">{module.description}</p>
        )}
      </div>

      {module.lessons.length === 0 ? (
        <p className="px-5 py-4 text-sm text-slate-500">No lessons published yet.</p>
      ) : (
        <ul className="divide-y divide-slate-100">
          {module.lessons.map((lesson, index) => (
            <li key={lesson.id}>
              <Link
                href={`/courses/${courseId}/lessons/${lesson.id}`}
                className="flex items-center gap-4 px-5 py-3 transition hover:bg-slate-50"
              >
                {lesson.completed ? (
                  <CheckCircle2 size={20} className="shrink-0 text-emerald-500" />
                ) : lesson.percent > 0 ? (
                  <PlayCircle size={20} className="shrink-0 text-brand-500" />
                ) : (
                  <Circle size={20} className="shrink-0 text-slate-300" />
                )}
                <span className="w-10 shrink-0 text-sm tabular-nums text-slate-400">
                  {number === null ? index + 1 : `${number}.${index + 1}`}
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate font-medium">
                    {lesson.title_nl || lesson.title}
                  </span>
                  {lesson.title_en && (
                    <span className="block truncate text-sm text-slate-500">
                      {lesson.title_en}
                    </span>
                  )}
                </span>
                {lesson.best_quiz_percent !== null && (
                  <span className="hidden rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-600 sm:inline">
                    Quiz {lesson.best_quiz_percent}%
                  </span>
                )}
                <span className="w-14 text-right text-sm tabular-nums text-slate-400">
                  {formatDuration(lesson.duration_sec)}
                </span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
