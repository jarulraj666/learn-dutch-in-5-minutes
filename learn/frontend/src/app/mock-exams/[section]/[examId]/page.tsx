import { ExamPageClient } from "@/components/ExamPageClient";

export default async function TakeMockExamPage({ params }: { params: { examId: string } }) {
  return <ExamPageClient examId={params.examId} />;
}
