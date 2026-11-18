import os
import sys
import json
import time
import queue
import logging
import threading
import subprocess

try:
    import psutil
except ImportError:
    psutil = None  # type: ignore

try:
    import websocket
except ImportError:
    websocket = None  # type: ignore

from queues import motor_queue
from helper.fan import fan_on
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


def load_dotenv_file() -> None:
    """Load key=value pairs from .env in project root without requiring python-dotenv."""
    env_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".env"))
    if not os.path.isfile(env_path):
        return
    try:
        with open(env_path, "r", encoding="utf-8") as f:
            for raw_line in f:
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k = k.strip()
                v = v.strip().strip("'").strip('"')
                if k and k not in os.environ:
                    os.environ[k] = v
    except Exception as e:
        logger.warning(f"Failed to read .env file: {e}")


load_dotenv_file()

BACKEND_WS_URL = os.getenv("BACKEND_WS_URL", "ws://localhost:3001/ws")
DEVICE_SERIAL = os.getenv("DEVICE_SERIAL", "SR-RPI4-001")
DEVICE_API_KEY = os.getenv("DEVICE_API_KEY", "")

_ws_client = None
_current_mode = "standby"
_current_page = 1
_preferred_lang: str | None = os.getenv("DEFAULT_LANG") or None


def get_preferred_lang() -> str | None:
    return _preferred_lang


def set_preferred_lang(lang: str | None) -> None:
    global _preferred_lang
    if lang is None:
        _preferred_lang = None
    elif lang in ("id", "en"):
        _preferred_lang = lang
        logger.info(f"Preferred OCR/TTS language set to: {_preferred_lang}")


def get_cpu_temp() -> float:
    try:
        with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
            return round(int(f.read().strip()) / 1000.0, 1)
    except Exception:
        return 45.0


def _get_cpu_and_ram() -> tuple[int, int]:
    if psutil is not None:
        try:
            return (
                round(psutil.cpu_percent(interval=None)),
                round(psutil.virtual_memory().percent),
            )
        except Exception:
            pass
    # Pure-Linux /proc fallback for Raspberry Pi if psutil is not installed
    cpu_load = 20
    ram_pct = 40
    try:
        load1, _, _ = os.getloadavg()
        cores = os.cpu_count() or 4
        cpu_load = max(0, min(100, round((load1 / cores) * 100)))
    except Exception:
        pass
    try:
        mem_total = 0
        mem_avail = 0
        with open("/proc/meminfo", "r") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    mem_total = int(line.split()[1])
                elif line.startswith("MemAvailable:"):
                    mem_avail = int(line.split()[1])
        if mem_total > 0:
            ram_pct = max(0, min(100, round(((mem_total - mem_avail) / mem_total) * 100)))
    except Exception:
        pass
    return cpu_load, ram_pct


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
            "speed": round(0.5 + (get_tts_speed() / 100.0), 2),
        }
        try:
            _ws_client.send(json.dumps(payload))
        except Exception as e:
            logger.warning(f"WS state send failed: {e}")


