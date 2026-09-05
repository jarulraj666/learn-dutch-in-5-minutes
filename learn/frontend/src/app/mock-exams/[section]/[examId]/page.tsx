import { TakeExamClient } from "@/components/TakeExamClient";

export default async function TakeMockExamPage({ params }: { params: { examId: string } }) {
  return <TakeExamClient examId={params.examId} />;
}
