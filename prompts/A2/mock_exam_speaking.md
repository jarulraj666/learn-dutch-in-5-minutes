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

- **Part 1:** short personal video questions. The one visible adult speaker must be directly involved and speak as themselves, using `ik` or `mijn`. Each `content_nl` is a natural Dutch cue in 2-3 short A2 sentences of roughly 13-26 words and suitable for a 5-10 second delivery: first a simple personal statement about a daily habit, preference, food, work, travel, health or free time; then one direct question for the learner followed by one explicit imperative follow-up beginning with `Vertel...`. Insert ` <break time="1s" /> ` after every sentence except the final sentence, so the spoken video has a one-second pause between each sentence and no trailing pause. Do not write a two-person dialogue, a narration, greetings, generic offers of help, visual-inference questions, or extra background details. The learner must know exactly which two personal details to answer. Use an ordinary setting that visually supports the speaker's statement, such as a living room, kitchen, bicycle, workplace, park, or desk.

**Mandatory Part 1 self-check before returning JSON:** Every Part 1 `content_nl` must begin with a personal `ik` or `mijn` statement, never `Hallo`, `Goedemorgen`, `Goedemiddag`, `Goedenavond`, or another greeting. The actor must ask one direct question about the learner's own experience, preference, frequency or routine, then finish with a separate sentence beginning `Vertel` that requests the second detail. Insert exactly one ` <break time="1s" /> ` between each pair of sentences, and never after the final sentence. Reject and rewrite any Part 1 script that fails any check.
- **Part 2:** one-picture prompts. Give a very short naming setup for one or two visible people, for example `Dit zijn [naam] en [familierelatie].`, then ask the candidate to tell something about them and name exactly three visible details. The details can cover people, clothing, objects, location, actions, or relationship. Keep the task answerable from one picture.

Part 2 may also use a short event setup for one visible person, for example `[Naam] heeft een pakketje ontvangen.`, then ask `Vertel wat er is gebeurd. Vertel ook wat [naam] nu kan doen.` Require the learner to describe the visible event and one sensible next action. Keep the setup above the picture and the two `Vertel...` instructions below it.
- **Part 3:** two-picture prompts. Give a very short concrete situation, then ask the candidate to compare the practical options, make a choice, or explain which option fits a stated need.
- **Part 4:** three-picture prompts. Give a very short concrete situation, then ask the candidate to tell a simple sequence, describe the people or objects across the pictures, or explain an everyday activity.

The learner app gives exactly one minute to record each answer. Vary language functions and settings across all 16 questions; do not reuse a situation, recipient, or required action.

### Response scope

- **Short-response tasks:** ask for one visible fact, action, object, simple preference, or personal routine, with at most one simple reason. The learner should be able to answer in **1-2 clear A2 sentences**.
- **Extended-response tasks:** ask for two explicitly linked details, such as decline an invitation + give a reason, choose a visible option + explain why, describe an activity + say when the learner does it, or give information + explain what happens next. The learner should be able to answer in **2-4 complete A2 sentences**.
- Make every requested detail explicit in `question_text`, so the candidate and the future grading rubric can tell what a complete answer covers. Do not require a greeting unless it naturally belongs to the everyday situation.

## Audio-led picture task scripts

Parts 2-4 are spoken picture tasks, not silent image captions. The learner hears the Dutch task and sees the picture panel or panels at the same time. Write original `question_text` that is natural when read aloud by TTS: normally 12-26 simple words, delivered in about 7-14 seconds. The media generator inserts a one-second SSML pause between sentences for audio playback; do not include SSML tags in `question_text`.

- Start with one short factual setup sentence that names an ordinary person or immediate situation, for example a person at work, at school, on a journey, at home, or doing an everyday activity.
- Follow with one direct task sentence, or two very short task sentences. Use concrete A2 verbs such as `Vertel`, `Beschrijf`, `Leg uit`, `Vergelijk`, or `Zeg welke`.
- Let the picture evidence do the work. Do not invent dialogue, greetings, a long backstory, an answer the learner must repeat, or details that cannot be seen in the panel or panels.
- For Parts 3 and 4, every panel must be necessary to answer. A comparison must name a practical criterion; a sequence must have a clear before, during and after action.
- Keep the candidate's role practical and familiar: resident, customer, colleague, parent, traveller, patient, neighbour, student, or visitor. Use original names and details, never wording from an official exam.

## Approved scenario plan

The generator receives the selected exam's approved scenario plan from `config/mock_exam_speaking_scenarios.json`. Use all 16 plan entries exactly once and do not substitute, combine, omit, repeat, or invent another scenario. The plan controls the scenario, pattern, spoken script and required answer; this prompt controls the final artifact structure, Dutch level, media descriptions, rubrics and model answers.

## Randomize real task variations within each fixed format

