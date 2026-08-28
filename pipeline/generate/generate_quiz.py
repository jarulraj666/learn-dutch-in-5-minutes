"""Generate a multiple-choice quiz for an episode script.

Dialogue episodes historically shipped without a quiz; grammar/vocabulary ones
shipped quizzes without stable ids or explanations. This module produces the
enriched shape the learner app needs: {id, question, options, answer,
explanation, difficulty, skill}.
"""
from __future__ import annotations

import logging
import re
from typing import Any

from pipeline import settings
from pipeline.utils import iter_dialogue_turns

LOGGER = logging.getLogger(__name__)

DEFAULT_QUESTION_COUNT = 5
OPTIONS_PER_QUESTION = 4
_VALID_DIFFICULTY = {"easy", "medium", "hard"}
_VALID_SKILL = {"comprehension", "vocabulary", "grammar"}
_MAX_TRANSCRIPT_CHARS = 12000

# TTS control tags that must never leak into a quiz question.
_TTS_TAG_RE = re.compile(
    r"\[(?:slow|fast|normal|whisper|excited|pause[^\]]*)\]", re.IGNORECASE
)


def _clean(text: str) -> str:
    return " ".join(_TTS_TAG_RE.sub(" ", text or "").split())


def _prompt_path(level: str):
    override = settings.ROOT / f"prompts/{level}/quiz.md"
    return override if override.exists() else settings.ROOT / "prompts/quiz.md"


def _format_transcript(script: dict[str, Any]) -> str:
    turns = iter_dialogue_turns(script.get("dialogue", []))
    en_turns = iter_dialogue_turns(script.get("dialogue_en", []))
    en_by_index = {i: line for i, (_, line) in enumerate(en_turns)}

    lines = []
    for idx, (speaker, line) in enumerate(turns):
        nl = _clean(line)
        if not nl:
            continue
        en = _clean(en_by_index.get(idx, ""))
        lines.append(f"{speaker}: {nl}" + (f"  ({en})" if en else ""))

    transcript = "\n".join(lines) or _clean(script.get("script_text", ""))
    return transcript[:_MAX_TRANSCRIPT_CHARS]


def _format_vocabulary(vocab: list[dict[str, str]]) -> str:
    return "\n".join(f"- {v.get('nl', '')} = {v.get('en', '')}" for v in vocab) or "(none)"


def _format_key_phrases(phrases: list[str]) -> str:
    return "\n".join(f"- {_clean(p)}" for p in phrases) or "(none)"


def _format_grammar_notes(notes: list[dict[str, Any]]) -> str:
    if not notes:
        return "(none)"
    blocks = []
    for n in notes:
        examples = "\n".join(f"  * {_clean(e)}" for e in n.get("examples", []))
        blocks.append(f"- {n.get('title', '')}: {n.get('explanation', '')}\n{examples}".rstrip())
    return "\n".join(blocks)


def _build_prompt(script: dict[str, Any], level: str, category: str, question_count: int) -> str:
    template = _prompt_path(level).read_text(encoding="utf-8")
    return (
        template.replace("{level}", level)
        .replace("{question_count}", str(question_count))
        .replace("{topic_title}", script.get("topic_title", ""))
        .replace("{category}", category)
        .replace("{transcript}", _format_transcript(script))
        .replace("{key_phrases}", _format_key_phrases(script.get("key_phrases", [])))
        .replace("{vocabulary}", _format_vocabulary(script.get("vocabulary", [])))
        .replace("{grammar_notes}", _format_grammar_notes(script.get("grammar_notes", [])))
    )


def _normalize_item(raw: Any, topic_id: str, index: int) -> dict[str, Any] | None:
    """Coerce one model-produced question into the canonical shape, or drop it."""
    if not isinstance(raw, dict):
        return None

    question = str(raw.get("question", "")).strip()
    answer = str(raw.get("answer", "")).strip()
    # Older artifacts and some model outputs use "choices" instead of "options".
    options_raw = raw.get("options") or raw.get("choices") or []
    if not isinstance(options_raw, list):
        return None

    options: list[str] = []
    for opt in options_raw:
        text = str(opt).strip()
        if text and text not in options:
            options.append(text)

    if not question or not answer or len(options) < 2:
        return None
    if answer not in options:
        LOGGER.warning("quiz: dropping question with answer not in options: %s", question[:60])
        return None

    difficulty = str(raw.get("difficulty", "")).strip().lower()
    skill = str(raw.get("skill", "")).strip().lower()

    return {
        "id": f"{topic_id}-q{index}",
        "question": question,
        "options": options,
        "answer": answer,
        "explanation": str(raw.get("explanation", "")).strip(),
        "difficulty": difficulty if difficulty in _VALID_DIFFICULTY else "medium",
        "skill": skill if skill in _VALID_SKILL else "comprehension",
    }


def normalize_quiz(raw_quiz: list[Any], topic_id: str) -> list[dict[str, Any]]:
    """Normalize an existing quiz list without calling the LLM."""
    items = []
    for raw in raw_quiz or []:
        item = _normalize_item(raw, topic_id, len(items) + 1)
        if item:
            items.append(item)
    return items


def quiz_is_complete(quiz: Any, min_questions: int = 3) -> bool:
    """True when *quiz* already satisfies the learner-app contract."""
    if not isinstance(quiz, list) or len(quiz) < min_questions:
        return False
    return all(
        isinstance(q, dict)
        and q.get("id")
        and q.get("question")
        and q.get("explanation")
        and isinstance(q.get("options"), list)
        and len(q["options"]) >= 2
        and q.get("answer") in q["options"]
        for q in quiz
    )


def generate_quiz(
    script: dict[str, Any],
    level: str = "A1A2",
    category: str = "dialogue",
    topic_id: str = "",
    question_count: int = DEFAULT_QUESTION_COUNT,
) -> list[dict[str, Any]]:
    """Generate and validate a quiz for *script*. Returns [] if generation fails."""
    from pipeline.generate.generate_script import _generate_script_gemini

    topic_id = topic_id or script.get("topic_id", "lesson")
    prompt = _build_prompt(script, level, category, question_count)

    try:
        result = _generate_script_gemini(prompt)
    except Exception as exc:
        LOGGER.error("quiz generation failed for topic_id=%s: %s", topic_id, exc)
        return []

    raw_quiz = result.get("quiz") if isinstance(result, dict) else None
    if not isinstance(raw_quiz, list):
        LOGGER.error("quiz generation returned no 'quiz' array for topic_id=%s", topic_id)
        return []

    quiz = normalize_quiz(raw_quiz, topic_id)
    if len(quiz) < 3:
        LOGGER.warning(
            "quiz: only %d valid questions for topic_id=%s (wanted %d)",
            len(quiz), topic_id, question_count,
        )
    LOGGER.info("quiz: %d questions generated for topic_id=%s", len(quiz), topic_id)
    return quiz[:question_count]
