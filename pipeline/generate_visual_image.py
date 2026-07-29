from __future__ import annotations

import logging
import re
import shutil
import subprocess
import time
from pathlib import Path

from pipeline import settings
from pipeline.utils import command_exists


_IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp")
LOGGER = logging.getLogger(__name__)


def _load_prompt_template() -> str:
    prompt_path = settings.ROOT / "prompts" / "image_prompt.md"
    if prompt_path.exists():
        return prompt_path.read_text(encoding="utf-8")
    return (
        "Create one cartoon image background for a Dutch A1 lesson.\n"
        "Topic id: {{TOPIC_ID}}\n"
        "Topic title: {{TOPIC_TITLE}}\n"
        "Background brief: {{BACKGROUND_BRIEF}}\n"
        "Include one male and one female cartoon human talking.\n"
    )


def _background_brief(topic_title: str, topic_id: str) -> str:
    key = f"{topic_title} {topic_id}".lower()
    if "cafe" in key or "coffee" in key or "order" in key:
        return "Warm Dutch cafe interior with menu board, coffee counter, and soft hanging lamps"
    if "train" in key or "ticket" in key or "station" in key:
        return "Dutch train platform with departure board, tracks, and ticket machine"
    if "supermarket" in key or "market" in key or "grocery" in key:
        return "Colorful supermarket aisle with shelves, signs, and shopping baskets"
    if "direction" in key or "street" in key or "map" in key:
        return "City street corner with signposts, zebra crossing, and map panel"
    if "introduce" in key or "name" in key or "origin" in key:
        return "Friendly neighborhood square with benches and small Dutch houses"
    if "restaurant" in key or "dinner" in key or "food" in key:
        return "Cosy Dutch restaurant interior with table settings and a chalkboard menu"
    if "office" in key or "work" in key or "reception" in key:
        return "Modern Dutch office reception with desk, plants, and company signage"
    if "classroom" in key or "school" in key or "learn" in key:
        return "Bright Dutch classroom with whiteboard, desks, and educational posters"
    if "pharmacy" in key or "medicine" in key or "health" in key:
        return "Clean Dutch pharmacy with shelves of products and a service counter"
    if "phone" in key or "call" in key:
        return "Split-screen Dutch living room and street scene for a phone conversation"
    if "weather" in key or "rain" in key or "sun" in key:
        return "Dutch street with canal and typical row houses under a partly cloudy sky"
    if "weekend" in key or "market" in key:
        return "Outdoor Dutch weekend market with stalls, flowers, and canal in the background"
    if "kitchen" in key or "home" in key or "house" in key:
        return "Cosy Dutch home kitchen with tiled walls, wooden counter, and window overlooking canal"
    return "Clean Dutch daily-life scene matching the topic title with clear environment cues"


# Dutch signs per scene type, derived from visual_style.yaml scenes and topic tracks
_DUTCH_SIGNS: dict[str, list[str]] = {
    "cafe": [
        "Koffie €2,50", "Thee €2,00", "Dagschotel €8,50",
        "OPEN", "Welkom!", "Menukaart", "Kassa →",
    ],
    "train": [
        "Amsterdam Centraal", "Vertrek / Departure", "Spoor 4",
        "Kaartjes kopen", "Instappen", "Uitstappen", "NS",
        "Let op! Deuren sluiten automatisch.",
    ],
    "supermarket": [
        "Aanbiedingen", "Kassa", "Groente & Fruit",
        "Zuivel", "Brood & Banket", "Biologisch",
        "2 voor €3,00", "Vandaag vers",
    ],
    "street": [
        "Centrum →", "Fietspad", "Oversteken",
        "Stop", "Parkeren verboden", "Straat",
        "← Markt", "Bushalte",
    ],
    "restaurant": [
        "Menu", "Dagmenu €12,50", "Reserveren",
        "Welkom bij Restaurant De Tulp", "Vandaag open: 17:00–22:00",
        "Betalen bij de kassa", "Toiletten →",
    ],
    "office": [
        "Receptie", "Bezoeker aanmelden", "Vergaderzaal A",
        "Nooduitgang →", "Welkom!", "Lift", "Kantoor 101",
    ],
    "classroom": [
        "Nederlands voor beginners", "Les 1: Begroeten",
        "Huiswerk: bladzijde 5", "Goed gedaan!",
        "Woordenschat", "Grammatica",
    ],
    "pharmacy": [
        "Apotheek", "Openingstijden: ma–vr 9:00–18:00",
        "Op recept", "Vrij verkrijgbaar",
        "Pijnstillers", "Vitaminespoor", "Wachtrij hier →",
    ],
    "home": [
        "Welkom thuis", "Boodschappenlijstje",
        "Maandag: soep", "Niet vergeten!", "Afval: dinsdag",
    ],
    "weather": [
        "Weerbericht", "Verwacht: bewolkt met regen",
        "Max. 14°C", "KNMI", "Paraplu meenemen!",
    ],
    "market": [
        "Markt", "Zaterdag 9:00–17:00",
        "Verse bloemen €5,–", "Biologische groenten",
        "Hollandse kaas", "Stroopwafels 3 voor €2,–",
    ],
    "default": [
        "Welkom", "Info", "Open", "Gesloten",
        "Let op", "→ Uitgang", "Informatie",
    ],
}