def _telemetry_loop() -> None:
    while True:
        if _ws_client and _ws_client.sock and _ws_client.sock.connected:
            speed_mult = 0.5 + (get_tts_speed() / 100.0)
            wpm = int(150 * speed_mult) if _current_mode == "reading" else 0
            cpu_load, ram_usage = _get_cpu_and_ram()
            payload = {
                "type": "telemetry",
                "cpuTemp": get_cpu_temp(),
                "cpuLoad": cpu_load,
                "ramUsage": ram_usage,
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

    elif cmd_type in ("tts_speed", "speed"):
        raw_val = float(cmd.get("value", 1.0))
        if raw_val <= 5.0:
            # Multiplier (e.g. 0.5 .. 1.5 from DeviceControls or SessionConfigModal)
            mult = raw_val
        else:
            # WPM (e.g. 150 WPM = 1.0x)
            mult = raw_val / 150.0
        pct = max(0, min(100, round((mult - 0.5) * 100)))
        set_encoder_speed(pct)
        send_state_update()

    elif cmd_type == "language":
        lang = str(cmd.get("value", "id")).lower()
        set_preferred_lang(lang)

    elif cmd_type == "flip":
        step = int(cmd.get("step", 1))
        if step < 1:
            logger.warning("Backward page flip is not supported by hardware; ignoring.")
            return
        stop_playback()
        for mod_name in ("main", "__main__"):
            mod = sys.modules.get(mod_name)
            if mod is not None and hasattr(mod, "_motor_running"):
                setattr(mod, "_motor_running", True)
        send_state_update(mode="flipping", page=max(1, _current_page + step))
        try:
            fan_on(pi)
            motor_queue.put("forward")
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
        from helper.limit_switch import read_limit_sw1
        from helper.led import led_on, led_off
        from helper.fan import fan_off
        from helper.motor import get_motor_direction
        from queues import ocr_queue

        if mode == "on":
            for mod_name in ("main", "__main__"):
                mod = sys.modules.get(mod_name)
                if mod is not None:
                    if hasattr(mod, "_motor_running"):
                        setattr(mod, "_motor_running", True)
                    if hasattr(mod, "_ready_to_start"):
                        setattr(mod, "_ready_to_start", False)
                    if hasattr(mod, "_resetting"):
                        setattr(mod, "_resetting", False)
                    if hasattr(mod, "_homing_purpose"):
                        setattr(mod, "_homing_purpose", None)
                    if hasattr(mod, "_cancel_scan"):
                        getattr(mod, "_cancel_scan").clear()
            if not read_limit_sw1(pi):
                send_state_update(mode="restarting")
                motor_queue.put("backward")
            else:
                send_state_update(mode="reading")
                motor_queue.put("stop")
                led_on(pi)
                ocr_queue.put("start")

        elif mode == "restart":
            is_ready_to_start = False
            is_resetting = False
            for mod_name in ("main", "__main__"):
                mod = sys.modules.get(mod_name)
                if mod is not None and hasattr(mod, "_ready_to_start"):
                    is_ready_to_start = bool(getattr(mod, "_ready_to_start"))
                    is_resetting = bool(getattr(mod, "_resetting", False))
                    break

            if is_ready_to_start:
                # 2nd click (same as physical BTN5 2nd click): start scan
                logger.info("BTN5 (Web): start scan")
                for mod_name in ("main", "__main__"):
                    mod = sys.modules.get(mod_name)
                    if mod is not None:
                        if hasattr(mod, "_ready_to_start"):
                            setattr(mod, "_ready_to_start", False)
                        if hasattr(mod, "_motor_running"):
                            setattr(mod, "_motor_running", True)
                        if hasattr(mod, "_cancel_scan"):
                            getattr(mod, "_cancel_scan").clear()
                motor_queue.put("stop")
                led_on(pi)
                ocr_queue.put("start")

            elif not is_resetting:
                # 1st click (same as physical BTN5 1st click): reset & home to LIMIT_SW1
                logger.info("BTN5 (Web): reset")
                stop_playback()
                fan_off(pi)
                led_off(pi)
                for mod_name in ("main", "__main__"):
                    mod = sys.modules.get(mod_name)
                    if mod is not None:
                        if hasattr(mod, "_cancel_scan"):
                            getattr(mod, "_cancel_scan").set()
                        if hasattr(mod, "_resetting"):
                            setattr(mod, "_resetting", True)
                speaker_queue.put("start_restart")
                if read_limit_sw1(pi):
                    logger.info("Reset complete (already at LIMIT_SW1)")
                    for mod_name in ("main", "__main__"):
                        mod = sys.modules.get(mod_name)
                        if mod is not None:
                            if hasattr(mod, "_ready_to_start"):
                                setattr(mod, "_ready_to_start", True)
                            if hasattr(mod, "_resetting"):
                                setattr(mod, "_resetting", False)
                            if hasattr(mod, "_motor_running"):
                                setattr(mod, "_motor_running", False)
                            if hasattr(mod, "set_page_seen"):
                                mod.set_page_seen(False)
                    motor_queue.put("stop")
                    speaker_queue.put("reset_success")
                    send_state_update(mode="standby", page=1)
                else:
                    send_state_update(mode="restarting", page=1)
                    if get_motor_direction() == "backward":
                        motor_queue.put("bounce")
                    motor_queue.put("backward")

        elif mode == "off":
            stop_playback()
            fan_off(pi)
            led_off(pi)
            for mod_name in ("main", "__main__"):
                mod = sys.modules.get(mod_name)
                if mod is not None:
                    if hasattr(mod, "_motor_running"):
                        setattr(mod, "_motor_running", False)
                    if hasattr(mod, "_ready_to_start"):
                        setattr(mod, "_ready_to_start", False)
                    if hasattr(mod, "_resetting"):
                        setattr(mod, "_resetting", False)
                    if hasattr(mod, "_cancel_scan"):
                        getattr(mod, "_cancel_scan").set()
                    if not read_limit_sw1(pi) and hasattr(mod, "_homing_purpose"):
                        setattr(mod, "_homing_purpose", "shutdown")
            if not read_limit_sw1(pi):
                send_state_update(mode="off")
                motor_queue.put("backward")
            else:
                motor_queue.put("stop")
                speaker_queue.put("shutdown")
                send_state_update(mode="off")


def start_cloud_client(pi, speaker_queue: queue.Queue) -> None:
    global _ws_client
    if websocket is None:
        logger.warning(
            "'websocket-client' package not installed — Cloud WebSocket disabled. "
            "Install on Raspberry Pi with: pip install websocket-client psutil"
        )
        return
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
