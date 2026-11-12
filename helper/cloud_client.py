import os
import json
import time
import queue
import logging
import threading
import subprocess
import psutil
import websocket

from helper.encoder import (
    get_volume,
    get_tts_speed,
    set_encoder_volume,
    set_encoder_speed,
)
from helper.speak import (
    speak,
    stop_playback,
    pause_playback,
    resume_playback,
    set_volume,
)

logger = logging.getLogger(__name__)

BACKEND_WS_URL = os.getenv("BACKEND_WS_URL", "ws://localhost:3001/ws")
DEVICE_SERIAL = os.getenv("DEVICE_SERIAL", "SR-RPI4-001")
DEVICE_API_KEY = os.getenv("DEVICE_API_KEY", "")

_ws_client: websocket.WebSocketApp | None = None
_current_mode = "standby"
_current_page = 1
_preferred_lang = os.getenv("DEFAULT_LANG", "id")


def get_preferred_lang() -> str:
    return _preferred_lang


def set_preferred_lang(lang: str) -> None:
    global _preferred_lang
    if lang in ("id", "en"):
        _preferred_lang = lang
        logger.info(f"Preferred OCR/TTS language set to: {_preferred_lang}")


def get_cpu_temp() -> float:
    try:
        with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
            return round(int(f.read().strip()) / 1000.0, 1)
    except Exception:
        return 45.0


def send_state_update(mode: str | None = None, page: int | None = None) -> None:
    global _current_mode, _current_page
    if mode is not None:
        _current_mode = mode
    if page is not None:
        _current_page = page

    if _ws_client and _ws_client.sock and _ws_client.sock.connected:
        payload = {
            "type": "state",
            "mode": _current_mode,
            "page": _current_page,
            "volume": get_volume(),
            "speed": round(0.5 + (get_tts_speed() / 100.0) * 1.5, 2),
        }
        try:
            _ws_client.send(json.dumps(payload))
        except Exception as e:
            logger.warning(f"WS state send failed: {e}")


def _telemetry_loop() -> None:
    while True:
        if _ws_client and _ws_client.sock and _ws_client.sock.connected:
            speed_mult = 0.5 + (get_tts_speed() / 100.0) * 1.5
            wpm = int(150 * speed_mult) if _current_mode == "reading" else 0
            payload = {
                "type": "telemetry",
                "cpuTemp": get_cpu_temp(),
                "cpuLoad": round(psutil.cpu_percent(interval=None)),
                "ramUsage": round(psutil.virtual_memory().percent),
                "wpm": wpm,
                "ts": int(time.time() * 1000),
            }
            try:
                _ws_client.send(json.dumps(payload))
            except Exception:
                pass
        time.sleep(3.0)


def _handle_command(cmd: dict, pi, speaker_queue: queue.Queue) -> None:
    cmd_type = cmd.get("type")
    logger.info(f"Received cloud command: {cmd}")

    if cmd_type == "volume":
        val = int(cmd.get("value", 80))
        set_encoder_volume(val)
        set_volume(val)
        send_state_update()

    elif cmd_type == "tts_speed":
        wpm = int(cmd.get("value", 150))
        pct = max(0, min(100, int(((wpm - 80) / 160.0) * 100)))
        set_encoder_speed(pct)
        send_state_update()

    elif cmd_type == "speed":
        # Direct multiplier from pre-session modal (e.g. 0.75, 1.0, 1.25, 1.5)
        mult = float(cmd.get("value", 1.0))
        pct = max(0, min(100, int(((mult - 0.5) / 1.5) * 100)))
        set_encoder_speed(pct)
        send_state_update()

    elif cmd_type == "language":
        lang = str(cmd.get("value", "id")).lower()
        set_preferred_lang(lang)

    elif cmd_type == "flip":
        step = int(cmd.get("step", 1))
        send_state_update(mode="flipping", page=max(1, _current_page + step))
        try:
            from helper.motor import flip_page
            threading.Thread(
                target=flip_page,
                args=(pi, speaker_queue),
                daemon=True,
            ).start()
        except Exception:
            logger.exception("Failed to trigger motor flip")

    elif cmd_type == "speech":
        action = cmd.get("action")
        if action == "pause":
            pause_playback()
            send_state_update(mode="paused")
        elif action == "resume":
            resume_playback()
            send_state_update(mode="reading")

    elif cmd_type == "play_text":
        text = cmd.get("text", "")
        if text:
            stop_playback()
            send_state_update(mode="reading")
            lang_name = "english" if _preferred_lang == "en" else "indonesian"
            threading.Thread(
                target=speak,
                kwargs={
                    "text": text,
                    "lang": lang_name,
                    "speaker_queue": speaker_queue,
                    "volume": get_volume(),
                    "speed": get_tts_speed(),
                },
                daemon=True,
            ).start()

    elif cmd_type == "power":
        mode = cmd.get("mode")
        if mode == "restart":
            send_state_update(mode="restarting")
            subprocess.Popen(["sudo", "reboot"])
        elif mode == "off":
            send_state_update(mode="off")
            subprocess.Popen(["sudo", "shutdown", "-h", "now"])


def start_cloud_client(pi, speaker_queue: queue.Queue) -> None:
    global _ws_client
    if not DEVICE_API_KEY:
        logger.warning("DEVICE_API_KEY not set — Cloud WebSocket client disabled")
        return

    ws_url = (
        f"{BACKEND_WS_URL}?role=device"
        f"&serial={DEVICE_SERIAL}&key={DEVICE_API_KEY}"
    )

    def on_open(ws):
        logger.info("Connected to Smart Reading Cloud WebSocket")
        send_state_update(mode="standby")

    def on_message(ws, message):
        try:
            data = json.loads(message)
            _handle_command(data, pi, speaker_queue)
        except Exception:
            logger.exception("Failed to handle WS message")

    def on_close(ws, status_code, msg):
        logger.warning(f"Cloud WS closed ({status_code}): {msg}")

    def ws_runner():
        global _ws_client
        while True:
            try:
                _ws_client = websocket.WebSocketApp(
                    ws_url,
                    on_open=on_open,
                    on_message=on_message,
                    on_close=on_close,
                )
                _ws_client.run_forever(ping_interval=20, ping_timeout=10)
            except Exception as e:
                logger.error(f"Cloud WS error: {e}")
            time.sleep(5)

    threading.Thread(target=ws_runner, daemon=True, name="cloud-ws").start()
    threading.Thread(
        target=_telemetry_loop, daemon=True, name="cloud-telemetry"
    ).start()