def _dutch_signs(topic_title: str, topic_id: str) -> str:
    """Return Dutch sign text relevant to the scene, drawn from visual_style.yaml scene types."""
    key = f"{topic_title} {topic_id}".lower()
    if "cafe" in key or "coffee" in key or "order" in key:
        signs = _DUTCH_SIGNS["cafe"]
    elif "train" in key or "ticket" in key or "station" in key:
        signs = _DUTCH_SIGNS["train"]
    elif "supermarket" in key or "grocery" in key:
        signs = _DUTCH_SIGNS["supermarket"]
    elif "direction" in key or "street" in key or "map" in key:
        signs = _DUTCH_SIGNS["street"]
    elif "restaurant" in key or "dinner" in key or "food" in key:
        signs = _DUTCH_SIGNS["restaurant"]
    elif "office" in key or "work" in key or "reception" in key:
        signs = _DUTCH_SIGNS["office"]
    elif "classroom" in key or "school" in key or "learn" in key:
        signs = _DUTCH_SIGNS["classroom"]
    elif "pharmacy" in key or "medicine" in key or "health" in key:
        signs = _DUTCH_SIGNS["pharmacy"]
    elif "kitchen" in key or "home" in key or "house" in key:
        signs = _DUTCH_SIGNS["home"]
    elif "weather" in key or "rain" in key or "sun" in key:
        signs = _DUTCH_SIGNS["weather"]
    elif "market" in key or "weekend" in key:
        signs = _DUTCH_SIGNS["market"]
    elif "introduce" in key or "name" in key or "origin" in key:
        signs = _DUTCH_SIGNS["street"]  # neighborhood square uses street signs
    else:
        signs = _DUTCH_SIGNS["default"]
    return ", ".join(f'"{s}"' for s in signs)


def _build_prompt(topic_id: str, topic_title: str, width: int, height: int) -> str:
    template = _load_prompt_template()
    return (
        template.replace("{{TOPIC_ID}}", topic_id)
        .replace("{{TOPIC_TITLE}}", topic_title)
        .replace("{{WIDTH}}", str(width))
        .replace("{{HEIGHT}}", str(height))
        .replace("{{BACKGROUND_BRIEF}}", _background_brief(topic_title, topic_id))
        .replace("{{DUTCH_SIGNS}}", _dutch_signs(topic_title, topic_id))
    )


def _collect_image_paths(text: str, cwd: Path) -> list[Path]:
    candidates: list[Path] = []

    # Match absolute/relative file paths printed by CLI.
    path_pattern = r"([^\s'\"]+\.(?:png|jpg|jpeg|webp))"
    for raw in re.findall(path_pattern, text, flags=re.IGNORECASE):
        candidate = Path(raw)
        if not candidate.is_absolute():
            candidate = (cwd / candidate).resolve()
        if candidate.exists() and candidate.suffix.lower() in _IMAGE_EXTENSIONS:
            candidates.append(candidate)

    # Keep order while removing duplicates.
    deduped: list[Path] = []
    seen: set[str] = set()
    for path in candidates:
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(path)
    return deduped


