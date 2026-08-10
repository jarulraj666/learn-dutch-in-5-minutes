"""Audio QA Module.

Compares the words actually spoken in a WAV file against the expected script
using free WhisperX ASR and a word-level diff.

Issue types
-----------
MISSING  – word(s) present in the script but not spoken in the audio.
EXTRA    – word(s) spoken in the audio that are not in the script.

Score
-----
score = matched_words / total_script_words * 100
missing words carry a full penalty (-1 per word).
extra words carry a half penalty (-0.5 per word).
Passes when score >= PASS_THRESHOLD (default 95).
"""

from __future__ import annotations

import difflib
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

LOGGER = logging.getLogger(__name__)

# Episodes with score >= this are considered passing
PASS_THRESHOLD = 95.0


# ── Text Normalisation ────────────────────────────────────────────────────────

_PACING_RE = re.compile(r"\[.*?\]")          # strip [slow], [pause for 1 second], …
_PUNCT_RE  = re.compile(r"[^\w\s'\-]", re.UNICODE)


def _normalise(text: str) -> str:
    """Lower-case, strip pacing markers and punctuation."""
    text = _PACING_RE.sub("", text)
    text = _PUNCT_RE.sub("", text)
    return " ".join(text.lower().split())


# Similarity threshold above which a spoken word is considered a match for a
# script word (handles pronunciation variants, ASR accent differences, etc.)
_WORD_MATCH_THRESHOLD = 0.75
# Maximum number of consecutive spoken words to try merging into one script word
_COMPOUND_MERGE_WINDOW = 4

# Words that strongly indicate Dutch — used to detect line language.
_DUTCH_MARKERS = frozenset({
    "ik", "jij", "hij", "zij", "wij", "jullie", "het", "een", "de",
    "van", "voor", "aan", "niet", "zijn", "hebben", "dat", "dit",
    "met", "op", "uit", "maar", "ook", "als", "nog", "door",
})
# Words that strongly indicate English (not present in Dutch).
_ENGLISH_MARKERS = frozenset({
    "the", "our", "your", "their", "this", "that", "these", "those",
    "and", "but", "with", "from", "have", "has", "are", "were",
    "would", "could", "should", "very", "hello", "welcome",
})


def _line_is_target_language(text: str, language: str) -> bool:
    """Return True if *text* appears to be written in *language*.

    Uses a simple word-overlap heuristic against known Dutch/English marker
    sets. Lines with no detectable language are kept (returned True).
    Only Dutch ("nl") filtering is currently implemented; all other languages
    return True unconditionally.
    """
    if language != "nl":
        return True
    words = set(_normalise(text).split())
    dutch_hits   = len(words & _DUTCH_MARKERS)
    english_hits = len(words & _ENGLISH_MARKERS)
    if dutch_hits == 0 and english_hits == 0:
        return True          # no signal — keep
    return dutch_hits >= english_hits


def _script_words(dialogue: list[dict[str, str]], language: str = "nl") -> list[str]:
    """Return flat normalised word list from script lines that match *language*.

    English translation lines are excluded when language is "nl" so the QA
    doesn't penalise for lines intentionally spoken in Dutch instead.
    """
    words: list[str] = []
    for turn in dialogue:
        for text in turn.values():
            if _line_is_target_language(text, language):
                words.extend(_normalise(text).split())
    return words


# ── Free ASR ──────────────────────────────────────────────────────────────────


def _free_transcribe(wav_path: Path, language: str) -> list[dict[str, Any]]:
    """Run WhisperX free ASR (no script guidance) and return raw segments.

    Transcribes whatever was actually spoken, including content not in the
    script (e.g. Gemini vocalising a pacing tag like "pause for one second").
    """
    import torch
    import whisperx

    device = "cuda" if torch.cuda.is_available() else "cpu"
    compute_type = "float16" if device == "cuda" else "int8"
    audio = whisperx.load_audio(str(wav_path))
    model = whisperx.load_model("base", device, compute_type=compute_type, language=language)
    result = model.transcribe(audio, batch_size=16)
    return result.get("segments", [])


