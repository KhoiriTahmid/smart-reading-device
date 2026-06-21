import logging
import queue
import subprocess

from helper.encoder import get_volume

SOUNDS = {
    "letakan_buku":  "sounds/letakan_buku.mp3",
    "stuck":         "sounds/motor_stuck.mp3",
    "explain_onoff": "sounds/explain_onoff.mp3",
    "explain_lang":  "sounds/explain_language.mp3",
    "explain_volume":"sounds/explain_volume.mp3",
    "explain_speed": "sounds/explain_speed.mp3",
}


def setup_speaker() -> None:
    pass


def _play_sound(path: str, volume: int) -> None:
    ext   = path.rsplit(".", 1)[-1].lower()
    scale = int(volume / 100 * 32768)
    cmd   = (
        ["mpg123", "-q", "--scale", str(scale), "-a", "plughw:2,0", path]
        if ext == "mp3" else
        ["aplay",  "-q", "-D", "plughw:2,0", path]
    )
    try:
        subprocess.run(cmd, check=True)
    except Exception as e:
        logging.error(f"speaker: playback failed: {e}")


def speaker_worker(speaker_queue: queue.Queue) -> None:
    while True:
        name = speaker_queue.get()
        if name == "quit":
            break
        path = SOUNDS.get(name)
        if path is None:
            logging.warning(f"speaker: unknown sound '{name}'")
            continue
        volume = get_volume()
        logging.info(f"speaker: playing '{name}' vol={volume}")
        # _play_sound(path, volume)