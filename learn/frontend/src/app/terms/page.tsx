export const metadata = { title: "Terms of Use · Learn Dutch in 5 Minutes" };

export default function TermsPage() {
  return (
    <article className="mx-auto max-w-3xl">
      <h1 className="text-3xl font-bold">Terms of Use</h1>
      <p className="mt-2 text-sm text-slate-500">Last updated: 18 August 2026</p>

      <Section title="The service">
        Learn Dutch in 5 Minutes is a free online Dutch course. We may add, change or remove
        lessons at any time. We do not guarantee uninterrupted availability.
      </Section>

      <Section title="Your account">
        You are responsible for the Google account you sign in with. Do not share your account or
        attempt to access other learners&apos; data.
      </Section>

      <Section title="Content">
        Lesson videos, transcripts, vocabulary, grammar notes and quizzes are our copyright. You
        may use them for your own learning. You may not republish, resell or redistribute them.
      </Section>

      <Section title="Certificates">
        Certificates confirm that you completed the lessons and passed the quizzes on this site.
        They are not an accredited qualification and carry no formal CEFR certification.
      </Section>

      <Section title="Liability">
        The course is provided as-is, without warranty. We are not liable for any loss arising
        from its use.
      </Section>
    </article>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="mt-6">
      <h2 className="text-lg font-semibold">{title}</h2>
      <p className="mt-2 text-slate-700">{children}</p>
    </section>
  );
}
