import os
import logging
import subprocess
import threading
from piper import PiperVoice
from helper.tts_edge          import tts_edge
from helper.tts_piper          import tts_piper
from helper.is_wifi_connected import is_wifi_connected

_play_lock    = threading.Lock()
_play_process: subprocess.Popen | None = None

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

MODEL_EN = os.path.join(BASE_DIR, "voices", "en_US-lessac-medium.onnx")
MODEL_ID = os.path.join(BASE_DIR, "voices", "id_ID-news_tts-medium.onnx")

PIPER_VOICES: dict[str, PiperVoice] = {}
PIPER_VOICES["english"] = PiperVoice.load(MODEL_EN)
PIPER_VOICES["indonesian"] = PiperVoice.load(MODEL_ID)

def stop_playback() -> None:
    """Kill the current playback process, if any."""
    global _play_process
    with _play_lock:
        if _play_process and _play_process.poll() is None:
            _play_process.terminate()
            logging.info("Playback stopped")


def set_volume(volume: int) -> None:
    """Change system volume mid-playback via amixer (0–100)."""
    volume = max(0, min(100, volume))
    try:
        subprocess.run(
            ["amixer", "-q", "sset", "Master", f"{volume}%"],
            check=True
        )
        logging.info(f"Volume set to {volume}%")
    except FileNotFoundError:
        logging.error("amixer not found — install: sudo apt install alsa-utils")
    except subprocess.CalledProcessError as e:
        logging.error(f"amixer failed: {e}", exc_info=True)


def _play(filepath: str, volume: int = 50) -> None:
    global _play_process

    ext = filepath.rsplit(".", 1)[-1].lower()

    player_map = {
        "wav": ["aplay",  "-q", "-D", "plughw:2,0", filepath],
        "mp3": ["mpg123", "-q", "-a", "plughw:2,0", filepath],
    }

    cmd = player_map.get(ext)
    if not cmd:
        logging.error(f"_play: unsupported extension '.{ext}'")
        return

    # Set initial volume before playback
    set_volume(volume)

    try:
        with _play_lock:
            _play_process = subprocess.Popen(cmd)

        _play_process.wait()  # block until done, but process is now interruptible
        logging.info(f"Playback done: {filepath}")

    except FileNotFoundError:
        player = cmd[0]
        pkg    = "alsa-utils" if player == "aplay" else "mpg123"
        logging.error(f"{player} not found — install: sudo apt install {pkg}")
    except Exception as e:
        logging.error(f"Playback failed: {e}", exc_info=True)
    finally:
        with _play_lock:
            _play_process = None


def speak(text: str, lang: str, volume: int = 50, speed: int = 50) -> str | None:
    """Synthesize via Edge TTS (online) and play. Returns filepath or None."""
    if not text or not text.strip():
        logging.warning("speak: empty text")
        return None

    if is_wifi_connected():
        logging.info("speak: WiFi available → Edge TTS")
        filepath = tts_edge(text, lang=lang, speed=speed)
    else:
        logging.info("speak: No WiFi → Piper (offline)")
        piper_voice = PIPER_VOICES.get(lang)
        if piper_voice is None:
            logging.error(f"speak: no Piper voice loaded for lang='{lang}'")
            return None
        filepath = tts_piper(text, lang, speed)

    if filepath:
        print(f"filepath tts:{filepath}")
        _play(filepath, volume=volume)

    return filepath