You are writing **mock exam #{exam_number} of 5** for the **Lezen (Reading)** section of the Dutch **Staatsexamen NT2 Programma I** (A2 civic-integration exam).

This prompt is based on a close read-through of multiple official DUO practice exams. Follow the *pattern* observed there — passage count, question style, personalization, table use — but **invent original scenarios**: different names, different numbers, different situations. Never reproduce the exact wording of the reference texts described below.

## Real exam structure to replicate

- 25 multiple-choice questions, 65 minutes, pass mark 18/25.
- The exam is made of **10-13 separate, independent texts**. Each text gets **2 or 3 questions** (never just 1, never more than 3) — this is different from what you might expect from generic "one text, one question" advice; the real exam clusters 2-3 questions per text.
- **Every passage starts with one short context sentence** (in Dutch) that tells the reader *who is reading this and why*, before the document itself — e.g. "Alle bewoners van een dorp krijgen een brief.", "Jasper ontvangt een e-mail van zijn collega.", "In de krant staat een tekst over Bartjes Kringloopcentrum.", "Op internet staat een folder met informatie over EHBO-cursussen.". Put this sentence as the first line of `content_nl`, then a blank line, then the document itself (with its own heading/greeting if it has one).
- **Texts must be full length** — a genuine multi-paragraph document of roughly 120-200 words, with at least 3 paragraphs and at least 8 complete sentences. Write 2-4 short, clear sentences in each paragraph, plus a greeting/sign-off where appropriate (e.g. "Met vriendelijke groet"). Do not write stripped-down notices or one-line paragraphs.
- **Questions are personalized.** Most questions open with a one-sentence scenario naming a fictional person and their specific situation, THEN the actual question — e.g. "Gaston woont in de Flamingostraat.\nWanneer moet hij zijn auto weghalen op zaterdag 13 juni?" or "Myra geeft les op een basisschool. Ze wil een EHBO-cursus volgen die past bij haar werk.\nWelke cursus is het meest geschikt voor Myra?". Put the full scenario + question together in `question_text` (use `\n` between sentences if that reads more naturally). Use a different first name for each question's persona; do not reuse the same name across a whole exam.
- Each question tests skim/scan for a specific detail, applying a rule/condition correctly, or (occasionally) the main point/purpose of the text — never outside knowledge.
- Language level is strictly A2: short sentences, high-frequency vocabulary, everyday topics (housing, work, health, shopping, school, appointments, public services, community life).

## Realistic scenario categories (generate NEW originals inspired by these — do not copy)

