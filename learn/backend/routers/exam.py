from __future__ import annotations

import re

from fastapi import APIRouter, HTTPException, status

from models import ExamFeedbackRequest, ExamFeedbackResult

router = APIRouter()


def _sentences(answer: str) -> list[str]:
    return [part.strip() for part in re.split(r"(?<=[.!?])\s+", answer.strip()) if part.strip()]


def _build_feedback(prompt: str, answer: str) -> ExamFeedbackResult:
    cleaned = answer.strip()
    if not cleaned:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Answer is required")

    words = re.findall(r"\b[\w'-]+\b", cleaned.lower())
    sentence_count = max(1, len(_sentences(cleaned)))
    core_links = ["because", "however", "therefore", "for example", "in addition", "although"]
    has_connective = any(link in cleaned.lower() for link in core_links)
    has_specific_detail = len(words) >= 35 and any(
        token in cleaned.lower() for token in ("example", "for example", "such as", "because", "therefore")
    )

    missing: list[str] = []
    if len(words) < 30:
        missing.append("Add more detail so the answer feels fully developed.")
    if not has_connective:
        missing.append("Use linking words such as because, however, or for example to show clear reasoning.")
    if sentence_count < 2:
        missing.append("Add another sentence or example so the explanation feels more complete.")
    if not has_specific_detail:
        missing.append("Include a concrete example or clearer evidence to support your point.")

    if not missing:
        strengths = [
            "Your answer directly addresses the prompt.",
            "It gives a clear reason and supports it with relevant detail.",
            "The argument is easy to follow and reads as convincing.",
        ]
        return ExamFeedbackResult(
            prompt=prompt,
            answer=answer,
            summary="This is a strong answer. It already explains the point clearly and gives enough reasoning that no major revision is needed.",
            justification="The response responds directly to the question and supports the point with a clear reason and relevant detail. It is already persuasive and well structured enough that no major fix is required.",
            improvement_suggestions=[],
            strengths=strengths,
            weaknesses=[],
        )

    strengths: list[str] = []
    if len(words) >= 25:
        strengths.append("Your answer has enough substance to explain the main point in a complete sentence.")
    if has_connective:
        strengths.append("You use linking language that helps the argument flow logically from one point to the next.")
    if has_specific_detail:
        strengths.append("The answer includes concrete detail, which makes the reasoning feel more credible and specific.")
    if not strengths:
        strengths.append("The response shows a clear attempt to address the prompt and communicate the main idea.")

    weaknesses: list[str] = []
    if len(words) < 50:
        weaknesses.append("The answer could be more developed with a little more detail and evidence.")
    if not has_connective:
        weaknesses.append("Add link words such as because, however, for example, and therefore to make the reasoning clearer.")
    if sentence_count < 2:
        weaknesses.append("A second sentence or example would make the answer feel more complete and better justified.")
    if not has_specific_detail:
        weaknesses.append("Add a concrete example or precise reason so the justification is easier to follow.")
    if not weaknesses:
        weaknesses.append("The answer is already strong; a final polish can make it sound even more confident and concise.")

    suggestions = [
        "Expand the answer with one concrete example that supports your point.",
        "Use a stronger structure: claim, reason, example, and conclusion.",
        "Replace vague phrases with more specific language to make the justification more convincing.",
    ]
    if not has_connective:
        suggestions.insert(0, "Add linking words such as because, however, and for example to make the logic easier to follow.")
    if len(words) < 60:
        suggestions.append("Aim for a fuller answer by adding one or two more sentences that explain the reason behind your choice.")

    summary = (
        f"This response addresses the prompt with {len(words)} words across {sentence_count} sentence(s). "
        f"It shows a reasonable attempt at justification, but adding clearer evidence and a stronger structure would make it more persuasive."
    )

    justification = (
        "The answer responds to the prompt by taking a position and giving a reasoned explanation. "
        "It is strongest when it connects the point to a clear example or evidence from the question context. "
        "The main improvement is to make the reasoning more explicit so the examiner can see why this answer is valid."
    )

    return ExamFeedbackResult(
        prompt=prompt,
        answer=answer,
        summary=summary,
        justification=justification,
        improvement_suggestions=suggestions[:4],
        strengths=strengths[:3],
        weaknesses=weaknesses[:3],
    )


@router.post("/exam/feedback", response_model=ExamFeedbackResult)
async def exam_feedback(payload: ExamFeedbackRequest) -> ExamFeedbackResult:
    return _build_feedback(payload.prompt, payload.answer)


@router.post("/exam/justify", response_model=ExamFeedbackResult)
async def exam_justify(payload: ExamFeedbackRequest) -> ExamFeedbackResult:
    return _build_feedback(payload.prompt, payload.answer)


@router.post("/writing/feedback", response_model=ExamFeedbackResult)
async def writing_feedback(payload: ExamFeedbackRequest) -> ExamFeedbackResult:
    return _build_feedback(payload.prompt, payload.answer)


@router.post("/writing/justify", response_model=ExamFeedbackResult)
async def writing_justify(payload: ExamFeedbackRequest) -> ExamFeedbackResult:
    return _build_feedback(payload.prompt, payload.answer)
