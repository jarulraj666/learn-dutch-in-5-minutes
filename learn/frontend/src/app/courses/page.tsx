import Link from "next/link";
import { api } from "@/lib/api";
import type { CourseSummary } from "@/lib/types";

export const metadata = { title: "Courses · Learn Dutch in 5 Minutes" };

export default async function CoursesPage() {
  const courses = await api<CourseSummary[]>("/api/courses");

  return (
    <div>
      <h1 className="text-3xl font-bold">Courses</h1>
      <p className="mt-2 text-slate-600">
        Each level is a sequence of short units built around real situations. Every unit mixes
        everyday words with the grammar that makes them usable, starting from your very first
        lesson. Real conversations are an optional add-on.
      </p>

      <div className="mt-8 grid gap-6 md:grid-cols-2 lg:grid-cols-3">
        {courses.map((course) => {
          const soon = course.status === "coming_soon";
          const percent = course.lesson_count
            ? Math.round((course.completed_count * 100) / course.lesson_count)
            : 0;

          const card = (
            <article
              className={`card flex h-full flex-col p-6 transition ${
                soon ? "opacity-60" : "hover:-translate-y-1 hover:shadow-md"
              }`}
            >
              <span className="w-fit rounded-full bg-brand-50 px-3 py-1 text-xs font-semibold text-brand-700">
                {course.subtitle}
              </span>
              <h2 className="mt-3 text-xl font-semibold">{course.title}</h2>
              <p className="mt-2 flex-1 text-sm text-slate-600">{course.description}</p>

              {soon ? (
                <p className="mt-4 text-sm font-medium text-slate-500">Coming soon</p>
              ) : (
                <div className="mt-4">
                  <div className="h-1.5 overflow-hidden rounded-full bg-slate-200">
                    <div className="h-full rounded-full bg-brand" style={{ width: `${percent}%` }} />
                  </div>
                  <p className="mt-2 text-sm text-slate-500">
                    {course.module_count} units · {course.lesson_count} core lessons · {percent}% complete
                  </p>
                  {course.optional_lesson_count > 0 && (
                    <p className="mt-1 text-xs text-slate-400">
                      + {course.optional_lesson_count} optional dialogue lessons
                    </p>
                  )}
                </div>
              )}
            </article>
          );

          return soon ? (
            <div key={course.id}>{card}</div>
          ) : (
            <Link key={course.id} href={`/courses/${course.id}`}>
              {card}
            </Link>
          );
        })}
      </div>
    </div>
  );
}
