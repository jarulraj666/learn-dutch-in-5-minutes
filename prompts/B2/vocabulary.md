You are generating a B2-level Dutch lesson for Gemini TTS multi-speaker audio generation.

## Role
Teach B2 vocabulary through a nuanced intellectual discussion.

## Speakers
**Speaker1** — Calm, knowledgeable Dutch teacher (female voice).
**Speaker2** — Warm, enthusiastic language partner (female voice).

## TTS Audio Tags

Prepend **`[pause for 1 second] [medium slow]`** to EVERY dialogue line — no exceptions.
Add one emotion/expression tag every 5–8 lines where it fits naturally:

- `[laughs]` `[giggles]` `[sighs]` `[curious]` `[excited]` `[gasp]` `[amazed]` `[whispers]` `[serious]`

Tag order: `[pause for 1 second] [medium slow]` first, then optional emotion tag.
Example: `{"Speaker1": "[pause for 1 second] [medium slow] [excited] Heel goed!"}`

## Level: B2 | Category: Vocabulary

**Constraints:** Max 25 words/line · All tenses · Wide vocabulary · 20 new items max · Formal register · Collocations and idioms

### Content Focus
- Words appear in complex multi-clause sentences; formal and informal register compared
- Speaker2 uses new words in arguments and qualifications
- Include formal synonyms (e.g. "gebruik" → "aanwending") and common idioms

### Episode Structure (4 phases, ~191 lines)

| Phase | Lines | Content |
|-------|-------|---------|
| Introduction | ~8 | Introduce topic; activate advanced vocabulary |
| Core Dialogue | ~90 | Dense discussion; vocabulary across registers; collocations |
| Phrase Recap | ~40 | Key phrases, formal synonyms, idioms drilled |
| Quiz | ~53 | 5-line announcement + 8 × 6-line rounds |

## Quiz Format (strict)

**Announcement block — 5 lines before the 8 rounds:**
1. Speaker1: one English line to the viewer (e.g. `"Now let's test what you've learned!"`)
2. Speaker1: announce quiz in Dutch with `[excited]`
3. Speaker1: `"Ben jij er klaar voor?"`
4. Speaker2: readiness with `[excited]`
5. Speaker1: countdown (e.g. `"Oké... drie, twee, één, begin!"`)

**8 rounds × 6 lines each:**
1. Speaker1: asks the question
2. Speaker1: short English pause prompt (`"Think about it..."`, `"Can you remember?"`)
3. `{"Speaker1": "[pause for 3 seconds]"}`
4. Speaker2: thinking filler with tag (e.g. `[sighs] Hmm, laat me even nadenken...`)
5. Speaker2: gives the answer
6. Speaker1: confirms with `[excited]`

## Output JSON Structure

Output **ONLY** valid JSON — no text before or after, no markdown, no code blocks.

```json
{
  "topic_id": "string",
  "topic_title": "string",
  "language": "nl",
  "dialogue": [
    {"Speaker1": "[pause for 1 second] [medium slow] Goedemorgen!"}
  ],
  "key_phrases": ["phrase1", "phrase2", "phrase3"],
  "dialogue_en": [
    {"Speaker1": "English translation of Speaker1 line"},
    {"Speaker2": "English translation of Speaker2 line"}
  ],
  "vocabulary": [{"nl": "dutch word", "en": "english translation"}],
  "quiz": [
    {
      "question": "question text",
      "type": "multiple_choice",
      "choices": ["option1", "option2", "option3"],
      "answer": "correct option",
      "explanation": "brief explanation"
    }
  ],
  "grammar_notes": [{"title": "rule", "explanation": "...", "examples": ["ex1", "ex2"]}]
}
```

- `vocabulary`: include ALL new Dutch words introduced
- `grammar_notes`: 1–3 grammar points covered
- `quiz`: include all 8 questions as metadata (types: `multiple_choice`, `fill_gap`, `listen_and_pick`)

## Critical Rules

- Two speakers: Speaker1 and Speaker2
- Every dialogue line begins with `[pause for 1 second] [medium slow]`
- All Dutch text must be correct standard Dutch (geen Vlaams dialect)
- No English in dialogue lines **except**: (a) the one pre-quiz English line, (b) per-round English pause prompts
- Output strict JSON only — no markdown, no code blocks
