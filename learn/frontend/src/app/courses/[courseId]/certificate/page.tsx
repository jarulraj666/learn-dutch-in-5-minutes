import { redirect } from "next/navigation";
import { auth } from "@/auth";
import { api } from "@/lib/api";
import { ClaimButton } from "./ClaimButton";
import type { CertificateEligibility } from "@/lib/types";

export default async function CourseCertificatePage({
  params,
}: {
  params: { courseId: string };
}) {
  const session = await auth();
  if (!session?.user) redirect("/signin");

  const status = await api<CertificateEligibility>(
    `/api/courses/${params.courseId}/certificate`,
  );

  return (
    <div className="mx-auto max-w-xl space-y-6">
      <h1 className="text-3xl font-bold">Certificate</h1>

      <section className="card space-y-3 p-6 text-sm">
        <Row
          label="Lessons completed"
          value={`${status.lessons_completed} / ${status.lessons_total}`}
          ok={status.lessons_completed === status.lessons_total}
        />
        <Row
          label={`Quizzes passed (≥ ${status.pass_percent}%)`}
          value={`${status.quizzes_passed} / ${status.quizzes_total}`}
          ok={status.quizzes_passed === status.quizzes_total}
        />
      </section>

      {status.certificate ? (
        <a href={`/certificates/${status.certificate.serial}`} className="btn-primary">
          View your certificate
        </a>
      ) : (
        <ClaimButton courseId={params.courseId} eligible={status.eligible} />
      )}
    </div>
  );
}

function Row({ label, value, ok }: { label: string; value: string; ok: boolean }) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-slate-600">{label}</span>
      <span className={ok ? "font-medium text-emerald-600" : "font-medium text-slate-500"}>
        {value}
      </span>
    </div>
  );
}
