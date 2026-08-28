export const metadata = { title: "Privacy Policy · Learn Dutch in 5 Minutes" };

export default function PrivacyPage() {
  return (
    <article className="prose mx-auto max-w-3xl">
      <h1 className="text-3xl font-bold">Privacy Policy</h1>
      <p className="mt-2 text-sm text-slate-500">Last updated: 18 August 2026</p>

      <Section title="Who we are">
        Learn Dutch in 5 Minutes (learndutchin5minutes.nl) provides free Dutch language
        lessons. For questions about this policy, contact info@learndutchin5minutes.nl.
      </Section>

      <Section title="What we collect">
        When you sign in with Google we receive and store your name, email address and profile
        picture. While you use the site we store your lesson progress, quiz answers and scores,
        flashcard review history, certificates and your account settings.
      </Section>

      <Section title="Why we collect it">
        Solely to run the course: to keep you signed in, to remember where you stopped, to score
        your quizzes and to issue certificates. We do not sell or share your data, and we do not
        use it for advertising.
      </Section>

      <Section title="Cookies">
        We set an essential cookie to keep you signed in and a local preference recording that you
        dismissed the cookie notice. Lesson videos are embedded from YouTube, which sets its own
        cookies when a video loads. See Google&apos;s privacy policy for details.
      </Section>

      <Section title="Your rights">
        You can download everything we store about you, and delete your account permanently, from
        your profile page. Deleting your account removes your progress, quiz results, flashcards
        and certificates immediately and irreversibly.
      </Section>

      <Section title="Retention">
        We keep your data for as long as your account exists. Deleting your account deletes it.
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
