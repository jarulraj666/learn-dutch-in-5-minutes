You are generating an A1-A2 level Dutch conversation for Gemini TTS multi-speaker audio generation.

## Role
Generate a natural, realistic Dutch conversation between two speakers in a real-world scenario. The conversation should flow naturally as it would in real life — let the scenario dictate the content, pacing, and length.

## Conversation Rules

**This must be a real conversation — not a lesson.**

- **No recap or summary sections.** Do NOT add a "let's repeat everything", "let's review", "let's go over what we learned", or any similar wrap-up block at the end. Real conversations don't end with a quiz.
- **No repetition of earlier lines.** Each turn must say something new. Do not echo or re-ask questions that were already answered earlier in the conversation.
- **No scripted drills.** Do not have one speaker fire a list of questions that the other answers one by one.
- **Natural progression only.** The conversation should start, develop organically, and end as it would in real life — with a goodbye or a natural closing, not a summary.
- **Location flexibility.** The conversation can move between different locations within the scenario as it naturally unfolds (e.g., from street to shop, or inside a building). Follow what feels natural for the dialogue.

## Speakers
**Speaker1** — {speaker1_role}, {speaker1_gender} voice. Use a name appropriate for a {speaker1_gender} person.
**Speaker2** — {speaker2_role}, {speaker2_gender} voice. Use a name appropriate for a {speaker2_gender} person.

**CRITICAL — speaker assignment rules:**
- Every single dialogue line must be attributed to the correct speaker based on their role.
- Speaker1 is always the {speaker1_role}. Speaker2 is always the {speaker2_role}.
- Never swap speakers mid-conversation. If Speaker2 is the customer, only the customer's lines are labeled Speaker2 — even when the topic shifts (e.g., asking for a map, asking about restaurants, asking about checkout). All customer questions stay as Speaker2. All staff/host answers stay as Speaker1.
- Before outputting, verify: does the speaker label match who would logically say this line given their role? If not, correct it.

**Common mistake to avoid — role swap mid-conversation:**
If Speaker1={speaker1_role} and Speaker2={speaker2_role}, this is WRONG:
```
{"Speaker2": "Wilt u een bon?"}   ← vendor question labeled as customer — WRONG
{"Speaker1": "Nee, dat hoeft niet."}  ← customer answer labeled as vendor — WRONG
{"Speaker2": "Prima. Hier is uw tas."}  ← vendor line labeled as customer — WRONG
```
This is CORRECT:
```
{"Speaker1": "Wilt u een bon?"}   ← vendor asks → Speaker1 ✓
{"Speaker2": "Nee, dat hoeft niet."}  ← customer answers → Speaker2 ✓
{"Speaker1": "Prima. Hier is uw tas."}  ← vendor closes → Speaker1 ✓
```
The golden rule: ask yourself "who would say this in real life given their role?" before assigning the label.

## Scenario
The conversation takes place in: **{scenario}**

## TTS Notes

Produce a raw script only.

Rules:
- Do not include any expressive, pace, pause, emotion, or stage-direction tags.
- Do not include bracketed instructions such as `[pause for 1 second]`, `[laughs]`, or similar.
- Output spoken Dutch lines only in each dialogue turn.

## Language

All dialogue must be in Dutch. No English in any dialogue line.

Use simple, everyday words that people actually say in real life. No complex vocabulary, no formal or literary language. Short sentences. Present tense. Words a beginner would hear on the street, in a shop, or at home.

Aim for approximately **120–140 dialogue turns** total.

## Image Prompt

Generate a single-sentence `image_prompt` field in the JSON that describes the specific scene: the exact environment, what makes it visually distinct, and any notable props or details from this particular dialogue. Do not include character layout or style instructions — those are handled separately.

## Output JSON Structure

Output **ONLY** valid JSON — no text before or after, no markdown, no code blocks.

```json
{
  "topic_id": "string",
  "topic_title": "Dutch title",
  "topic_title_en": "English title used for YouTube metadata",
  "image_prompt": "A busy supermarket aisle with colourful product shelves, a checkout counter visible in the background, and a shopping trolley nearby.",
  "language": "nl",
  "dialogue": [
    {"Speaker1": "Goedemiddag!"},
    {"Speaker2": "Goedemiddag, kan ik u helpen?"}
  ],
  "key_phrases": ["phrase1", "phrase2", "phrase3"],
  "vocabulary": [{"nl": "dutch word", "en": "english translation"}],
  "grammar_notes": [{"title": "rule", "explanation": "...", "examples": ["ex1", "ex2"]}]
}
```