Real exams draw from a recurring pool of everyday-life document types. For each exam, pick a **varied mix** across categories like these (not all in one exam, but variety across the 5 oefenexamens overall):
- An educational/informational guide or how-to article (e.g. study tips, health tips)
- A community/village/neighbourhood-association letter about a local event (with a date, time, route or program)
- A commercial service folder/leaflet with a **pricing or tariff table** (delivery, repair, rental — price depends on two combined variables) plus a bulleted list of conditions
- A casual work-colleague email about a social outing or work event (an invitation, RSVP details, what to bring)
- A short informal colleague email about a small mishap or request (forgotten item, favour, quick question) — sometimes shown with visible email header fields (`Aan:`, `CC:`, `Onderwerp:`)
- A neighbourhood-association or club letter about a paid group activity (sports day, workshop) with costs, sign-up deadlines and named contact people for different tasks
- An office/colleague email organizing a group gift or celebration (wedding, retirement, baby) with a small committee of named people each handling a different task
- An online course/training brochure listing 2-3 course options with different durations, content and prices
- A newspaper or local-news article about a local business, charity or initiative (how it works, what happens to profits/proceeds)
- A workplace policy/procedure text (e.g. how to report sick, how to request leave, safety rules) written as bullet/heading-structured guidance
- A professional practice folder (dentist, doctor, clinic) with a **staff/schedule table** (who works which days) plus multiple conditional contact rules (normal hours vs. urgent/after-hours, each with a different phone number)
- A school/course-institution practical-info guide with a **holiday/term-dates table**, an advance-notice rule for absence, and a list of open-house/info-day dates
- A workplace sick-leave policy with an **escalation chain** (who to contact first, who to contact if unreachable, what happens after a longer absence) — distinct from a simple one-contact sick-leave notice
- A neighbourhood or club event invitation with a **timed program/agenda** (a list of times and activities) plus a list of discussion topics or activity choices
- A job vacancy posting or CV/job-application preparation guide (what to include, how to apply, a deadline)
- A short personal letter/note from one neighbour to another (a request, a small complaint, an offer to help) — distinct from a neighbourhood-association mass letter
- A municipality (gemeente) website article or announcement about a local civic topic (permits, waste collection, subsidies, road works)
- A school/course email between a student and teacher, or between two fellow students (medecursist) — asking about an assignment, requesting absence, arranging group work
- A manager's email bundling **several unrelated rule/schedule changes at once** (e.g. new opening-day roster, a new loyalty-card system, a change in a recurring chore's frequency) — the question asks about just one of the bundled changes
- A boss's email with a **leave/vacation-request table** (who's already booked off which week) plus written rules (max weeks allowed, minimum staff always on duty, a cut-off week after which no one may be off) — the question asks the reader to combine the table and the rules to find the one valid remaining option
- An informational text structured as **FAQ-style question headings** (e.g. "Hoe meld ik mij ziek?", "Wat moet ik meenemen?") each followed by its answer, rather than a plain bulleted list
- An office celebration email where colleagues **vote on a shortlist of options** (e.g. two possible gifts) and the most-chosen one wins — the question asks who to contact or how to take part

## Passage images: never

Passages are always pure text. Always leave `scene_description` empty/omitted on every passage — do **not** add a photo to any passage, even for ads/notices that could plausibly show a product photo. All visual content in this exam belongs only in the picture-choice question options described below.

## Picture-choice questions (exactly one per exam)

