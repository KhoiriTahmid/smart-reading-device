import logging
import queue
import subprocess

from helper.encoder import get_volume

SOUNDS = {
    "explain_lang":      "explain_language.mp3",
    "explain_volume":    "explain_volume.mp3", 
    "explain_onoff":     "explain_onoff.mp3", 
    "explain_speed":     "explain_speed.mp3",
    "explain_restart":   "explain_restart.mp3",
    "language_english":  "language_english.mp3",
    "language_indonesian": "language_indonesian.mp3",
    "page_failed":       "page_failed.mp3",
    "page_success":      "page_success.mp3",
    "place_book":        "place_book.mp3",
    "reset_success":     "reset_success.mp3",
    "shutdown":          "shutdown.mp3",
    "start_scan":        "start_scan.mp3",
    "start_tts":         "start_tts.mp3",
    "start_turn":        "start_turn.mp3",
    "start_restart":     "start_restart.mp3",
    "stuck":             "stuck.mp3",
    "capture_failed":    "capture_failed.mp3",
    "ocr_empty":         "ocr_empty.mp3",
    "tts_failed":        "tts_failed.mp3",
    "beep_up": "beep_up.wav",
    "beep_down": "beep_down.wav",
}

LANG_DIRS = {
    "indonesian": "id",
    "english":    "en",
}
DEFAULT_LANG_DIR = "id"

def setup_speaker() -> None:
    pass


def _play_sound(path: str, volume: int) -> None:
    ext   = path.rsplit(".", 1)[-1].lower()
    scale = int(volume / 100 * 32768)
    cmd = (
        ["mpg123", "-q", "--scale", str(scale), "-a", "default", path]
        if ext == "mp3" else
        ["aplay",  "-q", "-D", "default", path]
    )
    try:
        subprocess.run(cmd, check=True, timeout=10)
    except subprocess.TimeoutExpired:
        logging.error(f"speaker: playback timed out for {path}")
    except Exception as e:
        logging.error(f"speaker: playback failed: {e}")

def speaker_worker(speaker_queue: queue.Queue, get_language) -> None:
    while True:
        name = speaker_queue.get()
        if name == "quit":
            break

        filename = SOUNDS.get(name)
        if filename is None:
            logging.warning(f"speaker: unknown sound '{name}'")
            continue

        if name.startswith("beep_"):
            path = f"sounds/{filename}"
        else:
            lang_dir = LANG_DIRS.get(get_language(), DEFAULT_LANG_DIR)
            path = f"sounds/{lang_dir}/{filename}"

        volume = get_volume()
        logging.info(f"speaker: playing '{name}' lang={lang_dir} vol={volume}")
        _play_sound(path, volume)

def speaker_worker(speaker_queue: queue.Queue, get_language) -> None:
    while True:
        name = speaker_queue.get()
        if name == "quit":
            break
        
        filename = SOUNDS.get(name)
        if filename is None:
            logging.warning(f"speaker: unknown sound '{name}'")
            continue

        if name.startswith("beep_"):
            path = f"sounds/{filename}"
            lang_dir = "-"
        else:
            lang_dir = LANG_DIRS.get(get_language(), DEFAULT_LANG_DIR)
            path = f"sounds/{lang_dir}/{filename}"

        volume = get_volume()
        logging.info(f"speaker: playing '{name}' lang={lang_dir} vol={volume}")
        _play_sound(path, volume)