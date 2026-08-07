import os
import math
import time
import logging
import subprocess
import threading
import queue
from piper import PiperVoice
from helper.tts_edge          import tts_edge
from helper.tts_piper          import tts_piper
from helper.is_wifi_connected import is_wifi_connected

logger = logging.getLogger(__name__)

_play_lock    = threading.Lock()
_play_process: subprocess.Popen | None = None

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

MODEL_EN = os.path.join(BASE_DIR, "voices", "en_US-lessac-medium.onnx")
MODEL_ID = os.path.join(BASE_DIR, "voices", "id_ID-news_tts-medium.onnx")

PIPER_VOICES: dict[str, PiperVoice] = {}


def stop_playback() -> None:
    """Kill the current playback process, if any."""
    global _play_process
    with _play_lock:
        if _play_process and _play_process.poll() is None:
            _play_process.terminate()
            logger.info("Playback stopped")


ALSA_CARD = "2"
ALSA_CONTROL = "PCM"
ALSA_DEVICE = "plughw:CARD=Headphones,DEV=0"

PCM_MIN_DB = -30.0
PCM_MAX_DB = 4.0

_last_set_volume: int | None = None  # track last applied volume to avoid redundant amixer calls


def set_volume(volume: int):
    global _last_set_volume
    volume = max(0, min(100, volume))

    # Skip if unchanged — avoids spamming amixer with identical values
    if volume == _last_set_volume:
        return

    x = math.sqrt(volume / 100.0)
    db = PCM_MIN_DB + (PCM_MAX_DB - PCM_MIN_DB) * x

    try:
        subprocess.run([
            "amixer", "-c", ALSA_CARD, "-q", "sset", ALSA_CONTROL, "--", f"{db:.2f}dB"
        ], check=True, timeout=2)
        _last_set_volume = volume
    except subprocess.TimeoutExpired:
        logger.error("set_volume: amixer timed out")
    except Exception:
        logger.exception("set_volume: failed")


def _play(filepath: str, volume: int = 50, min_timeout: int = 15) -> None:
    global _play_process

    ext = filepath.rsplit(".", 1)[-1].lower()

    player_map = {
        "wav": ["aplay",  "-q", "-D", ALSA_DEVICE, filepath],
        "mp3": ["mpg123", "-q", "-o", "alsa", "-a", ALSA_DEVICE, filepath],
    }

    cmd = player_map.get(ext)
    if not cmd:
        logger.error(f"_play: unsupported extension '.{ext}'")
        return

    set_volume(volume)

    # Estimate playback duration from the actual audio file, so long
    # TTS clips don't get cut off by a fixed timeout.
    timeout = min_timeout
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", filepath],
            capture_output=True, text=True, timeout=5,
        )
        duration = float(result.stdout.strip())
        timeout = max(min_timeout, duration + 10)  # +10s buffer
    except Exception as e:
        logger.warning(f"_play: could not probe duration, using default timeout: {e}")

    try:
        with _play_lock:
            if _play_process is not None and _play_process.poll() is None:
                logger.warning("_play: killing stuck previous playback process")
                _play_process.kill()
                _play_process.wait(timeout=2)
            _play_process = subprocess.Popen(cmd)

        _play_process.wait(timeout=timeout)
        logger.info(f"Playback done: {filepath}")

    except subprocess.TimeoutExpired:
        logger.error(f"_play: playback timed out ({timeout:.0f}s) for {filepath}, killing")
        with _play_lock:
            if _play_process:
                _play_process.kill()
    except FileNotFoundError:
        player = cmd[0]
        pkg    = "alsa-utils" if player == "aplay" else "mpg123"
        logger.error(f"{player} not found — install: sudo apt install {pkg}")
    except Exception:
        logger.exception("Playback failed")
    finally:
        with _play_lock:
            _play_process = None


def _get_piper_voice(lang: str) -> PiperVoice | None:
    """Lazy-load Piper voice only when actually needed."""
    if lang not in PIPER_VOICES:
        model_path = MODEL_EN if lang == "english" else MODEL_ID
        logger.info(f"Loading Piper voice for '{lang}' (first use)...")
        try:
            PIPER_VOICES[lang] = PiperVoice.load(model_path)
        except Exception:
            logger.exception(f"Failed to load Piper voice for '{lang}'")
            return None
    return PIPER_VOICES[lang]


def speak(*, text: str, lang: str, speaker_queue: queue.Queue, volume: int = 80, speed: int = 50) -> str | None:
    if not text or not text.strip():
        logger.warning("speak: empty text")
        return None

    speaker_queue.put("start_tts")

    filepath = None

    # ── Try Edge TTS first if WiFi is available ─────────────────────
    if is_wifi_connected():
        logger.info("speak: WiFi available → trying Edge TTS")
        filepath = tts_edge(text, lang, speed)
        if filepath is None:
            logger.warning("speak: Edge TTS failed → falling back to Piper")
    else:
        logger.info("speak: No WiFi → Piper (offline)")

    # ── Fallback to Piper if Edge TTS unavailable or failed ─────────
    if filepath is None:
        piper_voice = _get_piper_voice(lang)
        if piper_voice is None:
            logger.error(f"speak: no Piper voice available for lang='{lang}', giving up")
            return None
        filepath = tts_piper(text, lang, speed)

    if filepath:
        logger.info(f"filepath tts:{filepath}")
        _play(filepath, volume=volume)
    else:
        logger.error("gagal tts — both Edge and Piper failed")
        speaker_queue.put("tts_failed")

    return filepath


def volume_watcher(get_volume, interval: float = 0.2) -> None:
    last_volume = None
    while True:
        volume = get_volume()
        if volume != last_volume:
            set_volume(volume)
            last_volume = volume
        time.sleep(interval)