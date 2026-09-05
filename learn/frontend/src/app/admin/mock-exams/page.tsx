import Link from "next/link";
import { redirect } from "next/navigation";
import { learnerSession } from "@/lib/learner-session";
import { api, ApiError } from "@/lib/api";
import type { MockExamSummary } from "@/lib/types";
import { MockExamActions } from "@/components/MockExamActions";
import { GenerateExamForm } from "@/components/GenerateExamForm";

export const metadata = { title: "Mock exams · Admin · Learn Dutch in 5 Minutes" };

const SECTION_LABELS: Record<string, string> = {
  reading: "Lezen (Reading)",
  listening: "Luisteren (Listening)",
  writing: "Schrijven (Writing)",
  speaking: "Spreken (Speaking)",
  knm: "KNM (Dutch Society)",
};

export default async function AdminMockExamsPage() {
  const session = await learnerSession();
  if (!session?.user) redirect("/signin");

  let exams: MockExamSummary[];
  try {
    exams = await api<MockExamSummary[]>("/api/admin/mock-exams");
  } catch (error) {
    if (error instanceof ApiError && error.status === 403) {
      return <p className="text-slate-600">You do not have access to this page.</p>;
    }
    throw error;
  }

  const bySection = exams.reduce<Record<string, MockExamSummary[]>>((groups, exam) => {
    (groups[exam.section] ??= []).push(exam);
    return groups;
  }, {});

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-3xl font-bold">Mock exams</h1>
        <Link href="/admin" className="text-sm text-slate-500 hover:text-brand-700">
          ← Admin
        </Link>
      </div>

      <GenerateExamForm />

      {Object.entries(bySection).map(([section, sectionExams]) => (
        <section key={section} className="card overflow-hidden">
          <h2 className="border-b border-slate-200 px-5 py-3 font-semibold">
            {SECTION_LABELS[section] ?? section}
          </h2>
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs uppercase tracking-wide text-slate-400">
                <th className="px-5 py-2">Exam</th>
                <th className="px-5 py-2">Status</th>
                <th className="px-5 py-2">Free preview</th>
                <th className="px-5 py-2">Questions</th>
                <th className="px-5 py-2">Actions</th>
              </tr>
            </thead>
            <tbody>
              {sectionExams.map((exam) => (
                <tr key={exam.id} className="border-t border-slate-100">
                  <td className="px-5 py-3">
                    <p className="font-medium">{exam.title}</p>
                    <p className="text-xs text-slate-400">{exam.id}</p>
                  </td>
                  <td className="px-5 py-3 capitalize text-slate-600">{exam.status}</td>
                  <td className="px-5 py-3 text-slate-600">{exam.is_free_preview ? "Yes" : "No"}</td>
                  <td className="px-5 py-3 tabular-nums text-slate-600">{exam.total_questions}</td>
                  <td className="px-5 py-3">
                    <MockExamActions id={exam.id} status={exam.status} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      ))}
    </div>
  );
}