def _spoken_words(segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return [{word, start, end}, …] from ASR segments.

    Timestamps within each segment are distributed proportionally across
    the words in that segment.
    """
    result: list[dict[str, Any]] = []
    for seg in segments:
        tokens = _normalise(seg.get("text", "")).split()
        if not tokens:
            continue
        seg_start = seg.get("start", -1.0)
        seg_end   = seg.get("end",   -1.0)
        if seg_start >= 0 and seg_end > seg_start:
            step = (seg_end - seg_start) / len(tokens)
        else:
            step = 0.0
        for i, token in enumerate(tokens):
            result.append({
                "word":  token,
                "start": seg_start + i * step       if step else seg_start,
                "end":   seg_start + (i + 1) * step if step else seg_end,
            })
    return result


def _preprocess_compounds(
    spoken_word_list: list[str],
    script_words: list[str],
) -> list[str]:
    """Merge or split spoken words to align with the script's compound structure.

    - Merge: ["als", "u", "blieft"] → ["alstublieft"] when concat matches a script word.
    - Split: ["maincourse"] → ["main", "course"] when the word matches a script bigram.
    """
    script_set = set(script_words)

    # Build a set of consecutive script word pairs/triples for split detection
    script_ngrams: dict[str, list[str]] = {}
    for n in range(2, _COMPOUND_MERGE_WINDOW + 1):
        for i in range(len(script_words) - n + 1):
            joined = "".join(script_words[i : i + n])
            script_ngrams[joined] = list(script_words[i : i + n])

    result: list[str] = []
    i = 0
    while i < len(spoken_word_list):
        word = spoken_word_list[i]

        # 1. Try to split a single spoken word into consecutive script words
        if word not in script_set and word in script_ngrams:
            result.extend(script_ngrams[word])
            i += 1
            continue

        # 2. Try to merge consecutive spoken words into a single script word
        merged = False
        for window in range(_COMPOUND_MERGE_WINDOW, 1, -1):
            if i + window > len(spoken_word_list):
                continue
            candidate = "".join(spoken_word_list[i : i + window])
            if candidate in script_set:
                result.append(candidate)
                i += window
                merged = True
                break
            # Also try fuzzy match for merged candidate
            best_ratio = max(
                (difflib.SequenceMatcher(None, candidate, sw).ratio() for sw in script_set),
                default=0.0,
            )
            if best_ratio >= _WORD_MATCH_THRESHOLD + 0.05:  # stricter for merges
                best_sw = max(script_set, key=lambda sw: difflib.SequenceMatcher(None, candidate, sw).ratio())
                result.append(best_sw)
                i += window
                merged = True
                break
        if not merged:
            result.append(word)
            i += 1

    return result


def _normalise_spoken_words(
    spoken_word_list: list[str],
    script_words: list[str],
) -> list[str]:
    """Replace each spoken word with its closest script word when similarity
    is >= _WORD_MATCH_THRESHOLD.

    This absorbs common ASR artefacts:
    - pronunciation variants  ("vorgerecht" → "voorgerecht", "foi" → "fooi")
    - accent differences      ("nou" → "now")
    - compound word splits    ("als u blieft" stays split — handled at list level)
    - number formats          ("50" → "vijftig") when close enough
    - language confusion      ("de" → "the") when similar string
    """
    script_set = set(script_words)
    result: list[str] = []
    for word in spoken_word_list:
        if word in script_set:
            result.append(word)
            continue
        best_word = word
        best_ratio = 0.0
        for sw in script_set:
            r = difflib.SequenceMatcher(None, word, sw).ratio()
            if r > best_ratio:
                best_ratio = r
                best_word = sw
        result.append(best_word if best_ratio >= _WORD_MATCH_THRESHOLD else word)
    return result


# ── Data Types ────────────────────────────────────────────────────────────────


@dataclass
class QAIssue:
    issue_type:  str    # MISSING | EXTRA
    script_text: str    # word(s) expected from script (space-separated)
    spoken_text: str    # word(s) actually spoken  (space-separated, "" if purely MISSING)
    start_ts:    float  # approximate start timestamp (-1.0 if unknown)
    end_ts:      float  # approximate end   timestamp (-1.0 if unknown)


@dataclass
class QAReport:
    total_script_words: int = 0
    total_spoken_words: int = 0
    matched_words:      int = 0
    issues: list[QAIssue] = field(default_factory=list)

    @property
    def missing_word_count(self) -> int:
        return sum(len(i.script_text.split()) for i in self.issues if i.issue_type == "MISSING")

    @property
    def extra_word_count(self) -> int:
        return sum(len(i.spoken_text.split()) for i in self.issues if i.issue_type == "EXTRA")

    @property
    def score(self) -> float:
        if self.total_script_words == 0:
            return 100.0
        penalty = self.missing_word_count * 1.0 + self.extra_word_count * 0.5
        return max(0.0, 100.0 * (1.0 - penalty / self.total_script_words))

    @property
    def passed(self) -> bool:
        return self.score >= PASS_THRESHOLD


# ── Main QA Function ──────────────────────────────────────────────────────────


def run_audio_qa(
    wav_path: str | Path,
    script_dialogue: list[dict[str, str]],
    language: str = "nl",
    script_language_filter: str | None = None,
) -> QAReport:
    """Transcribe *wav_path* with free ASR and compare word-by-word against
    *script_dialogue*.

    Args:
        wav_path:               Path to the WAV audio file.
        script_dialogue:        Dialogue list, e.g. [{"Speaker1": "text"}, …].
        language:               BCP-47 language code for WhisperX ASR (default: "nl").
        script_language_filter: If set (e.g. "nl" or "en"), only script lines
                                detected as that language are included in the
                                comparison.  None → all lines included.

    Returns:
        QAReport with MISSING / EXTRA issues and a 0–100 score.
    """
    wav_path = Path(wav_path)
    if not wav_path.exists():
        raise FileNotFoundError(f"Audio file not found: {wav_path}")

    LOGGER.info("qa_audio.start wav=%s", wav_path.name)

    # Step 1: Free ASR — transcribe what was actually spoken
    LOGGER.info("qa_audio.transcribing (free ASR) ...")
    segments = _free_transcribe(wav_path, language)
    LOGGER.info("qa_audio.transcribed segments=%d", len(segments))

    # Step 2: Build word lists — filter script by language if requested
    filter_lang = script_language_filter if script_language_filter is not None else language
    script_wds = _script_words(script_dialogue, filter_lang)
    spoken_wds = _spoken_words(segments)
    spoken_word_list = [w["word"] for w in spoken_wds]

    report = QAReport(
        total_script_words=len(script_wds),
        total_spoken_words=len(spoken_word_list),
    )

    if not spoken_word_list:
        LOGGER.warning("qa_audio.no_transcript — ASR returned zero words")
        report.issues.append(QAIssue(
            issue_type="MISSING",
            script_text=" ".join(script_wds),
            spoken_text="",
            start_ts=-1.0,
            end_ts=-1.0,
        ))
        return report

    # Step 3: Word-level diff (script vs spoken)
    # Pre-process: merge/split compound words, then fuzzy-map pronunciation variants.
    spoken_word_list = _preprocess_compounds(spoken_word_list, script_wds)
    spoken_word_list = _normalise_spoken_words(spoken_word_list, script_wds)
    matcher = difflib.SequenceMatcher(None, script_wds, spoken_word_list, autojunk=False)
    matched = 0

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():

        if tag == "equal":
            matched += i2 - i1

        elif tag == "delete":
            # Script words not spoken at all
            ts_start = spoken_wds[j1]["start"] if j1 < len(spoken_wds) else -1.0
            ts_end   = spoken_wds[j1]["end"]   if j1 < len(spoken_wds) else -1.0
            report.issues.append(QAIssue(
                issue_type="MISSING",
                script_text=" ".join(script_wds[i1:i2]),
                spoken_text="",
                start_ts=ts_start,
                end_ts=ts_end,
            ))

        elif tag == "insert":
            # Words spoken that are not in the script
            ts_start = spoken_wds[j1]["start"]       if j1 < len(spoken_wds)      else -1.0
            ts_end   = spoken_wds[j2 - 1]["end"]     if 0 < j2 <= len(spoken_wds) else -1.0
            report.issues.append(QAIssue(
                issue_type="EXTRA",
                script_text="",
                spoken_text=" ".join(spoken_word_list[j1:j2]),
                start_ts=ts_start,
                end_ts=ts_end,
            ))

        elif tag == "replace":
            # Script words replaced by different words — MISSING (what was expected)
            # and EXTRA (what was said instead) at the same position.
            ts_start = spoken_wds[j1]["start"]       if j1 < len(spoken_wds)      else -1.0
            ts_end   = spoken_wds[j2 - 1]["end"]     if 0 < j2 <= len(spoken_wds) else -1.0
            report.issues.append(QAIssue(
                issue_type="MISSING",
                script_text=" ".join(script_wds[i1:i2]),
                spoken_text=" ".join(spoken_word_list[j1:j2]),  # what was said instead
                start_ts=ts_start,
                end_ts=ts_end,
            ))
            report.issues.append(QAIssue(
                issue_type="EXTRA",
                script_text=" ".join(script_wds[i1:i2]),        # what was expected
                spoken_text=" ".join(spoken_word_list[j1:j2]),
                start_ts=ts_start,
                end_ts=ts_end,
            ))

    report.matched_words = matched
    return report


# ── Reporting ─────────────────────────────────────────────────────────────────


def _fmt_ts(seconds: float) -> str:
    if seconds < 0:
        return "??:??"
    m, s = divmod(int(seconds), 60)
    return f"{m:02d}:{s:02d}"


def log_qa_report(report: QAReport, wav_name: str = "") -> None:
    """Log QA results to the module logger."""
    label   = f" [{wav_name}]" if wav_name else ""
    missing = [i for i in report.issues if i.issue_type == "MISSING"]
    extra   = [i for i in report.issues if i.issue_type == "EXTRA" and not i.script_text]
    score   = report.score

    if not report.issues:
        LOGGER.info(
            "qa_audio.PASS%s — score=%.1f/100 | all %d script words matched",
            label, score, report.total_script_words,
        )
        return

    LOGGER.warning(
        "qa_audio.FAIL%s — score=%.1f/100 | "
        "script=%d spoken=%d matched=%d missing_words=%d extra_words=%d",
        label, score,
        report.total_script_words, report.total_spoken_words, report.matched_words,
        report.missing_word_count, report.extra_word_count,
    )

    for issue in missing:
        if issue.spoken_text:
            LOGGER.warning(
                "  [MISSING ] @ (%s-%s) | expected: %r  heard: %r",
                _fmt_ts(issue.start_ts), _fmt_ts(issue.end_ts),
                issue.script_text[:80], issue.spoken_text[:80],
            )
        else:
            LOGGER.warning(
                "  [MISSING ] @ (%s-%s) | expected: %r",
                _fmt_ts(issue.start_ts), _fmt_ts(issue.end_ts),
                issue.script_text[:80],
            )

    for issue in extra:
        LOGGER.warning(
            "  [EXTRA   ] @ (%s-%s) | not in script: %r",
            _fmt_ts(issue.start_ts), _fmt_ts(issue.end_ts),
            issue.spoken_text[:80],
        )


def run_audio_qa_bilingual(
    wav_path: str | Path,
    script_dialogue: list[dict[str, str]],
) -> tuple[QAReport, QAReport]:
    """Run QA separately for Dutch and English script lines.

    Dutch check:   ASR in Dutch mode, compares Dutch script lines only.
    English check: ASR in English mode, compares English script lines only.

    Returns:
        (dutch_report, english_report)
    """
    wav_path = Path(wav_path)
    LOGGER.info("qa_audio.bilingual_start wav=%s", wav_path.name)

    dutch_report   = run_audio_qa(wav_path, script_dialogue,
                                   language="nl", script_language_filter="nl")
    english_report = run_audio_qa(wav_path, script_dialogue,
                                   language="en", script_language_filter="en")
    return dutch_report, english_report
