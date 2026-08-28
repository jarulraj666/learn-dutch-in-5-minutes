export type CourseStatus = "published" | "coming_soon";

export interface CourseSummary {
  id: string;
  title: string;
  subtitle: string;
  description: string;
  status: CourseStatus;
  /** Required modules only. */
  lesson_count: number;
  completed_count: number;
  optional_lesson_count: number;
  optional_completed_count: number;
  module_count: number;
}

export interface LessonSummary {
  id: string;
  title: string;
  title_nl: string;
  title_en: string;
  summary: string;
  duration_sec: number | null;
  order_index: number;
  is_premium: boolean;
  completed: boolean;
  percent: number;
  best_quiz_percent: number | null;
}

export interface ModuleDetail {
  id: string;
  category: string;
  title: string;
  description: string;
  order_index: number;
  is_optional: boolean;
  lessons: LessonSummary[];
}

export interface CourseDetail extends CourseSummary {
  modules: ModuleDetail[];
  next_lesson_id: string | null;
}

export interface VocabularyItem {
  id: number;
  nl: string;
  en: string;
}

export interface GrammarNote {
  title: string;
  explanation: string;
  examples: string[];
}

export interface TranscriptLine {
  speaker: string;
  line_nl: string;
  line_en: string;
}

export interface QuizQuestion {
  id: string;
  question: string;
  options: string[];
  difficulty: string;
  skill: string;
}

export interface LessonProgress {
  watched_sec: number;
  last_position_sec: number;
  percent: number;
  completed_at: string | null;
}

export interface LessonDetail {
  id: string;
  course_id: string;
  module_id: string;
  category: string;
  title: string;
  title_nl: string;
  title_en: string;
  summary: string;
  description: string;
  youtube_video_id: string;
  duration_sec: number | null;
  is_premium: boolean;
  key_phrases: string[];
  vocabulary: VocabularyItem[];
  grammar_notes: GrammarNote[];
  transcript: TranscriptLine[];
  subtitle_langs: string[];
  quiz: QuizQuestion[];
  progress: LessonProgress | null;
  prev_lesson_id: string | null;
  next_lesson_id: string | null;
}

export interface QuizAnswerResult {
  id: string;
  correct: boolean;
  given: string;
  answer: string;
  explanation: string;
}

export interface QuizResult {
  lesson_id: string;
  score: number;
  total: number;
  percent: number;
  attempt_no: number;
  results: QuizAnswerResult[];
}

export interface DashboardCourse {
  course_id: string;
  title: string;
  lessons_total: number;
  lessons_completed: number;
  percent: number;
  optional_total: number;
  optional_completed: number;
  resume_lesson_id: string | null;
  resume_lesson_title: string | null;
}

export interface Dashboard {
  courses: DashboardCourse[];
  flashcards_due: number;
  recent: Array<{
    lesson_id: string;
    title: string;
    course_id: string;
    percent: number;
    completed: boolean;
    updated_at: string;
  }>;
}

export interface FlashcardDue {
  vocab_id: number;
  nl: string;
  en: string;
  lesson_id: string;
  lesson_title: string;
  reps: number;
}

export interface Certificate {
  serial: string;
  course_id: string;
  course_title: string;
  user_name: string;
  issued_at: string;
}

export interface CertificateEligibility {
  course_id: string;
  eligible: boolean;
  lessons_total: number;
  lessons_completed: number;
  quizzes_total: number;
  quizzes_passed: number;
  pass_percent: number;
  certificate: Certificate | null;
}

export interface UserProfile {
  id: string;
  email: string | null;
  name: string | null;
  image: string | null;
  plan: string;
  role: string;
  settings: { locale: string; email_opt_in: boolean };
}

export interface AdminLearner {
  id: string;
  email: string | null;
  name: string | null;
  created_at: string;
  lessons_completed: number;
  quiz_attempts: number;
  last_active: string | null;
}
