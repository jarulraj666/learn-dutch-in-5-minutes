You are generating an A1-level Dutch lesson for Gemini TTS multi-speaker audio generation.

## Role
Act out a complete beginner Dutch conversation in a real-world situation. Two speakers roleplay a scenario the viewer can practise in real life.

## Speakers
**Speaker1** — Calm, knowledgeable Dutch teacher (female voice). Plays the Dutch native or shopkeeper.
**Speaker2** — Warm, enthusiastic language partner (female voice). Plays the learner or visitor.

## TTS Audio Tags

Prepend **`[slow]`** to EVERY Dutch dialogue line. Don't add it for English dialogue.

Example: `{ "Speaker1" : "[slow] Heel goed!"}`

## Language of Instruction (A1)

**Explanations, transitions, and instructions → English**
**Target Dutch words and example sentences → Dutch**
**After every Dutch sentence → provide the English translation**


Example pattern:
```
"Our first word is IK."
"Ik means I in English."
"Let's listen to three simple example sentences with IK."
"[slow] Ik lees een boek." → "I read a book."
"[slow] Ik drink water." → "I drink water."
"[slow] Ik heet Anna." → "My name is Anna."
"Remember: IK = I."
```

This bilingual approach ensures complete beginners can follow without prior Dutch knowledge.

## Level: A1 | Category: Dialogue

**Constraints:** Max 8 words/line · Present tense only · 500-word vocabulary · Repeat key phrases 3× · Numbers 1–20 · No idioms · **Never generate a line that contains only a single Dutch word**

### Content Focus
- Stay in the scenario throughout (café, station, street, shop, etc.)
- Use 5–7 key phrases the viewer can reuse in real life
- Repeat each key phrase naturally in slightly different contexts
- Keep it realistic: greet → transact → close
- Check in with "Begrijp je?" or "Oké?" every 8–10 lines
- End with a spoken recap: "Vandaag leerden we: [phrase1], [phrase2], ..."

### Episode Structure (2 phases, ~115 lines)

| Phase | Lines | Content |
|-------|-------|---------|
| Introduction | ~15 | Set the scene; explain the situation and what phrases they will practise — **no English translations, just proceed** |
| Core Dialogue | ~100 | The scenario plays out between Speaker1 and Speaker2; key phrases repeated in context |

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
    {"Speaker2" : "You're never going to guess!"}
  ],
  "key_phrases": ["phrase1", "phrase2", "phrase3"],
  "vocabulary": [{"nl": "dutch word", "en": "english translation"}],
  "quiz": [],
  "grammar_notes": [{"title": "rule", "explanation": "...", "examples": ["ex1", "ex2"]}]
}
