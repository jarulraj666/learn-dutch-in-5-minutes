You are writing **mock exam #{exam_number} of 5** for the **KNM (Kennis van de Nederlandse Maatschappij / Dutch Society)** section of the Dutch **Staatsexamen NT2 Programma I** (A2 civic-integration exam).

## Real exam structure to replicate exactly

- 40 multiple-choice questions, 45 minutes, pass mark 28/40.
- This section tests **factual knowledge of Dutch society**, not language comprehension: customs, education, healthcare, housing, history & geography.
- Each question is a short scenario or factual statement followed by a multiple-choice question.

## Rules

- Produce **exactly 40 questions**, tagged with `category` — **exactly 5 questions per theme** for the 8 official KNM themes: `customs` (omgangsvormen, waarden en normen), `work_income` (werk en inkomen), `education` (onderwijs en opvoeding), `healthcare` (gezondheid en gezondheidszorg), `housing` (wonen), `institutions` (instanties), `government` (staatsinrichting en rechtsstaat), `history_geography` (geschiedenis en geografie). Keep each theme in one uninterrupted block of 5, because the player shows a theme screen before each block.
- **One passage per question** (`passage_type: "text"`), because the real exam shows one situation photo per question. Write every question so it stands on its own and leave `content_nl` empty; only add a short situation sentence there when the question cannot be understood without it. Always give the passage a `scene_description` for that question's photo. `scene_description` is handed directly to a media creator: write it as a complete, copy-ready English prompt naming the people, visible action, objects, and setting, and end it with "Naturalistic educational assessment still, landscape 16:9, eye-level medium-wide shot, realistic daylight, clear uncluttered composition, no readable text, labels, logos, speech bubbles or watermarks."
- Write questions in the real exam's pattern: a short **named-person situation** of one to three very short sentences, each on its own line, followed by the actual question on the last line. Example: `"Ramish is verhuisd.\nHoe krijgt hij een huisarts in zijn nieuwe woonplaats?"`. Use varied first names from different backgrounds. Roughly a quarter of the questions may be plain factual questions without a situation (e.g. "Wat is de hoofdstad van Nederland?"). Use the polite "u"-form instead of a name when the answer options are written in the "u"-form.
- Name concrete Dutch institutions and terms where the real exam does: DigiD, BSN, Belastingdienst, UWV, KvK, Juridisch Loket, consultatiebureau, huisartsenpost, eigen risico, statiegeld, woningcorporatie, makelaar, notaris.
- Exactly 3 options per question, exactly one correct. `answer` must exactly match one option. Keep options short — usually a single noun phrase or short sentence ending in a full stop.
- **Distribute the correct answer evenly across option positions 1-3** — never cluster it mostly in one position. Deliberately plan the correct-answer position before writing distractors for each question.
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
      "content_nl": "Je hebt griep en wilt naar de dokter.",
      "scene_description": "A patient sitting in a Dutch general practitioner's waiting room."
    }
  ],
  "questions": [
    {
      "passage_id": "p1",
      "order_index": 1,
      "question_text": "Naar wie ga je eerst als je ziek bent?",
      "question_type": "multiple_choice",
      "options": ["De huisarts", "Het ziekenhuis", "De apotheek"],
      "answer": "De huisarts",
      "explanation": "In the Dutch healthcare system, the huisarts (GP) is the first point of contact and gatekeeper to specialist care.",
      "category": "healthcare",
      "year_asked": null
    }
  ]
}
```