def _newest_image_file(folder: Path, started_at: float) -> Path | None:
    if not folder.exists():
        return None

    newest_path: Path | None = None
    newest_mtime = 0.0
    for ext in _IMAGE_EXTENSIONS:
        for path in folder.glob(f"*{ext}"):
            try:
                stat = path.stat()
            except FileNotFoundError:
                continue
            if stat.st_mtime + 0.5 < started_at:
                continue
            if stat.st_mtime > newest_mtime:
                newest_mtime = stat.st_mtime
                newest_path = path
    return newest_path


def _run_ollama_image_generation(prompt: str, output_dir: Path, timeout_seconds: int) -> Path | None:
    if not command_exists("ollama"):
        LOGGER.error("image_generation.ollama_missing")
        return None

    model = settings.OLLAMA_IMAGE_MODEL
    command = ["ollama", "run", model, prompt]
    started_at = time.time()
    LOGGER.info("image_generation.start model=%s output_dir=%s", model, output_dir)

    try:
        proc = subprocess.run(
            command,
            cwd=str(output_dir),
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except Exception:
        LOGGER.exception("image_generation.subprocess_failed")
        return None

    elapsed = time.time() - started_at
    LOGGER.info("image_generation.subprocess_done returncode=%s elapsed_sec=%.2f", proc.returncode, elapsed)

    combined_output = f"{proc.stdout or ''}\n{proc.stderr or ''}"
    for path in _collect_image_paths(combined_output, output_dir):
        LOGGER.info("image_generation.file_detected file=%s", path)
        return path

    newest = _newest_image_file(output_dir, started_at=started_at)
    if newest:
        LOGGER.info("image_generation.file_detected_newest file=%s", newest)
    else:
        LOGGER.error("image_generation.no_output_file")
    return newest


def _normalize_to_png(source: Path, destination_png: Path) -> Path | None:
    destination_png.parent.mkdir(parents=True, exist_ok=True)
    if source.suffix.lower() == ".png":
        if source.resolve() == destination_png.resolve():
            return source
        shutil.copy2(source, destination_png)
        return destination_png

    if command_exists("ffmpeg"):
        command = [
            "ffmpeg",
            "-y",
            "-i",
            str(source),
            "-frames:v",
            "1",
            str(destination_png),
        ]
        try:
            subprocess.run(command, capture_output=True, text=True, check=True)
            if destination_png.exists():
                return destination_png
        except Exception:
            return None

    return None


def generate_topic_image(*, topic_id: str, topic_title: str, episode_id: int, output_root: Path) -> Path:
    started_at = time.perf_counter()
    render_cfg = settings.load_yaml(settings.ROOT / "config/visual_style.yaml").get("render", {})
    width = int(render_cfg.get("width", 1920))
    height = int(render_cfg.get("height", 1080))

    visuals_dir = output_root / "visuals"
    visuals_dir.mkdir(parents=True, exist_ok=True)
    output_png = visuals_dir / f"episode_{episode_id}_scene.png"

    prompt = _build_prompt(topic_id, topic_title, width, height)
    LOGGER.info(
        "image_generation.request episode=%s topic_id=%s topic_title=%s size=%sx%s",
        episode_id,
        topic_id,
        topic_title,
        width,
        height,
    )
    LOGGER.debug("image_generation.prompt_chars=%d", len(prompt))
    generated_file = _run_ollama_image_generation(prompt, visuals_dir, timeout_seconds=180)

    if not generated_file or not generated_file.exists():
        LOGGER.error("image_generation.failed_no_file episode=%s", episode_id)
        raise RuntimeError(
            f"Image generation failed for episode {episode_id}: model '{settings.OLLAMA_IMAGE_MODEL}' did not produce an image file"
        )

    normalized = _normalize_to_png(generated_file, output_png)
    if not normalized or not normalized.exists():
        LOGGER.error("image_generation.failed_normalize episode=%s source=%s", episode_id, generated_file)
        raise RuntimeError(
            f"Image generation failed for episode {episode_id}: unable to normalize generated file '{generated_file}' to PNG"
        )

    LOGGER.info(
        "image_generation.done episode=%s output=%s elapsed_sec=%.2f",
        episode_id,
        normalized,
        time.perf_counter() - started_at,
    )

    return normalized
