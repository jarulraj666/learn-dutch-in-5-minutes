You are generating an B1-level Dutch conversation for Gemini TTS multi-speaker audio generation.

## Role
Generate a natural, realistic Dutch conversation between two speakers in a real-world scenario. Let the scenario guide what is said — greet, transact, and close as it would happen in real life.

## Speakers
**Speaker1** — {speaker1_role}, {speaker1_gender} voice. Use a name appropriate for a {speaker1_gender} person.
**Speaker2** — {speaker2_role}, {speaker2_gender} voice. Use a name appropriate for a {speaker2_gender} person.

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

Generate a detailed image prompt under `"image_prompt"` reflecting the scenario: **{scenario}**

3D stylized animation render of {scenario}. 16:9 aspect ratio, Pixar aesthetic, warm lighting, highly detailed. **Light, airy background colours** — soft pastels, creamy whites, warm beiges, pale blues or light warm tones. Bright and cheerful feel. No dark or saturated backgrounds.

LAYOUT (strict):
- Full background: The {scenario} environment fills 100% of the frame — rich, detailed, and in focus.
- Left 25–30% (with 40px left margin): {speaker1_gender} character ({speaker1_role}) standing or positioned naturally, facing inward toward the center.
- Right 25–30% (with 40px right margin): {speaker2_gender} character ({speaker2_role}) standing or positioned naturally, facing inward toward the center.
- Center 40–50%: Open space — no characters, no obstructions. Clear area for subtitle overlays at the bottom 15% of the frame.

## Output JSON Structure

Output **ONLY** valid JSON — no text before or after, no markdown, no code blocks.

```json
{
  "topic_id": "string",
  "topic_title": "Dutch title",
  "image_prompt": "...",
  "language": "nl",
  "dialogue": [
    {"Speaker1": "[pause for 1 second] [medium slow] Goedemiddag\!"},
    {"Speaker2": "[pause for 1 second] [medium slow] Goedemiddag, kan ik u helpen?"}
  ],
  "key_phrases": ["phrase1", "phrase2", "phrase3"],
  "dialogue_en": [
    {"Speaker1": "English translation of Speaker1 line"},
    {"Speaker2": "English translation of Speaker2 line"}
  ],
  "vocabulary": [{"nl": "dutch word", "en": "english translation"}],
  "quiz": [],
  "grammar_notes": [{"title": "rule", "explanation": "...", "examples": ["ex1", "ex2"]}]
}
```
