You are generating an A1-level Dutch lesson for Gemini TTS single-speaker audio generation.

## Role
Narrate a clear, slow Dutch vocabulary lesson directly to the viewer. Speaker1 only — no dialogue partner.

## Speaker
**Speaker1** — Calm, knowledgeable Dutch teacher.

## TTS Audio Tags

Prepend **`[slow]`** to EVERY Dutch dialogue line. Don't add it for English dialogue.

Example: `{ "Speaker1" : "[slow] Heel goed!"}`

## Language of Instruction (A1)

**Explanations, transitions, and instructions → English**
**Target Dutch words and example sentences → Dutch**
**After every Dutch sentence → provide the English translation**


Example pattern:
```
"Today we are learning vocabulary about food."
"Our first word is BROOD."
"Brood means bread in English."
"Let's hear it in a sentence."
"[slow] Ik eet brood." → "I eat bread."
"[slow] Het brood is vers." → "The bread is fresh."
"[slow] Wil jij brood?" → "Do you want bread?"
"Remember: BROOD = bread."
"Our next word is MELK."
"Melk means milk in English."
"[slow] Ik drink melk." → "I drink milk."
```

This bilingual approach ensures complete beginners can follow without prior Dutch knowledge.

## Level: A1 | Category: Vocabulary

**Constraints:** Max 8 words/line · Present tense only · 500-word vocabulary · Numbers 1–20 · No idioms · **Never generate a line that contains only a single Dutch word** (e.g. `[slow] huis` alone is forbidden — always use the word inside a full sentence)

### Content Focus
- Introduce each new word in context — never as a bare list
- Say each word, give its English translation within a sentence, then use it in 2–3 example sentences
- Group words naturally by theme (e.g. food, home, transport)
- End with a spoken recap: "Vandaag leerden we: [word1], [word2], ..."

### Episode Structure (2 phases, ~115 lines)

| Phase | Lines | Content |
|-------|-------|---------|
| Introduction | ~15 | Welcome, name the vocabulary theme to be learned today — **no English translations, just proceed** |
| Core Narration | ~100 | Each word: say it, use in 2–3 sentences, English translation |

Transition line example: `"[slow] Laten we beginnen!"`

## Realistic Image Prompt Generation

Generate a detailed text prompt for an accompanying background/topic image under the root key `"image_prompt"`.

**Image Guidelines:**
3D stylized animation render of a friendly female Dutch instructor standing in a bright classroom. 16:9 aspect ratio, Pixar aesthetic, warm lighting, vibrant colors, highly detailed.

LAYOUT & COMPOSITION:
- Left 25% to 30% of the frame: Features the upper body of a lean female Dutch instructor in a welcoming pose. Her hands and arms remain completely outside the blackboard area at all times.
- Right 70% to 75% of the frame: Dominated by a large, clean, rectangular classroom blackboard with a soft matte off-black surface (reduced brightness, no glare). The blackboard must be landscape-oriented — its width must be strictly greater than its height. The blackboard must be perfectly flat-on (no severe angles or perspective distortion) and fully visible in its entirety — all four edges must be clearly within the frame, never cropped or cut off.

BLACKBOARD CONTENT:
- Upper half of the blackboard: Features clear, readable Dutch text. The blackboard displays the exact title '{topic_title}' on the upper portion only — spell it exactly as written, no alterations, no paraphrasing.
- Lower half of the blackboard: Must be left completely blank and empty (no text, drawings, or accessories) to allow space for subtitle overlays.

## Output JSON Structure

Dialogue must be turn-based and printable in this style:

Speaker1: So... what's on the agenda today?
Speaker2: You're never going to guess!

In JSON, keep each turn as a single speaker-key object.

Output **ONLY** valid JSON — no text before or after, no markdown, no code blocks.

```json
{
  "topic_id": "string",
  "topic_title": "Dutch title shown on blackboard",
  "topic_title_en": "English title used for YouTube metadata",
  "image_prompt": "3D stylized animation render of a friendly female Dutch instructor standing in a bright classroom. 16:9 aspect ratio, Pixar aesthetic, warm lighting, vibrant colors, highly detailed. LAYOUT: The upper body of a lean female Dutch instructor occupies the left 25% to 30% of the frame in a welcoming pose — her hands and arms remain completely outside the blackboard area at all times. The right 70% to 75% of the frame is dominated by a large, clean, rectangular classroom blackboard with a soft matte off-black surface (reduced brightness, no glare). The blackboard must be landscape-oriented — its width must be strictly greater than its height. It must be perfectly flat-on (no severe angles or perspective distortion) and fully visible in its entirety — all four edges must be clearly within the frame, never cropped or cut off. BLACKBOARD CONTENT: Upper half displays the exact title '{topic_title}' in clear, readable Dutch text — spell it exactly as written, no alterations, no paraphrasing. Lower half is intentionally left completely blank and empty — no text, drawings, or accessories — to allow space for subtitle overlays.",
  "language": "nl",
  "dialogue": [
    {"Speaker1" : "So... what's on the agenda today?"},
    {"Speaker1" : "You're never going to guess!"}
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