The real exam occasionally replaces text options with **photos**: the passage describes a set of objects (e.g. an email listing what's in a lost bag), and each of the 3-4 answer options is a small photo showing a different combination of everyday objects — the reader picks the photo matching the passage. Include **exactly one** such question in this exam, on whichever passage fits it most naturally (e.g. "what's in the bag/room/basket?"). For that one question:
- `options`: short text labels for grading, e.g. `["glasses, book, laptop", "phone, wallet, book", ...]` — one per option, in plain English or Dutch, describing what the photo shows.
- `option_image_prompts`: a parallel array (same length/order as `options`), each a short English image-generation prompt for that option's photo. Each prompt must specify a **rectangular landscape image, 1600x400px**, and must instruct that all objects be **arranged in a single horizontal row, spaced evenly side by side** (not stacked, not overlapping, not scattered) on a plain background — e.g. "A rectangular 1600x400px flat-lay product photo, plain background, with reading glasses, a paperback book, and a closed laptop arranged in a single horizontal row side by side, evenly spaced.".
- `answer`: must exactly match the option whose objects match what the passage describes.
Omit `option_image_prompts` entirely for every other (ordinary text-option) question in the exam.

## Example of the expected passage structure and length (context line + document)

```
Alle bewoners van een dorp krijgen een brief.

Aan de bewoners van het dorp

Onderwerp: Jaarlijkse hardloopwedstrijd

Wij willen u met deze brief informatie geven over de jaarlijkse hardloopwedstrijd in ons dorp. Ook willen wij u vertellen wat er die dag anders is voor het verkeer. We willen dat alles zo goed mogelijk gaat en we hopen dat u weinig last hebt van de wedstrijd.

Ongeveer 500 hardlopers doen mee aan de hardloopwedstrijd. De start en de finish zijn op het Dorpsplein. U kunt naar de hardlopers komen kijken, als u daar zin in heeft.

Datum: zaterdag 13 juni
Tijd: van 11.00 uur tot 16.00 uur
Route: Dorpsplein – Dorpsstraat – Bergsebaan – Flamingostraat – Dorpsplein

We willen dat alles veilig is voor de hardlopers, het verkeer en het publiek. Daarom sluiten wij een aantal straten en wegen af. Op de route mogen tot 17.00 uur geen auto’s staan. Wij vragen u daarom uw auto vóór zaterdagmorgen 13 juni 10.00 uur weg te halen. Auto’s die er daarna nog staan zal de politie wegslepen.

Wij bieden u onze excuses aan voor de overlast en wij danken u voor uw medewerking.

Met vriendelijke groet,

Piet Jansen
Organisator hardloopwedstrijd
```

With 2-3 questions like:
- "Waarom krijgen de dorpsbewoners deze brief van Piet Jansen?" (main purpose)
- "Gaston woont in de Flamingostraat.\nWanneer moet hij zijn auto weghalen op zaterdag 13 juni?" (personalized detail lookup)

Write your own version of a passage like this — same structure and length, invented content (different event, names, dates, streets).

## Example of a service/tariff passage with a table and bullet points

```
In een meubelwinkel ligt een folder met informatie over de transportservice.

Verzamel- en transportservice

Hebt u meubels gezien die u wilt kopen? En wilt u dat wij deze meubels bij u thuisbezorgen? Dan kunt u gebruikmaken van onze transportservice.

Hoe werkt het? U maakt een lijstje met de meubels, op internet of in onze winkel. Wij verzamelen deze meubels en bezorgen alles bij u thuis. Dit alles voor een klein bedrag. De prijzen voor het bezorgen ziet u hieronder.

Tarieven:
Hoeveel weegt uw bestelling? | Bezorging op de begane grond | Bezorging op de 1e, 2e, 3e etc. verdieping
0-199 kg | € 54,- | € 64,-
200 kg of meer | € 104,- | € 144,-

Deze prijzen zijn geldig voor één adres. Wilt u de meubels op meer adressen laten bezorgen? Ga dan voor meer informatie naar de informatiebalie in onze winkel.

Bezorging
- De levertijd van de meubels is ten minste twee weken.
- U kunt op onze website zien op welke dagen wij meubels thuisbezorgen.
- Wilt u weten hoe laat wij de meubels bezorgen? Bel dan naar onze klantenservice. Dit kan alleen op de dag van de bezorging, vanaf 8 uur 's ochtends.
- Woont u op de vijfde verdieping of hoger? Wij bezorgen alleen als er een lift is.
```

Include at least 1-2 passages like this per exam: a service/company notice built around a small **tariff table** (price depends on two combined variables, e.g. weight tier AND floor/location) plus a bulleted list of conditions. Questions on this kind of passage should require reading the *correct row and column* of the table together (e.g. "Modibo woont op de tweede verdieping. Hij heeft een tafel van 20 kilo gekocht. Wat moet hij hiervoor betalen?"), or applying one of the bulleted conditions correctly — never just restating a single number in isolation.

**Table formatting:** whenever a passage includes a table (tariffs, schedules, staff/day rosters, holiday/term dates, etc.), write each row on its own line with columns separated by ` | ` (a pipe with a space on each side), header row first — e.g. `Type reparatie | Gewone fiets | Elektrische fiets`. This is the only format the learner app renders as an actual table; do not use aligned spaces/tabs instead.

## Rules

- Produce **exactly 25 questions** total, distributed across **10-13 passages**, with **2 or 3 questions per passage** (never 1, never more than 3) — plan the passage count so the questions divide evenly into this range (e.g. eleven passages: seven with 2 questions + four with 3 questions = 25).
- Vary passage length realistically: most passages are 80-180 word full documents; a couple of shorter email-style ones are fine, but none should be a single bare sentence.
- Every question must be answerable from its own passage alone. Never test outside knowledge.
- **3 or 4 options per multiple-choice question** (match the real exam's variety — not every question needs a 4th distractor), exactly one correct.
- `answer` MUST be a character-for-character copy of one entry in `options`.
- Distractors must be plausible and similar in length/shape. Never use "All of the above" / "None of the above".
- **Distribute the correct answer evenly across option positions.** Don't cluster the correct answer mostly in one position (e.g. always 2nd) — deliberately vary it question to question.
- Write passages and questions **in Dutch** (this mimics the real exam, which is entirely in Dutch). Do not translate to English.
- `explanation` (in English, for admin QA only): 1 short sentence pointing to where in the passage the answer comes from.
- Only set `year_asked` on a question if you are confident it matches a real historical Staatsexamen NT2 Programma I exam question you have knowledge of. Leave it `null` for every newly composed question — never guess.
- **Be careful with schedules, time ranges, dates, quantities and tables.** If a question asks the reader to compare or combine multiple time ranges (e.g. "on which day does X work in both the afternoon AND the evening") or to look up a value in a table with two variables (e.g. price by weight tier AND floor), work out the actual answer yourself first by checking every option against the passage's numbers/times/table cells one by one — do not just guess which one looks right. Only mark an option as the answer if it is the *only* one that satisfies every condition stated in the question.

## Output

Return **strict JSON only** — no markdown, no commentary — matching this shape:

```json
{
  "section": "reading",
  "exam_number": {exam_number},
  "level": "A2",
  "title": "Lezen - Oefenexamen {exam_number}",
  "instructions": "Lees de teksten en beantwoord de vragen.",
  "time_limit_minutes": 65,
  "total_questions": 25,
  "parts_count": 1,
  "pass_threshold": 18,
  "max_score": 25,
  "passages": [
    {
      "id": "p1",
      "order_index": 1,
      "passage_type": "text",
      "title": "Kamer te huur",
      "content_nl": "Een kennis stuurt een advertentie voor een kamer.\n\nfull Dutch passage text here (120-200 words, at least 8 complete sentences)",
      "scene_description": "A cosy single furnished room with a bed, desk and window, product-photo style (only fill this in for the rare ad/notice that would show a real photo; leave empty otherwise)"
    },
    {
      "id": "p2",
      "order_index": 2,
      "passage_type": "text",
      "title": "Bericht van de gemeente",
      "content_nl": "Een bewoner krijgt een brief van de gemeente.\n\nfull Dutch passage text here (120-200 words, at least 8 complete sentences)"
    }
  ],
  "questions": [
    {
      "passage_id": "p1",
      "order_index": 1,
      "question_text": "Wat kost de kamer per maand?",
      "question_type": "multiple_choice",
      "options": ["€350", "€450", "€550", "€650"],
      "answer": "€450",
      "explanation": "The ad states the rent is €450 per month.",
      "year_asked": null
    },
    {
      "passage_id": "p1",
      "order_index": 2,
      "question_text": "Karim wil de kamer bezichtigen.\nWanneer kan hij dat het beste doen?",
      "question_type": "multiple_choice",
      "options": ["'s ochtends", "'s middags", "'s avonds"],
      "answer": "'s avonds",
      "explanation": "The ad says viewings are only possible in the evening.",
      "year_asked": null
    },
    {
      "passage_id": "p2",
      "order_index": 3,
      "question_text": "Waarom stuurt de gemeente deze brief vooral?",
      "question_type": "multiple_choice",
      "options": ["Een formulier insturen", "Een afspraak maken", "Een boete betalen"],
      "answer": "Een formulier insturen",
      "explanation": "The letter's main purpose is to ask the reader to return a form.",
      "year_asked": null
    }
  ]
}
```
Note: this abbreviated example shows only 2 passages with 2 and 1 questions for illustration — your real output must contain 10-13 passages and exactly 25 questions total, with every passage carrying 2 or 3 questions (never 1).

