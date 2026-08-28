import Link from "next/link";
import { notFound } from "next/navigation";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { learnerSession } from "@/lib/learner-session";
import { api, ApiError } from "@/lib/api";
import { LessonTabs } from "@/components/LessonTabs";
import { PlaylistSidebar } from "@/components/PlaylistSidebar";
import { YouTubePlayer } from "@/components/YouTubePlayer";
import type { CourseDetail, LessonDetail } from "@/lib/types";

export default async function LessonPage({
  params,
}: {
  params: { courseId: string; lessonId: string };
}) {
  const session = await learnerSession();

  let lesson: LessonDetail;
  let course: CourseDetail;
  try {
    [lesson, course] = await Promise.all([
      api<LessonDetail>(`/api/lessons/${params.lessonId}`),
      api<CourseDetail>(`/api/courses/${params.courseId}`),
    ]);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) notFound();
    throw error;
  }

  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_22rem]">
      <div className="min-w-0">
        <Link
          href={`/courses/${params.courseId}`}
          className="mb-3 inline-flex items-center gap-1 text-sm text-slate-500 hover:text-brand-700"
        >
          <ChevronLeft size={16} /> Back to course
        </Link>

        <YouTubePlayer
          lessonId={lesson.id}
          videoId={lesson.youtube_video_id}
          durationSec={lesson.duration_sec}
          startAtSec={lesson.progress?.last_position_sec ?? 0}
          initialPercent={lesson.progress?.percent ?? 0}
        />

        <h1 className="mt-5 text-2xl font-bold">{lesson.title_nl || lesson.title}</h1>
        {lesson.title_en && <p className="mt-1 text-lg text-slate-500">{lesson.title_en}</p>}

        <LessonTabs lesson={lesson} signedIn={Boolean(session?.user)} />

        <nav className="mt-6 flex items-center justify-between gap-3">
          {lesson.prev_lesson_id ? (
            <Link
              href={`/courses/${params.courseId}/lessons/${lesson.prev_lesson_id}`}
              className="btn-secondary"
            >
              <ChevronLeft size={16} /> Previous
            </Link>
          ) : (
            <span />
          )}
          {lesson.next_lesson_id && (
            <Link
              href={`/courses/${params.courseId}/lessons/${lesson.next_lesson_id}`}
              className="btn-primary"
            >
              Next lesson <ChevronRight size={16} />
            </Link>
          )}
        </nav>
      </div>

      <div className="lg:sticky lg:top-20 lg:self-start">
        <PlaylistSidebar
          courseId={params.courseId}
          modules={course.modules}
          currentLessonId={lesson.id}
        />
      </div>
    </div>
  );
}