The three official samples use the same four media layouts. Do not invent a fifth layout, a multiple-choice answer, a written answer, or a text-only Part 2-4 task. Instead, randomly distribute these genuine spoken-task variations inside the required format for each new exam. Do not use one variation more than twice in any part.

- **Part 1, video:** use only short personal-response tasks. The actor first shares a simple personal habit or preference, then asks one direct question about the learner's related routine, preference or frequency and finishes with a `Vertel...` sentence requesting the second detail. Use daily habits, hobbies, transport, food, work, health or free time. Do not use visual observation, advice, problem-solving, service requests or role-play in Part 1.
- **Part 2, one picture:** use short-response tasks: introduce one or two named visible people, then ask `Vertel wat over [naam/namen]. Noem drie dingen.` Use three clear visual details about people, actions, objects or the setting. Also use the event-and-next-action pattern: a named person has experienced a visible event or problem, then ask `Vertel wat er is gebeurd. Vertel ook wat [naam] nu kan doen.`
- **Part 3, two pictures:** use extended-response tasks: choose one picture and explain why; compare the two practical options using a named practical criterion; state which visible place/item/activity suits a named need and give a reason.
- **Part 4, three pictures:** use extended-response tasks: describe something shown in all three pictures; tell a simple before/during/after sequence; explain three steps of a daily task; say what someone can do with the objects or people in each picture; or respond to a practical situation with an action and a reason.

### Required pattern allocation for every exam

Use the supplied reference examples as the pattern for this allocation, while inventing original Dutch scenarios and preserving the required media layouts.

- **Part 1 - short video answers:** exactly four personal-routine or preference questions. Every clip has an actor's personal statement, a main question, and one final `Vertel...` follow-up. Each answer needs 1-2 clear A2 sentences that cover both requested details.
- **Part 2 - one-picture short answers:** introduce one or two named people in the picture and ask for exactly three visible details about them, their actions, objects or location. Each answer needs 1-2 clear A2 sentences.
- **Part 3 - two-picture extended choices:** show two practical alternatives and ask the learner to choose one and give a reason. Each answer needs 2-4 complete A2 sentences.
- **Part 4 - three-picture extended situations:** use a clear sequence, practical message, request, rescheduled appointment, refusal with reason, or simple advice. Require two explicit details. Each answer needs 2-4 complete A2 sentences.

Across the full exam, include original versions of these task archetypes. Match them to the required part and picture layout; do not copy any sample wording.

- **Visual observation:** ask where a visible person is, what the person is doing, what object they use, or what visible problem is occurring. Require one or two factual details from the image or video.
- **Personal routine or preference:** ask about a familiar activity such as travel, food, free time, news, work, or school. Require a simple choice or frequency and, at most, one reason or companion.
- **Practical message, request, or advice:** set an everyday problem such as illness, a changed appointment, an invitation, a workplace absence, or a friend needing help. Require two explicit details, for example the problem + next action, a refusal + reason, or two simple pieces of advice.
- **Choice with justification:** show two genuinely usable options in a `two_picture` passage, such as types of course, transport, housing, activity, or service. Require the learner to choose one and give one or two practical reasons based on the visible difference.

### Reference examples for script shape

Use these as reference for sentence length, clarity and required details. They are examples only: create new names, settings, wording and answers that follow the original scenario invention rules above. Do not reproduce them verbatim in a generated exam.

- **Short visual observation (Part 1 or Part 2):** Prompt: `Kijk naar de foto. Waar is de vrouw en wat doet zij?` Model answer: `De vrouw is in de supermarkt. Ze kiest fruit.`
- **One-picture named people (Part 2):** Prompt shape: `Dit zijn [naam] en [familierelatie]. Vertel wat over [naam] en [familierelatie]. Noem drie dingen.` Model answer: `Ze zitten samen in de tuin. De man leest een krant en het kind speelt met een bal.`
- **One-picture event and next action (Part 2):** Prompt shape: `[Naam] heeft [zichtbare gebeurtenis]. Vertel wat er is gebeurd. Vertel ook wat [naam] nu kan doen.` Model answer: `Nora heeft een kapot pakketje ontvangen. Ze kan de winkel bellen en het pakketje terugsturen.`
- **Short specific video cue (Part 1):** Video script: `Ik bezorg vandaag pakketten in deze straat. Welk pakket mist u precies?` Expected learner response: `Mijn pakket is niet gekomen. Het is voor nummer twaalf.`
- **Short personal routine - transport (Part 1 or Part 2):** Prompt shape: name a common way someone travels, then ask how the learner travels to work or school and why. Model answer: `Ik ga met de bus, want de halte is dichtbij.`
- **Short personal routine - free time (Part 1 or Part 2):** Prompt shape: ask what the learner most likes to do at the weekend, then ask who they do it with. Model answer: `In het weekend kook ik graag. Dat doe ik vaak met mijn broer.`
- **Short personal routine - frequency (Part 1 or Part 2):** Prompt shape: ask how often the learner does a familiar activity such as following news, exercising, calling family, or cooking, then ask why. Model answer: `Ik luister elke avond naar het nieuws, omdat ik wil weten wat er gebeurt.`
- **Extended practical message (Part 4):** Prompt: `U bent ziek en belt uw chef. Zeg dat u niet kunt werken en vertel wanneer u denkt terug te zijn.` Model answer: `Hallo, ik ben vandaag ziek en kan niet werken. Ik denk dat ik maandag terug ben.`
- **Extended advice (Part 4):** Prompt: `Uw vriend wil beter Nederlands leren. Geef twee eenvoudige tips.` Model answer: `Hij kan een cursus volgen. Ook kan hij elke dag Nederlands luisteren.`
- **Extended visible choice (Part 3):** Prompt: `U ziet twee woningen. Kies een woning en vertel waarom die woning beter bij u past.` Model answer: `Ik kies de woning in de stad. De winkels zijn dichtbij en ik hoef niet ver te reizen.`

