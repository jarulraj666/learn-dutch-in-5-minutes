You are writing **mock exam #{exam_number} of 5** for the **Schrijven (Writing)** section of the Dutch **Staatsexamen NT2 Programma I** (A2 civic-integration exam).

## Real exam structure to replicate exactly

- Exactly 4 tasks, 40 minutes total: **1 form-filling task** + **3 short writing tasks**.
- Max 37 points total across the 4 tasks; DUO does not publish an official pass mark. Use a conservative study target of 25/37 points (about 68%) without calling it an official pass score.
- The candidate writes short, practical Dutch messages for an everyday recipient. Each task gives a concrete situation, a clear reader, and 2-4 required information points. The candidate must decide how to phrase those points; never ask for a long essay or a grammar exercise.

## Verified DUO practice-paper structure

The three supplied DUO A2 practice papers each contain exactly these four independent task types. Copy this structure and difficulty, but invent all content.

1. **One e-mail or briefje:** the candidate writes a new functional message to a named person, such as a classmate, teacher, colleague, manager, neighbour, or friend. There is no incoming e-mail to answer: the candidate composes a new message.
2. **One wijkkrant text:** the candidate writes a short personal text for a neighbourhood newspaper. Start with `U krijgt elke week een wijkkrant. Iedereen uit de buurt mag iets voor deze krant schrijven.` Ask for a familiar topic, such as a weekend, favourite clothes, an annual celebration, food, a hobby, or a local activity. Require at least three sentences and give exactly three idea prompts, followed by `Dit is mijn tekst over ...:`.
3. **One form task:** the candidate completes a practical form. Use a sports-club registration, insurance claim, municipal problem report, library or course registration, appointment request, or similar everyday service. State that some details must be invented. The blank form must contain labelled fields; relevant choice fields may use `O` checkboxes. Where appropriate, require a date and a short description of a problem, event, or preference.
4. **One additional e-mail or briefje:** a different functional-message situation, with a different recipient and purpose from task 1.

Rotate the page order across generated exams, as in the practice papers. Do not always begin with the form. For example, use e-mail / wijkkrant / form / e-mail for one exam; wijkkrant / e-mail / form / e-mail for another; and e-mail / form / wijkkrant / briefje for another.

## Page layout and originality

- The paper has a candidate-name line followed by one complete task per page. Each task has a short bold title, a situation/instruction block, and a generous answer area.
- Use small visual evidence in **at most one** task per exam, as in the supplied papers. A picture is allowed only when the candidate must identify concrete information from it, for example two street problems to report, three stolen/damaged household items for an insurance form, or three practical jobs to leave for a colleague. Do not use decorative images, portraits, or generic scenes.
- For that optional visual task, create a `passage_type: "one_picture"`, `two_picture`, or `three_picture` passage with an English `scene_description` for each image. Link the question to that passage and include `Kijk naar de plaatjes.` in the Dutch task instructions. All other non-form tasks must remain paper instructions without a passage.
- Create a passage only for the **form task**. Its `content_nl` is the blank form. E-mail, briefje, and wijkkrant tasks have `passage_id: null`, because the instruction itself is the complete paper prompt.
- In `question_text`, use the DUO paper style: short situation paragraphs, Dutch bullet points where the candidate must include specific facts, and explicit closing lines such as `Schrijf de e-mail.` and `Schrijf in hele zinnen.`
- Each e-mail task must use this plain-text sequence exactly: a short topical title such as `Afspraak verzetten`, `Boek lenen`, `Dienst ruilen`, or `Vrije dag aanvragen`; a short situation paragraph; `U schrijft een e-mail aan [naam].`; 2-4 requirements starting with `• U schrijft ...`; then `Schrijf de e-mail.` on its own line and `Schrijf in hele zinnen.` on the last line. The topical title becomes the prefilled subject line in the paper email box. A briefje task uses `Briefje voor [naam]`, a short situation, `Schrijf een briefje voor [naam].`, three `• U ...` requirements, `Schrijf in hele zinnen.`, and a preprinted answer frame with `Hallo [naam],` at the top and `Alvast bedankt!` followed by `Groeten,` at the bottom.
- Do not use Markdown in any field. In particular, do not use `**`, `#`, Markdown bullets, or code formatting. Use only plain Dutch text and the literal bullet character `•` where required.
- The official practice exams are reference material for **format and difficulty only**. Invent every scenario, person, organisation, location, date, amount, and sentence. Do not reproduce or closely paraphrase a source task, its wording, or its names.
- Across a set of generated exams, cover varied daily-life settings: home, neighbours, work, school, health appointments, travel, shops, clubs, public services, and family events. Do not repeat the same setting within one exam.

## Rules

- Produce **exactly 4 questions**, `part_number` 1-4, each `question_type` = `"open_written"`, and one or two passages: the form task plus an optional functional visual task. Questions without a form or visual reference must set `passage_id` to `null`.
- Do not make the form task always Part 1. Its question gives the situation, any required incident details, and says `Vul het formulier in.` Its passage has `passage_type: "text"` and contains only the blank form layout.
- The blank form must copy this DUO paper layout exactly, adapting only the organisation, service, and relevant choices:
  1. Form title, for example `Inschrijfformulier Sportclub SPRINT`.
  2. `Persoonsgegevens` heading, followed by one factual field per line: `Voor- en achternaam`, `Adres`, `Postcode`, `Woonplaats`, `Telefoonnummer`, `Geslacht`, and `Geboortedatum`.
  3. Immediately after `Geslacht`, put the choices on their own line: `O man / O vrouw`.
  4. A clear section question, followed by 3 relevant selectable choices on separate lines. For a sports form, this is `Welke groepsles wilt u nu gaan doen?` followed by `O Fitness`, `O Yoga`, and `O Hardlopen`.
  5. A second clear section question, followed by 3 selectable choices on separate lines. For a sports form, this is `Hoe vaak wilt u komen?` followed by `O 1x per week`, `O 2x per week`, and `O meer dan 2x per week`.
  6. Two final open fields relevant to the service. For a sports form, use `Waarom kiest u voor deze groepsles?` and `Hoe is uw gezondheid?`.
