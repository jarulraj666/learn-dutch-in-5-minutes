You are writing **mock exam #{exam_number} of 5** for the **Spreken (Speaking)** section of the Dutch **Staatsexamen NT2 Programma I** (A2 civic-integration exam).

## Real exam structure to replicate exactly

- Exactly 4 parts, 16 questions total (4 per part), 36 minutes, 1 minute per answer:
  - **Part 1 — video tasks**: watch a short video of an everyday situation, then respond as if you were in it (e.g. asking a question, giving information).
  - **Part 2 — prompts and some one-picture tasks**: describe a single picture or answer a practical situation.
  - **Part 3 — prompts and some two-picture tasks**: compare two pictures, choose/react to one of them, or answer a practical situation.
  - **Part 4 — prompts and some three-picture tasks**: choose the suitable picture, narrate a 3-picture sequence, or answer a practical situation.
- Graded on 6 criteria: task achievement, vocabulary, grammar, fluency, structure, pronunciation. Pass mark is not officially published.
- Everyday A2 topics: shopping, appointments, work, neighbours, transport, health, school.
- Build each question as a short, concrete situation where the candidate has a clear role and purpose. The candidate should need to ask, answer, explain, request, choose, invite, apologise, or describe something useful in daily life — never give a memorised speech or an abstract opinion.

## Scenario progression

Make the four parts feel like one real exam session, with a different everyday context for every question:

- **Part 1:** brief encounter videos. The video ends with another person asking or saying something that needs a spoken response, for example at a shop counter, reception desk, bus stop, workplace, school, or clinic.
- **Part 2:** single-picture prompts. Ask the candidate to describe a visible situation, explain what someone should do, or respond as a person in the picture.
- **Part 3:** two-picture prompts. Ask the candidate to compare practical choices, say which option fits a stated need, or explain a difference between the pictures.
- **Part 4:** three-picture prompts. Ask the candidate to choose the suitable option for an everyday need or tell the simple sequence of events in the pictures.

The learner app gives exactly one minute to record each answer. Write instructions that can be answered naturally within that time, normally in 1-4 clear A2 sentences. Vary language functions and settings across all 16 questions; do not reuse a situation, recipient, or required action.

## Functional visual material

Use pictures sparingly, as the supplied DUO writing papers do: a picture must show information that the candidate needs in order to answer, never act as decoration.

- Across Parts 2-4, create **exactly 6 picture-based tasks**: exactly 2 `one_picture`, 2 `two_picture`, and 2 `three_picture` passages.
- The other 6 tasks in Parts 2-4 use `passage_type: "text"` with a short Dutch situation only; do not add `scene_description` to those passages. They must be completely answerable from the text instruction.
- For the 6 picture-based tasks, use clear everyday visual evidence: two broken/stolen items for a municipality or insurance report, three simple work tasks for a colleague, a bus-stop or shop choice, a short before/during/after sequence, or two practical options to compare. Generate only identifiable people and objects. Never include readable words, labels, signs, speech bubbles, or decorative stock scenes.
- Spread visual tasks across Parts 2, 3, and 4. Do not place more than two image tasks in any one part.

## Rules

- Produce **exactly 16 questions**: 4 with `part_number: 1`, 4 with `part_number: 2`, 4 with `part_number: 3`, 4 with `part_number: 4`. All `question_type` = `"open_spoken"`.
- Every question needs a passage describing its prompt material:
  - Part 1: `passage_type: "video"`, with `content_nl` = the full Dutch narration/dialogue spoken in the video, and `scene_description` (English) describing the everyday situation shown.
  - For a visual Part 2 task, use `passage_type: "one_picture"`, with `scene_description` (English) describing the single picture to generate.
  - For a visual Part 3 task, use `passage_type: "two_picture"`, with `scene_description` containing two distinct picture descriptions separated by " | ".
  - For a visual Part 4 task, use `passage_type: "three_picture"`, with `scene_description` containing three distinct picture descriptions separated by " | ".
  - For each non-visual Part 2-4 task, use `passage_type: "text"`, with a concise Dutch situation in `content_nl` and no `scene_description`.
- `question_text` gives the exact spoken instruction to the candidate, in Dutch (e.g. "Vraag de apotheker hoe vaak u dit medicijn moet innemen.").
- Every question needs a `grading_rubric`: exactly 6 entries, one per criterion (`task`, `vocabulary`, `grammar`, `fluency`, `structure`, `pronunciation`), each with a sensible `max_points` (e.g. 2-3 each, no need to sum to a fixed total since this section isn't scored numerically on the real exam).
- Every question needs a `model_answer`: a realistic A2-level spoken Dutch answer (for admin QA / future reference — never auto-graded yet).
- Only set `year_asked` if confident it matches a real historical exam question; otherwise `null`.

## Output

Return **strict JSON only** — no markdown, no commentary — matching this shape:

```json
{
  "section": "speaking",
  "exam_number": {exam_number},
  "level": "A2",
  "title": "Spreken - Oefenexamen {exam_number}",
  "instructions": "Beantwoord elke vraag mondeling binnen 1 minuut.",
  "time_limit_minutes": 36,
  "total_questions": 16,
  "parts_count": 4,
  "pass_threshold": null,
  "max_score": null,
  "passages": [
    {
      "id": "p1",
      "order_index": 1,
      "part_number": 1,
      "passage_type": "video",
      "title": "Bij de apotheek",
      "content_nl": "Goedemiddag, kan ik u helpen?",
      "scene_description": "A pharmacist greets a customer at the counter."
    }
  ],
  "questions": [
    {
      "passage_id": "p1",
      "part_number": 1,
      "order_index": 1,
      "question_text": "Vraag de apotheker hoe vaak u dit medicijn moet innemen.",
      "question_type": "open_spoken",
      "grading_rubric": [
        {"criterion": "task", "max_points": 3},
        {"criterion": "vocabulary", "max_points": 2},
        {"criterion": "grammar", "max_points": 2},
        {"criterion": "fluency", "max_points": 2},
        {"criterion": "structure", "max_points": 2},
        {"criterion": "pronunciation", "max_points": 2}
      ],
      "model_answer": "Hoe vaak moet ik dit medicijn innemen?",
      "year_asked": null
    }
  ]
}
```
