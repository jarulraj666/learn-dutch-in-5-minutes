from __future__ import annotations

from typing import Any

from pipeline import settings


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


def generate_description(script: dict[str, Any]) -> str:
    template = (settings.ROOT / "templates/youtube_description.md").read_text(encoding="utf-8")

    grammar, pattern, examples = _flatten_grammar_notes(script.get("grammar_notes", []))
    quiz_answers = _quiz_answers_block(script.get("quiz", []))

    return template.format(
        grammar_notes=grammar,
        pattern_breakdown=pattern,
        mini_examples=examples,
        quiz_answers=quiz_answers,
    )


def generate_title(script: dict[str, Any]) -> str:
    topic_title = script.get("topic_title", "Dutch Lesson")
    return f"Dutch A1 Conversation: {topic_title}"


def generate_metadata(script: dict[str, Any], playlist_track: str) -> dict[str, Any]:
    title = generate_title(script)
    description = generate_description(script)

    return {
        "title": title,
        "description": description,
        "tags": ["Dutch", "A1", "Conversation", "Learn Dutch", playlist_track],
        "chapters": [
            {"time": "00:00", "label": "Conversation"},
            {"time": "02:30", "label": "Vocabulary Recap"},
            {"time": "03:20", "label": "Quiz"},
        ],
    }
