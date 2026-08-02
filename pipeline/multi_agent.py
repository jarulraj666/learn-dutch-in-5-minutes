from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from pipeline import settings
from pipeline.generate_metadata import generate_metadata
from pipeline.ollama_client import call_ollama, extract_json_object
from pipeline.utils import iter_dialogue_turns, to_compact_dialogue


@dataclass
class WorkflowTopic:
    topic_id: str
    topic_title: str
    track: str
    language: str


def _read_prompt(name: str) -> str:
    return (settings.ROOT / "prompts" / name).read_text(encoding="utf-8")


class ConversationAgent:
    def run(self, topic: WorkflowTopic) -> dict[str, Any]:
        prompt = _read_prompt("conversation_prompt.md")
        enriched = (
            f"{prompt}\n"
            f"topic_id={topic.topic_id}\n"
            f"topic_title={topic.topic_title}\n"
            f"track={topic.track}\n"
            f"language={topic.language}\n"
        )
        text = call_ollama(enriched)
        data = extract_json_object(text)
        data.setdefault("topic_id", topic.topic_id)
        data.setdefault("topic_title", topic.topic_title)
        data.setdefault("language", topic.language)
        return data


class GrammarReviewAgent:
    def run(self, conversation_data: dict[str, Any]) -> dict[str, Any]:
        prompt = _read_prompt("grammar_review_prompt.md")
        enriched = f"{prompt}\n\nInput dialogue JSON:\n{json.dumps(conversation_data, ensure_ascii=False)}"
        text = call_ollama(enriched)
        return extract_json_object(text)


class VocabularyAgent:
    def run(self, dialogue_data: dict[str, Any]) -> dict[str, Any]:
        prompt = _read_prompt("vocabulary_prompt.md")
        enriched = f"{prompt}\n\nInput dialogue JSON:\n{json.dumps(dialogue_data, ensure_ascii=False)}"
        text = call_ollama(enriched)
        return extract_json_object(text)


class QuizAgent:
    def run(self, script_data: dict[str, Any]) -> dict[str, Any]:
        prompt = _read_prompt("quiz_prompt.md")
        enriched = f"{prompt}\n\nInput JSON:\n{json.dumps(script_data, ensure_ascii=False)}"
        text = call_ollama(enriched)
        return extract_json_object(text)


class VoiceAgent:
    def run(self, dialogue: list[dict[str, Any]]) -> dict[str, Any]:
        segments = []
        for idx, (speaker, line) in enumerate(iter_dialogue_turns(dialogue), start=1):
            segments.append(
                {
                    "segment": idx,
                    "speaker": speaker,
                    "text": line,
                    "tts_status": "planned",
                }
            )
        return {"voice_plan": segments}


class SubtitleAgent:
    def run(self, dialogue: list[dict[str, Any]]) -> dict[str, Any]:
        lines = []
        for idx, (_, line_text) in enumerate(iter_dialogue_turns(dialogue), start=1):
            lines.append(
                {
                    "index": idx,
                    "text": line_text,
                    "subtitle_status": "planned",
                }
            )
        return {"subtitle_plan": lines}


class AssembleVideoAgent:
    def run(self, topic_id: str) -> dict[str, Any]:
        return {
            "assembly_plan": {
                "topic_id": topic_id,
                "style": "cartoon_flat",
                "status": "planned",
            }
        }


class UploadPrepAgent:
    def run(self, script: dict[str, Any], playlist_track: str) -> dict[str, Any]:
        metadata = generate_metadata(script, playlist_track=playlist_track)
        return {"upload_metadata": metadata}


def run_multi_agent_content(topic: WorkflowTopic) -> dict[str, Any]:
    conversation = ConversationAgent().run(topic)
    grammar = GrammarReviewAgent().run(conversation)

    dialogue = to_compact_dialogue(
        iter_dialogue_turns(grammar.get("dialogue", conversation.get("dialogue", [])))
    )
    grammar_notes = grammar.get("grammar_notes", [])

    vocab = VocabularyAgent().run({"dialogue": dialogue})

    base_script = {
        "topic_id": topic.topic_id,
        "topic_title": topic.topic_title,
        "language": topic.language,
        "dialogue": dialogue,
        "key_phrases": conversation.get("key_phrases", []),
        "vocabulary": vocab.get("vocabulary", []),
        "grammar_notes": grammar_notes,
        "translations": grammar.get("translations", []),
    }

    quiz = QuizAgent().run(base_script)
    base_script["quiz"] = quiz.get("quiz", [])

    voice_plan = VoiceAgent().run(base_script["dialogue"])
    subtitle_plan = SubtitleAgent().run(base_script["dialogue"])
    assembly_plan = AssembleVideoAgent().run(topic.topic_id)

    base_script["agent_outputs"] = {
        "grammar_review": grammar,
        "voice": voice_plan,
        "subtitle": subtitle_plan,
        "assemble": assembly_plan,
    }

    return base_script
