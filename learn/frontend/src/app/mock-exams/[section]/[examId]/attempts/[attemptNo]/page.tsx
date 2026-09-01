import { redirect } from "next/navigation";
import { learnerSession } from "@/lib/learner-session";
import { TakeExamClient } from "@/components/TakeExamClient";

export default async function MockExamAttemptPage({
  params,
}: {
  params: { examId: string; attemptNo: string };
}) {
  const session = await learnerSession();
  if (!session?.user) redirect("/signin");

  return <TakeExamClient examId={params.examId} viewAttemptNo={Number(params.attemptNo)} />;
}
