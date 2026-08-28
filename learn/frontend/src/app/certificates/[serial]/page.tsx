import { notFound } from "next/navigation";
import { api, ApiError } from "@/lib/api";
import { formatDate } from "@/lib/format";
import type { Certificate } from "@/lib/types";

export default async function CertificatePage({ params }: { params: { serial: string } }) {
  let certificate: Certificate;
  try {
    certificate = await api<Certificate>(`/api/certificates/${params.serial}`, {
      authenticated: false,
    });
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) notFound();
    throw error;
  }

  return (
    <div className="mx-auto max-w-3xl">
      <div className="card overflow-hidden border-4 border-brand-200 p-12 text-center">
        <p className="text-sm uppercase tracking-[0.3em] text-brand-600">
          Certificate of Completion
        </p>
        <p className="mt-8 text-slate-500">This certifies that</p>
        <h1 className="mt-2 text-4xl font-bold">{certificate.user_name}</h1>
        <p className="mt-6 text-slate-500">has completed</p>
        <h2 className="text-gradient mt-2 text-2xl font-semibold">{certificate.course_title}</h2>
        <p className="mt-8 text-sm text-slate-500">
          Issued {formatDate(certificate.issued_at)} · Serial {certificate.serial}
        </p>
        <p className="mt-1 text-xs text-slate-400">learndutchin5minutes.nl</p>
      </div>

      <p className="mt-6 text-center text-sm text-slate-500">
        Anyone can verify this certificate at this URL.
      </p>
    </div>
  );
}
