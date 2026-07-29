Create one rich image-generation prompt result for a Dutch A1 learning video background.

Output format:
- Generate one high-quality PNG image.
- Do not return markdown or explanatory text.
- The model should save the generated image file to disk.

Canvas requirements:
- width={{WIDTH}}
- height={{HEIGHT}}
- 16:9 composition matching the same aspect ratio.

Topic context:
- topic id: {{TOPIC_ID}}
- topic title: {{TOPIC_TITLE}}

Visual direction:
- Cartoon + paint style.
- Rich and layered look with soft gradients and visual depth.
- Keep overall image bright and clean.
- Include one environment/location cue tied to the topic.
- Build the full background from this scene brief: {{BACKGROUND_BRIEF}}.
- Keep center lower-third area clear for subtitles.

Dutch authenticity — signs and text in scene:
- All visible signs, labels, menus, boards and notices must be written in Dutch.
- Use {{DUTCH_SIGNS}} as the primary text elements visible in the scene.
- Signs should look cleanly printed in a flat cartoon style consistent with the scene.
- Signs must be legible but not overly large — part of the background, not center stage.
- Street signs should use blue rectangles with white text, matching Dutch road sign conventions.
- Interior signs (menus, price tags, departure boards) should match the scene's setting style.
- Do not use English text anywhere in the image.
- Do NOT include any episode title, lesson title, topic title, or heading text anywhere in the image.
- Do NOT add any overlay text, captions, or labels derived from the topic context.

Mandatory characters:
- Include exactly two visible cartoon human figures in the scene.
- One should read as male and one should read as female.
- Both should appear in a conversation posture facing each other.
- Keep both humans fully visible and not blocked by foreground props.

Safety and compatibility:
- No script tags.
- No external assets or remote image links.
- No CSS imports.
