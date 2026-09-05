"use client";

import { useState } from "react";
import { CheckoutButton } from "@/components/CheckoutButton";
import type { MockExamSection } from "@/lib/types";

const SECTIONS: { key: MockExamSection; label: string }[] = [
  { key: "reading", label: "Lezen (Reading)" },
  { key: "listening", label: "Luisteren (Listening)" },
  { key: "writing", label: "Schrijven (Writing)" },
  { key: "speaking", label: "Spreken (Speaking)" },
  { key: "knm", label: "KNM (Dutch Society)" },
];

/** Section picker + checkout button for the single-section premium tier. */
export function SectionCheckoutCard() {
  const [section, setSection] = useState<MockExamSection>("reading");

  return (
    <div className="mt-8">
      <label htmlFor="section" className="block text-xs font-semibold uppercase tracking-wide text-slate-500">
        Choose a section
      </label>
      <select
        id="section"
        value={section}
        onChange={(e) => setSection(e.target.value as MockExamSection)}
        className="mt-2 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
      >
        {SECTIONS.map((s) => (
          <option key={s.key} value={s.key}>
            {s.label}
          </option>
        ))}
      </select>
      <CheckoutButton
        product="section"
        section={section}
        label="Unlock this section — €9"
        className="btn-secondary mt-4 block w-fit px-5 py-2 text-sm"
      />
    </div>
  );
}
