import { redirect } from "next/navigation";
import { learnerSession } from "@/lib/learner-session";
import { ExamPageClient } from "@/components/ExamPageClient";

export default async function MockExamAttemptPage({
  params,
}: {
  params: { examId: string; attemptNo: string };
}) {
  const session = await learnerSession();
  if (!session?.user) redirect("/signin");

  return <ExamPageClient examId={params.examId} viewAttemptNo={Number(params.attemptNo)} />;
}
