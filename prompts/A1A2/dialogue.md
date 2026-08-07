You are generating an A1-A2 level Dutch conversation for Gemini TTS multi-speaker audio generation.

## Role
Generate a natural, realistic Dutch conversation between two speakers in a real-world scenario. The conversation should flow naturally as it would in real life — let the scenario dictate the content, pacing, and length.

## Conversation Rules

**This must be a real conversation — not a lesson.**

- **No recap or summary sections.** Do NOT add a "let's repeat everything", "let's review", "let's go over what we learned", or any similar wrap-up block at the end. Real conversations don't end with a quiz.
- **No repetition of earlier lines.** Each turn must say something new. Do not echo or re-ask questions that were already answered earlier in the conversation.
- **No scripted drills.** Do not have one speaker fire a list of questions that the other answers one by one.
- **Natural progression only.** The conversation should start, develop organically, and end as it would in real life — with a goodbye or a natural closing, not a summary.
- **Single location only.** The entire conversation must take place in the same physical location defined by the scenario. Do not move the speakers to a different place mid-conversation. The dialogue must start, develop, and end in the same spot.

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

Generate a detailed image prompt under `"image_prompt"` reflecting the scenario of the dialogue**

3D stylized animation render of {scenario} - {title_hint}. 16:9 aspect ratio, Pixar aesthetic, warm lighting, highly detailed. **Light, airy background colours** — soft pastels, creamy whites, warm beiges, pale blues or light warm tones. Bright and cheerful feel. No dark or saturated backgrounds. Check the dialogue and fit the environment based on the dialogue.

LAYOUT (strict):
- Full background: The {scenario} - {title_hint} environment fills 100% of the frame — rich, detailed, and in focus.
- Left 35–40% : {speaker1_gender} character ({speaker1_role}) positioned naturally, facing inward toward the center.
- Right 35–40% : {speaker2_gender} character ({speaker2_role}) positioned naturally, facing inward toward the center.
- Center 20%: Open space — no characters, no obstructions.

## Output JSON Structure

Output **ONLY** valid JSON — no text before or after, no markdown, no code blocks.

```json
{
  "topic_id": "string",
  "topic_title": "Dutch title",
  "topic_title_en": "English title used for YouTube metadata",
  "image_prompt": "3D stylized animation render of {scenario} - {title_hint}. 16:9 aspect ratio, Pixar aesthetic, warm lighting, highly detailed. Light, airy background colours — soft pastels, creamy whites, warm beiges, pale blues or light warm tones. Bright and cheerful feel. No dark or saturated backgrounds. Full background: the {scenario} environment fills 100% of the frame — rich, detailed, and in focus. Left 35-40%: {speaker1_gender} character ({speaker1_role}) positioned naturally, facing inward toward the center. Right 35-40%: {speaker2_gender} character ({speaker2_role}) positioned naturally, facing inward toward the center. Center 20%: open space — no characters, no obstructions.",
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