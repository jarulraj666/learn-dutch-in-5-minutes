You are writing **mock exam #{exam_number} of 5** for the **Luisteren (Listening)** section of the Dutch **Staatsexamen NT2 Programma I** (A2 civic-integration exam).

## Real exam structure to replicate exactly

- 25 multiple-choice questions, 45 minutes, pass mark 18/25.
- Questions are based on short fragments: some are audio-only (announcements, phone messages, radio snippets), some are **video** fragments (two people having a short everyday conversation).
- Each fragment is followed by 1-4 questions (main point, specific detail, speaker's intention).
- Language level is strictly A2: short sentences, high-frequency vocabulary, everyday topics (appointments, shopping, transport, work, health, school).

## Rules

- Produce **exactly 25 questions** total, distributed across 6-10 short fragments.
- Mark each fragment's `passage_type` as `"audio"` or `"video"` — use a roughly even mix, with at least 2 video fragments.
- For every fragment, `content_nl` MUST be the full spoken Dutch transcript (this is fed directly to text-to-speech, so it must be exactly what is spoken, no stage directions).
- For `video` fragments only, also include a `scene_description` (English, 1-2 sentences) describing what the two speakers are doing/where they are, for image generation — no camera directions, just the everyday situation (e.g. "A woman asks a pharmacist about medication at a counter.").
- Exactly 4 options per multiple-choice question, exactly one correct. `answer` must exactly match one option.
- **Distribute the correct answer evenly across option positions 1-4.** Across the 25 questions, the correct answer should land roughly 6-7 times in each of positions 1, 2, 3 and 4 — never cluster it mostly in one position. Deliberately plan the correct-answer position before writing distractors for each question.
- Write fragments and questions **in Dutch** (options too), matching the real exam.
- `explanation` (English, admin QA only): 1 short sentence pointing to the part of the transcript the answer comes from.
- Only set `year_asked` if confident it matches a real historical exam question; otherwise `null`.
- **Be careful with schedules, time ranges, dates and quantities.** If a question asks the reader to compare or combine multiple pieces of information from the transcript, work out the actual answer yourself first by checking every option one by one — do not just guess which one looks right. Only mark an option as the answer if it is the *only* one that satisfies every condition stated in the question.

## Output

Return **strict JSON only** — no markdown, no commentary — matching this shape:

```json
{
  "section": "listening",
  "exam_number": {exam_number},
  "level": "A2",
  "title": "Luisteren - Oefenexamen {exam_number}",
  "instructions": "Luister naar de fragmenten en beantwoord de vragen.",
  "time_limit_minutes": 45,
  "total_questions": 25,
  "parts_count": 1,
  "pass_threshold": 18,
  "max_score": 25,
  "passages": [
    {
      "id": "p1",
      "order_index": 1,
      "passage_type": "audio",
      "title": "Afspraak bij de tandarts",
      "content_nl": "full Dutch spoken transcript here"
    },
    {
      "id": "p2",
      "order_index": 2,
      "passage_type": "video",
      "title": "Bij de apotheek",
      "content_nl": "full Dutch spoken transcript here",
      "scene_description": "A woman asks a pharmacist about medication at a counter."
    }
  ],
  "questions": [
    {
      "passage_id": "p1",
      "order_index": 1,
      "question_text": "Hoe laat is de afspraak?",
      "question_type": "multiple_choice",
      "options": ["9.00 uur", "10.30 uur", "13.00 uur", "15.15 uur"],
      "answer": "10.30 uur",
      "explanation": "The caller confirms the appointment is at 10:30.",
      "year_asked": null
    }
  ]
}
```
