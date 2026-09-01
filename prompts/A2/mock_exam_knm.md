You are writing **mock exam #{exam_number} of 5** for the **KNM (Kennis van de Nederlandse Maatschappij / Dutch Society)** section of the Dutch **Staatsexamen NT2 Programma I** (A2 civic-integration exam).

## Real exam structure to replicate exactly

- 40 multiple-choice questions, 45 minutes, pass mark 28/40.
- This section tests **factual knowledge of Dutch society**, not language comprehension: customs, education, healthcare, housing, history & geography.
- Each question is a short scenario or factual statement followed by a multiple-choice question.

## Rules

- Produce **exactly 40 questions**, tagged with `category` — **exactly 8 questions per category**: `customs`, `education`, `healthcare`, `housing`, `history_geography`.
- Group questions under short scenario passages (`passage_type: "text"`, 4-8 questions can share one passage, or use one question per passage — whichever reads naturally) describing a real-life situation (e.g. "Je kind wordt 4 jaar oud." / "Je hebt griep en wilt naar de dokter.").
- Exactly 4 options per question, exactly one correct. `answer` must exactly match one option.
- **Distribute the correct answer evenly across option positions 1-4.** Across the 40 questions, the correct answer should land roughly 10 times in each of positions 1, 2, 3 and 4 — never cluster it mostly in one position. Deliberately plan the correct-answer position before writing distractors for each question.
- **Factual accuracy matters most in this section** — only state facts about Dutch laws, institutions, customs, geography and history that you are confident are correct (e.g. the role of the huisarts as gatekeeper to specialist care, primary school starting age, the housing corporation/social housing system, well-known Dutch holidays and historical facts). If unsure of a specific number/rule, phrase the question around a more general, safely-correct fact instead of guessing a precise figure.
- Write scenarios and questions **in Dutch** (matching the real exam).
- `explanation` (English, admin QA only): 1 short sentence stating the real-world fact that makes the answer correct.
- Only set `year_asked` if confident it matches a real historical exam question; otherwise `null`.
- **Be careful with schedules, time ranges, dates and quantities.** If a question asks the reader to compare or combine multiple facts, work out the actual answer yourself first by checking every option one by one — do not just guess which one looks right. Only mark an option as the answer if it is the *only* one that satisfies every condition stated in the question.

## Output

Return **strict JSON only** — no markdown, no commentary — matching this shape:

```json
{
  "section": "knm",
  "exam_number": {exam_number},
  "level": "A2",
  "title": "KNM - Oefenexamen {exam_number}",
  "instructions": "Beantwoord de vragen over de Nederlandse maatschappij.",
  "time_limit_minutes": 45,
  "total_questions": 40,
  "parts_count": 1,
  "pass_threshold": 28,
  "max_score": 40,
  "passages": [
    {
      "id": "p1",
      "order_index": 1,
      "passage_type": "text",
      "title": "Naar de huisarts",
      "content_nl": "Je hebt griep en wilt naar de dokter."
    }
  ],
  "questions": [
    {
      "passage_id": "p1",
      "order_index": 1,
      "question_text": "Naar wie ga je eerst als je ziek bent?",
      "question_type": "multiple_choice",
      "options": ["De huisarts", "Het ziekenhuis", "De apotheek", "De tandarts"],
      "answer": "De huisarts",
      "explanation": "In the Dutch healthcare system, the huisarts (GP) is the first point of contact and gatekeeper to specialist care.",
      "category": "healthcare",
      "year_asked": null
    }
  ]
}
```
