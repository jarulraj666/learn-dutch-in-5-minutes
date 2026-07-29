from __future__ import annotations

from typing import Any


def validate_script_structure(script: dict[str, Any]) -> list[str]:
    errors: list[str] = []

    if not script.get("dialogue"):
        errors.append("Dialogue is missing")

    quiz = script.get("quiz", [])
    if len(quiz) < 2:  # Minimum 2 questions
        errors.append(f"Quiz must have at least 2 questions (found {len(quiz)})")

    grammar_notes = script.get("grammar_notes", [])
    # Grammar notes are optional but preferred
    # if not grammar_notes:
    #     errors.append("Grammar notes are missing")

    return errors


def validate_description(description: str) -> list[str]:
    required = ["Grammar Notes", "Pattern Breakdown", "Mini Examples"]
    errors = []
    for section in required:
        if section not in description:
            errors.append(f"Description missing section: {section}")
    return errors
