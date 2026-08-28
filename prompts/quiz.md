You are writing a multiple-choice comprehension quiz for a Dutch lesson aimed at CEFR {level} learners.

## Task

Read the lesson material below and produce exactly {question_count} multiple-choice questions that check whether the learner understood the lesson.

## Question mix

For a **dialogue** lesson, use this mix:
- 3 × `comprehension` — what happened in the conversation, who said what, what someone wanted
- 2 × `vocabulary` — meaning of a word or phrase that actually appears in the lesson

For a **grammar** lesson, use this mix:
- 3 × `grammar` — apply the rule taught in the lesson (fill-in-the-blank or "which sentence is correct")
- 2 × `vocabulary` — meaning of a word used in the examples

For **vocabulary** and **common_words** lessons, use this mix:
- 4 × `vocabulary` — NL→EN or EN→NL meaning, or "which word fits this sentence"
- 1 × `comprehension` — a usage question drawn from an example sentence

## Rules

- Every question MUST be answerable from the lesson material below. Never test outside knowledge.
- Write questions and options in **English**, except for the Dutch words, phrases or sentences being tested — keep those in Dutch.
- Exactly 4 options per question. Exactly one is correct.
- `answer` MUST be a character-for-character copy of one entry in `options`.
- Distractors must be plausible and the same length/shape as the correct answer. Never use "All of the above", "None of the above", or joke options.
- Do not reuse the same correct-option position for every question — vary it.
- `explanation` is 1–2 sentences telling the learner *why* the answer is correct, referring back to the lesson. Never just restate the answer.
- `difficulty` is one of `easy`, `medium`, `hard`. Aim for roughly 2 easy, 2 medium, 1 hard.
- Keep the language at CEFR {level}. No idioms or grammar the lesson did not teach.

## Output

Return **strict JSON only** — no markdown, no commentary — in exactly this shape:

```json
{
  "quiz": [
    {
      "question": "What does 'het weer' mean?",
      "options": ["the weather", "the water", "the road", "the week"],
      "answer": "the weather",
      "explanation": "'Het weer' is introduced in the vocabulary section as the Dutch word for the weather.",
      "difficulty": "easy",
      "skill": "vocabulary"
    }
  ]
}
```

---

## Lesson material

Topic: {topic_title}
Category: {category}

### Transcript
{transcript}

### Key phrases
{key_phrases}

### Vocabulary
{vocabulary}

### Grammar notes
{grammar_notes}
