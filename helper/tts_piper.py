import logging
import os
import subprocess
import sys
from datetime import datetime

logger = logging.getLogger(__name__)

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

MODEL_MAP = {
    "english":    os.path.join(BASE_DIR, "voices", "en_US-lessac-medium.onnx"),
    "indonesian": os.path.join(BASE_DIR, "voices", "id_ID-news_tts-medium.onnx"),
}

RESULTS_DIR = os.path.join(BASE_DIR, "results")
os.makedirs(RESULTS_DIR, exist_ok=True)

PIPER_BIN = os.path.join(os.path.dirname(sys.executable), "piper")


def _output_path() -> str:
    now = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    return os.path.join(RESULTS_DIR, f"output_{now}.wav")


def tts_piper(
    text: str,
    lang: str = "indonesian",
    speed: int = 50,
) -> str | None:
    if not text or not text.strip():
        logger.warning("tts_piper: empty text")
        return None

    model = MODEL_MAP.get(lang, MODEL_MAP["indonesian"])

    speed = max(0, min(100, speed))
    length_scale = 1.5 - speed / 100

    path = _output_path()

    try:
        logger.info(f"Piper TTS — lang={lang} speed={speed} length_scale={length_scale:.2f}")

        subprocess.run(
            [
                PIPER_BIN,
                "--model", model,
                "--output_file", path,
                "--length_scale", str(length_scale),
            ],
            input=text,
            text=True,
            check=True,
        )

        logger.info(f"Piper TTS saved: {path}")
        return path

    except FileNotFoundError:
        logger.error(f"Piper binary not found at {PIPER_BIN}")
        return None
    except subprocess.CalledProcessError:
        logger.exception("Piper TTS failed")
        return None