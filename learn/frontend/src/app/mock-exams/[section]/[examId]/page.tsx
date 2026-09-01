import { redirect } from "next/navigation";
import { learnerSession } from "@/lib/learner-session";
import { TakeExamClient } from "@/components/TakeExamClient";

export default async function TakeMockExamPage({ params }: { params: { examId: string } }) {
  const session = await learnerSession();
  if (!session?.user) redirect("/signin");

  return <TakeExamClient examId={params.examId} />;
}
