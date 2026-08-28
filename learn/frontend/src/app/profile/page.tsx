import { redirect } from "next/navigation";
import { auth } from "@/auth";
import { api } from "@/lib/api";
import { SettingsForm } from "./SettingsForm";
import type { Certificate, UserProfile } from "@/lib/types";

export const metadata = { title: "Profile · Learn Dutch in 5 Minutes" };

export default async function ProfilePage() {
  const session = await auth();
  if (!session?.user) redirect("/signin");

  const profile = await api<UserProfile>("/api/me");
  const data = await api<{ certificates: Certificate[] }>("/api/me/export").catch(() => null);

  return (
    <div className="mx-auto max-w-2xl space-y-8">
      <header className="card flex items-center gap-4 p-6">
        {profile.image ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={profile.image} alt="" className="h-16 w-16 rounded-full" />
        ) : (
          <div className="h-16 w-16 rounded-full bg-brand-100" />
        )}
        <div>
          <h1 className="text-xl font-bold">{profile.name ?? "Learner"}</h1>
          <p className="text-sm text-slate-500">{profile.email}</p>
          <p className="mt-1 text-xs uppercase tracking-wide text-slate-400">
            {profile.plan} plan
          </p>
        </div>
      </header>

      <SettingsForm initial={profile.settings} />

      {data?.certificates && data.certificates.length > 0 && (
        <section className="card p-6">
          <h2 className="font-semibold">Certificates</h2>
          <ul className="mt-3 space-y-2 text-sm">
            {data.certificates.map((certificate) => (
              <li key={certificate.serial}>
                <a
                  href={`/certificates/${certificate.serial}`}
                  className="text-brand-700 underline"
                >
                  {certificate.course_id} — {certificate.serial}
                </a>
              </li>
            ))}
          </ul>
        </section>
      )}

      <section className="card p-6">
        <h2 className="font-semibold">Your data</h2>
        <p className="mt-1 text-sm text-slate-600">
          Download everything we store about you, or delete your account permanently. Deleting
          removes your progress, quiz results, flashcards and certificates.
        </p>
        <div className="mt-4 flex flex-wrap gap-3">
          <a href="/api/backend/me/export" className="btn-secondary text-sm" download>
            Download my data
          </a>
        </div>
      </section>
    </div>
  );
}
