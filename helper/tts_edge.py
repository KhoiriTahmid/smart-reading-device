import asyncio
import logging
import os
from datetime import datetime

import edge_tts

logger = logging.getLogger(__name__)

VOICE_MAP = {
    "english":    "en-US-AriaNeural",
    "indonesian": "id-ID-GadisNeural",
}

BASE_DIR    = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
RESULTS_DIR = os.path.join(BASE_DIR, "results")
os.makedirs(RESULTS_DIR, exist_ok=True)


def _output_path() -> str:
    now = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    return os.path.join(RESULTS_DIR, f"output_{now}.mp3")


async def _synthesize(text: str, voice: str, path: str, speed: int = 50) -> None:
    speed = max(0, min(100, speed))
    rate = f"{speed - 50:+d}%"

    communicate = edge_tts.Communicate(
        text=text,
        voice=voice,
        rate=rate,
    )

    await communicate.save(path)


def tts_edge(text: str, lang: str = "indonesian", speed: int = 50) -> str | None:
    if not text or not text.strip():
        logger.warning("tts_edge: empty text")
        return None

    voice = VOICE_MAP.get(lang, VOICE_MAP["indonesian"])
    path  = _output_path()

    try:
        logger.info(f"Edge TTS — lang={lang} voice={voice} chars={len(text)} speed={speed}")
        asyncio.run(_synthesize(text, voice, path, speed))
        logger.info(f"Edge TTS saved: {path}")
        return path
    except Exception:
        logger.exception("Edge TTS failed")
        return None