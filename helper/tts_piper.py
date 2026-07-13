import logging
import os
import subprocess
from datetime import datetime

MODEL_MAP = {
    "english": os.path.join(
        os.path.abspath(os.path.join(os.path.dirname(__file__), "..")),
        "voices",
        "en_US-lessac-medium.onnx",
    ),
    "indonesian": os.path.join(
        os.path.abspath(os.path.join(os.path.dirname(__file__), "..")),
        "voices",
        "id_ID-news_tts-medium.onnx",
    ),
}

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
RESULTS_DIR = os.path.join(BASE_DIR, "results")
os.makedirs(RESULTS_DIR, exist_ok=True)


def _output_path() -> str:
    now = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    return os.path.join(RESULTS_DIR, f"output_{now}.wav")


def tts_piper(
    text: str,
    lang: str = "indonesian",
    speed: int = 50,
) -> str | None:
    if not text or not text.strip():
        logging.warning("tts_piper: empty text")
        return None

    model = MODEL_MAP.get(lang, MODEL_MAP["indonesian"])

    speed = max(0, min(100, speed))
    length_scale = 1.5 - speed / 100

    path = _output_path()

    try:
        logging.info(
            f"Piper TTS — lang={lang} speed={speed} length_scale={length_scale:.2f}"
        )

        subprocess.run(
            [
                "piper",
                "--model", model,
                "--output_file", path,
                "--length_scale", str(length_scale),
            ],
            input=text,
            text=True,
            check=True,
        )

        logging.info(f"Piper TTS saved: {path}")
        return path

    except subprocess.CalledProcessError as e:
        logging.error(f"Piper TTS failed: {e}", exc_info=True)
        return None