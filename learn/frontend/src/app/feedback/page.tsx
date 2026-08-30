import { redirect } from "next/navigation";
import { learnerSession } from "@/lib/learner-session";
import { FeedbackForm } from "@/components/FeedbackForm";

export const metadata = { title: "Feedback · Learn Dutch in 5 Minutes" };

export default async function FeedbackPage() {
  const session = await learnerSession();
  if (!session?.user) redirect("/signin");

  return (
    <div className="mx-auto max-w-xl space-y-6">
      <header>
        <h1 className="text-3xl font-bold">Share your feedback</h1>
        <p className="mt-1 text-slate-600">
          Tell us how your learning is going. Published feedback helps other learners decide to
          start.
        </p>
      </header>

      <FeedbackForm />
    </div>
  );
}