- Keep every field blank; never fill an answer into the form. Do not put a checkbox choice on the same line as a field label, except the exact `O man / O vrouw` gender line.
- Rotate between these verified form families from the three papers:
  - **Registration form:** title, `Persoonsgegevens`, the seven factual rows, `Geslacht O man / O vrouw`, two grouped three-choice questions, then two multi-line open questions. This mirrors the sports-club form.
  - **Insurance claim:** title, `Persoonsgegevens` with `Achternaam`, `Voorletters`, `Adres`, `Telefoonnummer`, and `E-mail`; then `Datum van de schade`; then `Omschrijving gestolen spullen en schade` with exactly three blank bullet entries. The task must ask the learner to give the date and describe three picture-supported incidents.
  - **Municipality report:** title `Meldingsformulier`, `Persoonsgegevens` with the six factual rows, then a multi-line location field such as `In welke straat zijn er problemen?`, followed by a larger `Wat zijn de problemen?` field. The task must ask the learner to report two visible problems from the optional evidence pictures.
- Represent headings and form labels as plain text lines with no Markdown or numbering. Use `O ` or `0 ` only for checkbox options. Use the literal bullet `•` only for the three separate incident entries in an insurance claim.
- Give every e-mail task a short topical title; give every note task a title beginning `Briefje voor ...`; give the free-writing task a topical title. This title belongs at the beginning of `question_text`, because there is no passage for these paper tasks.
- Make the expected response length realistic: a form contains short field values; a briefje or e-mail has 3-6 short sentences; a wijkkrant text has at least 3 sentences. Do not include word counts in learner-facing text.
- Assign `max_score` to each task so they sum to exactly 37 (e.g. 7, 10, 10, 10).
- Each question needs a `grading_rubric`: an array of exactly five `{criterion, max_points}` entries, in this order: `adequacy_understandability`, `grammar`, `spelling`, `vocabulary`, and `cohesion`. The entries must sum to the task's `max_score`.
- `adequacy_understandability` carries the most weight and is the gatekeeper: it checks that the answer is on-topic, understandable, and completes every required bullet point. Give it 3 of 7 points for the form task and 4 of 10 points for each other task. Allocate the remaining points across grammar, spelling, vocabulary, and cohesion. For the form task, spelling of factual personal details must be assessed carefully.
- Within `adequacy_understandability`, assess the correct response format for the task type: an e-mail must have an appropriate greeting, message, and closing; a briefje must communicate every requested action; a wijkkrant text must have at least three complete sentences and address all three idea prompts; and a form must complete every factual field, use relevant choices, and answer each open field. These are task-completion checks, not extra scoring categories.
- Each question needs a `model_answer`: a realistic A2-level Dutch answer that would score full marks (for admin QA / future auto-grading reference — never shown to learners as "the" answer since these are open tasks).
- Instructions and prompts are in Dutch (matching the real exam); the `model_answer` is in Dutch.
- Only set `year_asked` if confident it matches a real historical exam question; otherwise `null`.

## Output

Return **strict JSON only** — no markdown, no commentary — matching this shape:

```json
{
  "section": "writing",
  "exam_number": {exam_number},
  "level": "A2",
  "title": "Schrijven - Oefenexamen {exam_number}",
  "instructions": "Maak de 4 schrijfopdrachten. Lees bij elke opdracht eerst de situatie en schrijf daarna je antwoord in het Nederlands.",
  "time_limit_minutes": 40,
  "total_questions": 4,
  "parts_count": 4,
  "pass_threshold": null,
  "max_score": 37,
  "passages": [
    {
      "id": "p1",
      "order_index": 1,
      "part_number": 1,
      "passage_type": "text",
      "title": "Inschrijfformulier bibliotheek",
      "content_nl": "Naam:\nAdres:\nPostcode en woonplaats:\nGeboortedatum:\nTelefoonnummer:\nReden van aanmelding:"
    },
    {
      "id": "p2",
      "order_index": 2,
      "part_number": 2,
      "passage_type": "text",
      "title": "Bericht van je buurvrouw",
      "content_nl": "Hallo,\n\nKun jij zaterdagmiddag mijn pakketje aannemen? Ik ben dan niet thuis.\n\nGroet,\nSanne"
    }
  ],
  "questions": [
    {
      "passage_id": "p1",
      "part_number": 1,
      "order_index": 1,
      "question_text": "Je heet Anna de Vries. Je woont in de Kerkstraat 12, 3512 AB Utrecht. Je bent geboren op 4 maart 1990. Je telefoonnummer is 06 12345678. Je wilt boeken lenen voor je cursus Nederlands.\n\nVul het formulier in.",
      "question_type": "open_written",
      "max_score": 7,
      "grading_rubric": [
        {"criterion": "adequacy_understandability", "max_points": 3},
        {"criterion": "grammar", "max_points": 1},
        {"criterion": "spelling", "max_points": 1},
        {"criterion": "vocabulary", "max_points": 1},
        {"criterion": "cohesion", "max_points": 1}
      ],
      "model_answer": "Naam: Anna de Vries\nAdres: Kerkstraat 12\nPostcode en woonplaats: 3512 AB Utrecht\nGeboortedatum: 04-03-1990\nTelefoonnummer: 06 12345678\nReden van aanmelding: Ik wil boeken lenen voor mijn cursus Nederlands.",
      "year_asked": null
    }
  ]
}
```
