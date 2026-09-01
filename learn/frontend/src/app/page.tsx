import Link from "next/link";
import Image from "next/image";
import {
  BookOpenCheck,
  Clock,
  GraduationCap,
  Languages,
  ListChecks,
  Subtitles,
} from "lucide-react";
import { api } from "@/lib/api";
import { TestimonialCarousel } from "@/components/TestimonialCarousel";
import type { CourseSummary, FeedbackPublic, PublicStats } from "@/lib/types";

const FEATURES = [
  { icon: Clock, title: "Five-minute lessons", body: "Short enough to actually finish, structured enough to build real skill." },
  { icon: BookOpenCheck, title: "Structured curriculum", body: "Units built around real situations, each mixing words and the grammar that unlocks them." },
  { icon: ListChecks, title: "Quizzes with explanations", body: "Check what stuck, and find out why an answer was right or wrong." },
  { icon: Languages, title: "Vocabulary you keep", body: "Every word from every lesson, with spaced-repetition flashcards." },
  { icon: Subtitles, title: "Dutch & English transcripts", body: "Follow along line by line, switch the translation on or off." },
  { icon: GraduationCap, title: "Certificate of completion", body: "Finish a level and pass every quiz to earn a shareable certificate." },
];

export default async function HomePage() {
  let courses: CourseSummary[] = [];
  let stats: PublicStats = { active_learners: 350 };
  let testimonials: FeedbackPublic[] = [];
  try {
    courses = await api<CourseSummary[]>("/api/courses", { authenticated: false });
  } catch {
    // The landing page must render even when the API is unavailable.
  }
  try {
    [stats, testimonials] = await Promise.all([
      api<PublicStats>("/api/public/stats", { authenticated: false }),
      api<FeedbackPublic[]>("/api/feedback/public", { authenticated: false }),
    ]);
  } catch {
    // Fall back to defaults above.
  }
  const published = courses.filter((c) => c.status === "published");
  const lessonCount = published.reduce((n, c) => n + c.lesson_count, 0);
  const unitCount = published.reduce((n, c) => n + c.module_count, 0);

  return (
    <div className="space-y-20">
      <section className="rounded-3xl bg-brand px-6 py-16 text-center text-white sm:px-12">
        <Image
          src="/logo.png"
          alt=""
          width={112}
          height={112}
          priority
          className="mx-auto mb-6 rounded-full shadow-lg ring-4 ring-white/30"
        />
        <h1 className="mx-auto max-w-3xl text-4xl font-bold leading-tight sm:text-5xl">
          Learn Dutch in 5 Minutes a Day
        </h1>
        <p className="mx-auto mt-4 max-w-2xl text-lg opacity-90">
          A complete, free Dutch course built from short video lessons. Grammar starts in the
          very first unit, so you build real sentences from day one — with vocabulary,
          transcripts and quizzes for every episode.
        </p>
        <div className="mt-8 flex flex-wrap justify-center gap-4">
          <Link
            href="/courses"
            className="rounded-full bg-white px-8 py-3 font-semibold text-brand-700 transition hover:-translate-y-0.5"
          >
            Start learning
          </Link>
          <Link
            href="/dashboard"
            className="rounded-full border border-white/60 px-8 py-3 font-semibold transition hover:bg-white/10"
          >
            My learning
          </Link>
          <Link
            href="/exam-justification"
            className="rounded-full border border-white/60 px-8 py-3 font-semibold transition hover:bg-white/10"
          >
            Writing coach
          </Link>
        </div>
      </section>

      <section>
        <h2 className="text-center text-3xl font-bold">Everything in one place</h2>
        <div className="mt-10 grid gap-6 md:grid-cols-2 lg:grid-cols-3">
          {FEATURES.map(({ icon: Icon, title, body }) => (
            <article key={title} className="card p-6">
              <span className="grid h-11 w-11 place-items-center rounded-xl bg-brand-50 text-brand-700">
                <Icon size={20} />
              </span>
              <h3 className="mt-4 font-semibold">{title}</h3>
              <p className="mt-1 text-sm text-slate-600">{body}</p>
            </article>
          ))}
        </div>
      </section>

      {published.length > 0 && (
        <section>
          <h2 className="text-center text-3xl font-bold">Choose your level</h2>
          <div className="mx-auto mt-10 grid max-w-4xl gap-6 md:grid-cols-2">
            {courses.map((course) => (
              <article key={course.id} className="card p-6">
                <span className="rounded-full bg-brand-50 px-3 py-1 text-xs font-semibold text-brand-700">
                  {course.subtitle}
                </span>
                <h3 className="mt-3 text-xl font-semibold">{course.title}</h3>
                <p className="mt-2 text-sm text-slate-600">{course.description}</p>
                {course.status === "published" ? (
                  <Link
                    href={`/courses/${course.id}`}
                    className="btn-primary mt-4 px-5 py-2 text-sm"
                  >
                    {course.lesson_count + course.optional_lesson_count} lessons — open course
                  </Link>
                ) : (
                  <p className="mt-4 text-sm font-medium text-slate-500">Coming soon</p>
                )}
              </article>
            ))}
          </div>
        </section>
      )}

      <section className="rounded-3xl bg-white px-6 py-12 text-center shadow-sm">
        <div className="mx-auto grid max-w-4xl gap-8 sm:grid-cols-4">
          <Stat value={`${stats.active_learners}+`} label="Active learners" />
          <Stat value={`${lessonCount}+`} label="Video lessons" />
          <Stat value={`${unitCount}`} label="Course units" />
          <Stat value="100%" label="Free" />
        </div>
      </section>

      {testimonials.length > 0 && (
        <section>
          <h2 className="text-center text-3xl font-bold">What learners say</h2>
          <div className="mx-auto mt-10 max-w-5xl">
            <TestimonialCarousel items={testimonials} />
          </div>
        </section>
      )}
    </div>
  );
}

function Stat({ value, label }: { value: string; label: string }) {
  return (
    <div>
      <p className="text-gradient text-4xl font-bold">{value}</p>
      <p className="mt-1 text-sm text-slate-500">{label}</p>
    </div>
  );
}
