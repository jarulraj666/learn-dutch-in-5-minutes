import Link from "next/link";

export const metadata = { title: "Contact · Learn Dutch in 5 Minutes" };

const FAQS = [
  {
    question: "Is Learn Dutch in 5 Minutes free?",
    answer: "Yes, the full course is free to use.",
  },
  {
    question: "Do I need an account?",
    answer:
      "You can browse lessons without one, but signing in with Google lets you track progress, take quizzes, use flashcards and earn certificates.",
  },
  {
    question: "How are lessons structured?",
    answer:
      "Each lesson is a short video with vocabulary, grammar notes, a transcript and a quiz to check your understanding.",
  },
  {
    question: "How do I get a certificate?",
    answer:
      "Complete every lesson in a course and pass its quizzes, then claim your certificate from the course's certificate page.",
  },
  {
    question: "What are flashcards for?",
    answer: "They help you review vocabulary from your lessons using spaced repetition.",
  },
  {
    question: "How do I report a bug or suggest a topic?",
    answer: (
      <>
        Use the <Link href="/feedback" className="text-brand-700 underline">Feedback</Link> page,
        or email us directly.
      </>
    ),
  },
  {
    question: "How do I delete my account or data?",
    answer: (
      <>
        You can download or permanently delete your data from your{" "}
        <Link href="/profile" className="text-brand-700 underline">profile page</Link>. See our{" "}
        <Link href="/privacy" className="text-brand-700 underline">Privacy Policy</Link> for
        details.
      </>
    ),
  },
];

export default function ContactPage() {
  return (
    <article className="mx-auto max-w-3xl">
      <h1 className="text-3xl font-bold">Contact</h1>
      <p className="mt-4 text-slate-600">
        Have a question, found a bug, or want to share feedback about the course? We&apos;d love
        to hear from you.
      </p>
      <p className="mt-6">
        <a
          href="mailto:learndutchin5minutes@gmail.com"
          className="text-lg font-medium text-brand-700 hover:underline"
        >
          learndutchin5minutes@gmail.com
        </a>
      </p>

      <h2 className="mt-12 text-2xl font-bold">Frequently asked questions</h2>
      <div className="mt-4 divide-y divide-slate-200">
        {FAQS.map(({ question, answer }) => (
          <div key={question} className="py-4">
            <h3 className="font-semibold">{question}</h3>
            <p className="mt-1 text-sm text-slate-600">{answer}</p>
          </div>
        ))}
      </div>
    </article>
  );
}
