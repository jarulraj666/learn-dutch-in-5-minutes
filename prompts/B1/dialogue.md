You are generating an B1-level Dutch conversation for Gemini TTS multi-speaker audio generation.

## Role
Generate a natural, realistic Dutch conversation between two speakers in a real-world scenario. Let the scenario guide what is said — greet, transact, and close as it would happen in real life.

## Conversation Rules

**This must be a real conversation — not a lesson.**

- **No recap or summary sections.** Do NOT add a "let's repeat everything", "let's review", "let's go over what we learned", or any similar wrap-up block at the end. Real conversations don't end with a quiz.
- **No repetition of earlier lines.** Each turn must say something new. Do not echo or re-ask questions that were already answered earlier in the conversation.
- **No scripted drills.** Do not have one speaker fire a list of questions that the other answers one by one. That is a classroom drill, not a conversation.
- **Natural progression only.** The conversation should start, develop organically, and end as it would in real life — with a goodbye or a natural closing, not a summary.

## Speakers
**Speaker1** — {speaker1_role}, {speaker1_gender} voice. Use a name appropriate for a {speaker1_gender} person.
**Speaker2** — {speaker2_role}, {speaker2_gender} voice. Use a name appropriate for a {speaker2_gender} person.

**CRITICAL — speaker assignment rules:**
- Every single dialogue line must be attributed to the correct speaker based on their role.
- Speaker1 is always the {speaker1_role}. Speaker2 is always the {speaker2_role}.
- Never swap speakers mid-conversation. If Speaker2 is the customer, only the customer's lines are labeled Speaker2 — even when the topic shifts (e.g., asking for a map, asking about restaurants, asking about checkout). All customer questions stay as Speaker2. All staff/host answers stay as Speaker1.
- Before outputting, verify: does the speaker label match who would logically say this line given their role? If not, correct it.

## Scenario
The conversation takes place in: **{scenario}**

## TTS Audio Tags

Prepend **`[pause for 1 second] [medium slow]`** to EVERY dialogue line — no exceptions.

Add **expression tags** naturally where they fit the scenario and moment. Choose based on what the character would actually feel:

| Tag | Use when... |
|-----|-------------|
| `[laughs]` | Something is genuinely funny or light |
| `[giggles]` | Playful, slightly awkward, or cute moment |
| `[sighs]` | Mild frustration, relief, or tiredness |
| `[curious]` | Asking a question or discovering something |
| `[excited]` | Good news, enthusiasm, surprise |
| `[gasp]` | Sudden surprise or shock |
| `[amazed]` | Impressed or in awe |
| `[whispers]` | Saying something quietly or secretly |
| `[serious]` | Important instruction or correction |

Tag order: pacing tag first, then expression tag.
Example: `{"Speaker1": "[pause for 1 second] [medium slow] [excited] Dat is geweldig!"}` · `{"Speaker2": "[pause for 1 second] [medium slow] [curious] Wat betekent dat?"}`

Don't force tags on every line — use them where the scenario makes them natural.

## Language

All dialogue must be in Dutch. No English in any dialogue line.

Use natural, conversational Dutch. Everyday vocabulary — no academic or formal language. Opinions and reactions should sound like what a real person would say, not a textbook. Varied tenses where natural.

Aim for approximately **150 dialogue turns** total.

## Image Prompt

Generate a single-sentence `image_prompt` field in the JSON that describes the specific scene: the exact environment, what makes it visually distinct, and any notable props or details from this particular dialogue. Do not include character layout or style instructions — those are handled separately.

## Output JSON Structure

Output **ONLY** valid JSON — no text before or after, no markdown, no code blocks.

```json
{
  "topic_id": "string",
  "topic_title": "Dutch title",
  "image_prompt": "A restaurant with a warm-lit interior, wooden tables, a chalkboard menu on the wall, and wine glasses on the counter.",
  "language": "nl",
  "dialogue": [
    {"Speaker1": "[pause for 1 second] [medium slow] Goedemiddag\!"},
    {"Speaker2": "[pause for 1 second] [medium slow] Goedemiddag, kan ik u helpen?"}
  ],
  "key_phrases": ["phrase1", "phrase2", "phrase3"],
  "vocabulary": [{"nl": "dutch word", "en": "english translation"}],
  "quiz": [],
  "grammar_notes": [{"title": "rule", "explanation": "...", "examples": ["ex1", "ex2"]}]
}
```
