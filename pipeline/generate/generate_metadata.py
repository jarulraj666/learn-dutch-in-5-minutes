from __future__ import annotations

from typing import Any

from pipeline import settings

_LEVEL_DISPLAY: dict[str, str] = {
    "A1A2": "A1-A2",
}


def _level_label(level: str) -> str:
    """Return the human-readable display label for a CEFR level slug."""
    return _LEVEL_DISPLAY.get(level, level)


_CATEGORY_LABELS: dict[str, str] = {
    "common_words": "Common Words",
    "grammar": "Grammar",
    "vocabulary": "Vocabulary",
    "dialogue": "Dialogue",
    "introductions": "Introductions",
    "shopping": "Shopping",
    "transport": "Transport",
    "food": "Food and Café",
    "daily_life": "Daily Life",
}


def _category_label(category: str) -> str:
    return _CATEGORY_LABELS.get(category, category.replace("_", " ").title())


def _quiz_answers_block(quiz: list[dict[str, Any]]) -> str:
    lines = []
    for idx, q in enumerate(quiz, start=1):
        lines.append(f"{idx}. {q.get('answer', '')}")
    return "\n".join(lines)


def _flatten_grammar_notes(notes: list[dict[str, Any]]) -> tuple[str, str, str]:
    grammar_lines = []
    pattern_lines = []
    mini_examples = []

    for n in notes:
        grammar_lines.append(f"{n.get('title', '')}: {n.get('explanation', '')}")
        examples = n.get("examples", [])
        if examples:
            pattern_lines.append(examples[0])
            mini_examples.extend(examples[:2])

    return (
        "\n- ".join(grammar_lines),
        "\n- ".join(pattern_lines),
        "\n- ".join(mini_examples),
    )


def _format_key_phrases(phrases: list[str]) -> str:
    return "\n".join(f"• {p}" for p in phrases) if phrases else ""


def _format_vocabulary(vocab: list[dict[str, str]]) -> str:
    return "\n".join(f"• {v.get('nl', '')} — {v.get('en', '')}" for v in vocab) if vocab else ""


def generate_description(script: dict[str, Any], level: str = "A1A2", category: str = "") -> str:
    template = (settings.ROOT / "templates/youtube_description.md").read_text(encoding="utf-8")

    grammar, pattern, examples = _flatten_grammar_notes(script.get("grammar_notes", []))
    quiz_answers = _quiz_answers_block(script.get("quiz", []))
    key_phrases = _format_key_phrases(script.get("key_phrases", []))
    vocabulary_list = _format_vocabulary(script.get("vocabulary", []))
    topic_title = script.get("topic_title", "Dutch Lesson")
    cat_label = _category_label(category) if category else ""

    # Escape any stray braces in dynamic content so str.format() doesn't choke
    def _safe(text: str) -> str:
        return text.replace("{", "{{").replace("}", "}}")

    description = template.format(
        topic_title=_safe(topic_title),
        level=_level_label(level),
        category_label=_safe(cat_label),
        key_phrases=_safe(key_phrases),
        vocabulary_list=_safe(vocabulary_list),
        grammar_notes=_safe(grammar),
        pattern_breakdown=_safe(pattern),
        mini_examples=_safe(examples),
        quiz_answers=_safe(quiz_answers),
    )

    # YouTube description limit is 5000 characters
    return description[:5000]


def generate_title(script: dict[str, Any], level: str = "A1A2", category: str = "") -> str:
    topic_title_en = script.get("topic_title_en") or script.get("topic_title", "Dutch Lesson")
    cat_label = _category_label(category) if category else "Dutch Lesson"
    return f"{topic_title_en} - {cat_label} | Dutch in 5 minutes | {_level_label(level)} Beginners"


def generate_metadata(
    script: dict[str, Any],
    playlist_track: str,
    level: str = "A1A2",
    category: str = "",
) -> dict[str, Any]:
    title = generate_title(script, level=level, category=category)
    description = generate_description(script, level=level, category=category)
    cat_label = _category_label(category) if category else playlist_track
    topic_title_en = script.get("topic_title_en") or script.get("topic_title", "")

    tags = [
        "Learn Dutch",
        "Dutch",
        level,
        cat_label,
        topic_title_en,
        "Dutch for beginners",
        "Nederlandse les",
        "Dutch language",
        f"Dutch {level}",
    ]
    # Remove empty strings
    tags = [t for t in tags if t]

    return {
        "title": title,
        "description": description,
        "tags": tags,
        "chapters": [
            {"time": "00:00", "label": "Introduction"},
            {"time": "01:00", "label": "Lesson"},
            {"time": "04:30", "label": "Vocabulary Recap"},
        ],
    }
