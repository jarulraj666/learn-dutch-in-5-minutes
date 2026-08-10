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

## Scenario
The conversation takes place in: **{scenario}**

## TTS Notes

Write clean dialogue lines without inline speech tags. Do not add bracketed markers such as `[slow]`, `[pause for 1 second]`, or expression tags.

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
  "dialogue_en": [
    // Plain English only — no TTS tags, no [slow], no [pause for 1 second]
    {"Speaker1": "English translation of Speaker1 line"},
    {"Speaker2": "English translation of Speaker2 line"}
  ],
  "vocabulary": [{"nl": "dutch word", "en": "english translation"}],
  "grammar_notes": [{"title": "rule", "explanation": "...", "examples": ["ex1", "ex2"]}]
}
```