## Functional visual material

Use pictures sparingly, as the supplied DUO writing papers do: a picture must show information that the candidate needs in order to answer, never act as decoration.

- Match the official four-part pattern exactly: Part 2 has **exactly 4** `one_picture` passages, Part 3 has **exactly 4** `two_picture` passages, and Part 4 has **exactly 4** `three_picture` passages. Do not use `passage_type: "text"` in Parts 2-4.
- For all 12 picture-based tasks, use clear everyday visual evidence: two broken/stolen items for a municipality or insurance report, three simple work tasks for a colleague, a bus-stop or shop choice, a short before/during/after sequence, or two practical options to compare. Generate only identifiable people and objects. Never include readable words, labels, signs, speech bubbles, or decorative stock scenes.
- Every visual task must be answerable from its pictures and Dutch instruction. Part 2 uses one picture to describe; Part 3 uses two equally important pictures for an explicit choice or comparison; Part 4 uses three equally important pictures that the learner must all describe.

## Media prompt format

`scene_description` is handed directly to a media creator. Make it a complete, copy-ready English prompt, not an internal note. It must specify the people, visible action, objects that matter to the task, setting, framing and style. Use: "Naturalistic educational assessment still, landscape 16:9, eye-level medium-wide shot, realistic daylight, clear uncluttered composition, no readable text, labels, logos, speech bubbles or watermarks." Append it to every image prompt.

For Part 1 videos, begin with: "Short naturalistic educational assessment video, 8-15 seconds, landscape 16:9, one continuous eye-level medium-wide shot..." Show exactly one adult speaker facing straight toward the camera and addressing the learner. Do not show any other people, including blurred, distant or background people. Include the complete `content_nl` spoken cue in quotation marks; its final question or request must make the learner's reply clear. Keep gestures and actions simple and ensure no visual wording is needed to understand the scene. Set `presenter_gender` to exactly `"female"` or `"male"` for each video passage, matching the visible adult who speaks. Use two female and two male presenters in every exam.

For `two_picture` and `three_picture` passages, write a complete independent prompt for each panel, separated only by ` | `. Keep the same main person, camera angle and realistic style across panels where a sequence is being told. Each panel must be understandable without text and must visually contrast the decision or action it represents.

## Rules

- Produce **exactly 16 questions**: 4 with `part_number: 1`, 4 with `part_number: 2`, 4 with `part_number: 3`, 4 with `part_number: 4`. All `question_type` = `"open_spoken"`.
- Every question needs a passage describing its prompt material:
  - Part 1: `passage_type: "video"`, with `content_nl` = the full one-speaker Dutch cue from the video (1-2 short sentences, roughly 16-32 words, approximately 8-15 seconds, ending with one direct question or request for the learner), `scene_description` (English) describing the everyday situation shown, and `presenter_gender`: `"female"` or `"male"`.
  - For a visual Part 2 task, use `passage_type: "one_picture"`, with `scene_description` (English) describing the single picture to generate.
  - For a visual Part 3 task, use `passage_type: "two_picture"`, with `scene_description` containing two distinct picture descriptions separated by " | ".
  - For a visual Part 4 task, use `passage_type: "three_picture"`, with `scene_description` containing three distinct picture descriptions separated by " | ".
- `question_text` gives the exact spoken instruction to the candidate, in Dutch. For Parts 2-4, use the DUO-like cadence: one short factual setup sentence followed by one or two direct A2 imperatives. Keep it concrete and answerable from the picture panels. Every Part 2 `question_text` must end with the separate final sentence `Gebruik het plaatje.` so it is included in the audio script. The learner app avoids displaying it twice.
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
      "content_nl": "Ik werk bij de apotheek. Hoe vaak wilt u dit medicijn innemen?",
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
