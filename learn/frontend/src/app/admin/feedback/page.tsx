import Link from "next/link";
import { redirect } from "next/navigation";
import { Star } from "lucide-react";
import { learnerSession } from "@/lib/learner-session";
import { api, ApiError } from "@/lib/api";
import { formatDate } from "@/lib/format";
import type { AdminFeedback } from "@/lib/types";
import { FeedbackActions } from "@/components/FeedbackActions";

export const metadata = { title: "Feedback · Admin · Learn Dutch in 5 Minutes" };

export default async function AdminFeedbackPage() {
  const session = await learnerSession();
  if (!session?.user) redirect("/signin");

  let feedback: AdminFeedback[];
  try {
    feedback = await api<AdminFeedback[]>("/api/admin/feedback");
  } catch (error) {
    if (error instanceof ApiError && error.status === 403) {
      return <p className="text-slate-600">You do not have access to this page.</p>;
    }
    throw error;
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-3xl font-bold">Feedback</h1>
        <Link href="/admin" className="text-sm text-slate-500 hover:text-brand-700">
          ← Admin
        </Link>
      </div>

      <section className="card overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-xs uppercase tracking-wide text-slate-400">
              <th className="px-5 py-2">Learner</th>
              <th className="px-5 py-2">Rating</th>
              <th className="px-5 py-2">Comment</th>
              <th className="px-5 py-2">Status</th>
              <th className="px-5 py-2">Submitted</th>
              <th className="px-5 py-2">Actions</th>
            </tr>
          </thead>
          <tbody>
            {feedback.map((item) => (
              <tr key={item.id} className="border-t border-slate-100 align-top">
                <td className="px-5 py-3">
                  <p className="font-medium">{item.name ?? "—"}</p>
                  <p className="text-xs text-slate-400">{item.email ?? "—"}</p>
                </td>
                <td className="px-5 py-3">
                  <div className="flex gap-0.5">
                    {Array.from({ length: 5 }, (_, i) => (
                      <Star
                        key={i}
                        size={14}
                        className={
                          i < item.rating
                            ? "fill-amber-400 text-amber-400"
                            : "fill-transparent text-slate-300"
                        }
                      />
                    ))}
                  </div>
                </td>
                <td className="max-w-sm px-5 py-3 text-slate-600">{item.comment}</td>
                <td className="px-5 py-3 capitalize text-slate-600">{item.status}</td>
                <td className="px-5 py-3 text-slate-500">{formatDate(item.created_at)}</td>
                <td className="px-5 py-3">
                  <FeedbackActions id={item.id} status={item.status} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  );
}
