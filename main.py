#!/usr/bin/env python3
"""
Book Scanner Motor Controller — Raspberry Pi 4B
"""

import threading
import time

import pigpio

import logging
import os
from logging.handlers import RotatingFileHandler

from queues import motor_queue, ocr_queue, speaker_queue

from helper.button import (
    setup_buttons,
    read_btn1,
    read_btn2,
    read_btn3,
    read_btn4,
    read_btn5,
    read_btn6,
)
from helper.encoder import setup_encoders, read_encoders, get_tts_speed, get_volume
from helper.fan import setup_fan, fan_off
from helper.led import setup_led, led_on, led_off
from helper.limit_switch import setup_limit_switches, read_limit_sw1, read_limit_sw2
from helper.motor import setup_motor, motor_worker, get_motor_direction
from helper.ocr_tts import ocr_tts_worker
from helper.speak import volume_watcher
from helper.speaker import setup_speaker, speaker_worker
from helper.switch import setup_switches, read_sw1, read_sw2_language
from helper.ultrasonic import setup_ultrasonic, read_ultra1

# ── State ─────────────────────────────────────────────────────────────────
LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILE = os.path.join(LOG_DIR, "reader.log")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(threadName)s] %(name)s: %(levelname)s: %(message)s",
    handlers=[
        RotatingFileHandler(
            LOG_FILE,
            maxBytes=5 * 1024 * 1024,   # 5 MB per file
            backupCount=3,              # keep 3 old files: reader.log.1, .2, .3
        ),
        logging.StreamHandler(),        # still prints to console too
    ],
)

logger = logging.getLogger(__name__)

# ── State ─────────────────────────────────────────────────────────────────
_language = "indonesian"
_motor_running = False
_page_seen = False
_page_lock = threading.Lock()
_resetting = False
_ready_to_start = False
_homing_purpose = None   # None | "startup" | "shutdown"
_cancel_scan = threading.Event()


# ── Ultrasonic 1 (page detection) ───────────────────────────────────────────
ULTRA1_INTERVAL = 0.1     # seconds between readings
PAGE_DETECTED_CM = 15     # adjust to your sensor

# ── Ultrasonic 2 (book presence / stuck detection / slowdown) ──────────────
ULTRA2_STUCK_TIME = 4.0          # seconds with no movement before flagging stuck
ULTRA2_STUCK_TOLERANCE = 1.0     # cm — movement below this counts as "no progress"
ULTRA2_SLOW_CM = 47.0             # cm — object close while moving forward → slow down (tune this)
ULTRA2_INTERVAL = 0.1            # seconds between readings


def get_language() -> str:
    return _language


def set_page_seen(value: bool) -> None:
    global _page_seen
    with _page_lock:
        _page_seen = value


def get_page_seen() -> bool:
    with _page_lock:
        return _page_seen


def ultrasonic1_worker(pi: pigpio.pi) -> None:
    while True:
        distance = read_ultra1(pi)

        if (
            distance is not None
            and get_motor_direction() == "forward"
            and distance < PAGE_DETECTED_CM
        ):
            logger.info(f"page detected {distance}")
            set_page_seen(True)
            fan_off(pi)

        time.sleep(ULTRA1_INTERVAL)


# def ultrasonic2_worker(pi: pigpio.pi) -> None:
#     """
#     Monitors book presence, stuck detection, and slows the motor
#     when approaching an obstacle while moving forward.

#     read_ultra2() is assumed to already return a filtered distance.
#     """
#     last_slow_trigger = 0.0

#     # Stuck detector
#     reference_distance = None
#     no_progress_since = None
#     stuck_reported = False
#     last_stuck_distance = None
#     retrying = False

#     while True:
#         distance = read_ultra2(pi)
#         continue

#         if distance is None:
#             time.sleep(ULTRA2_INTERVAL)
#             continue

#         now = time.time()
#         direction = get_motor_direction()

#         if direction in ("forward", "backward"):
#             if reference_distance is None:
#                 reference_distance = distance
#                 no_progress_since = now
#                 stuck_reported = False

#             else:
#                 movement = abs(distance - reference_distance)

#                 if movement >= ULTRA2_STUCK_TOLERANCE:
#                     # Significant movement detected
#                     reference_distance = distance
#                     no_progress_since = now
#                     stuck_reported = False
#                     retrying = False

#                 else:
#                     elapsed = now - no_progress_since

#                     if elapsed >= ULTRA2_STUCK_TIME and not stuck_reported:
#                         if retrying:
#                             movement = abs(distance - last_stuck_distance)

#                             if movement < ULTRA2_STUCK_TOLERANCE:
#                                 print("Still stuck after bounce")

#                                 motor_queue.put("stop")
#                                 speaker_queue.put("stuck")
#                                 stuck_reported = True
#                                 global _resetting
#                                 _resetting = False

#                             else:
#                                 print("Bounce succeeded")

#                                 retrying = False
#                                 reference_distance = distance
#                                 no_progress_since = now

#                         else:
#                             print("First stuck -> bouncing")

#                             last_stuck_distance = reference_distance
#                             retrying = True

#                             motor_queue.put("bounce")

#                             reference_distance = distance
#                             no_progress_since = now

#         else:
#             # Reset whenever motor isn't moving
#             reference_distance = None
#             no_progress_since = None
#             stuck_reported = False

#         # --------------------------------------------------------------
#         # SLOW DOWN
#         # --------------------------------------------------------------
#         if (
#             direction == "forward"
#             and (ULTRA2_SLOW_CM - 1) <= distance < ULTRA2_SLOW_CM
#             and (now - last_slow_trigger) > 1.0
#         ):
#             print(f"Ultra2: {distance:.1f} cm -> slow")
#             motor_queue.put("slow")
#             last_slow_trigger = now

#         time.sleep(ULTRA2_INTERVAL)

def run_ocr_tts(pi: pigpio.pi):
    _cancel_scan.clear()
    motor_queue.put("stop")
    led_on(pi)
    ocr_queue.put("start")

# ── Setup & Loop ─────────────────────────────────────────────────────────────
def setup(pi: pigpio.pi) -> None:
    setup_fan(pi)
    setup_motor(pi)
    setup_switches(pi)
    setup_buttons(pi)
    setup_limit_switches(pi)
    setup_ultrasonic(pi)
    setup_encoders(pi)
    setup_speaker()
    setup_led(pi)
    logger.info("System ready")


def start_threads(pi: pigpio.pi) -> None:
    threads = [
        threading.Thread(target=motor_worker, args=(pi, motor_queue), name="motor_worker", daemon=True),
        threading.Thread(target=ultrasonic1_worker, args=(pi,), name="ultrasonic1_worker", daemon=True),
        threading.Thread(
            target=ocr_tts_worker,
            args=(ocr_queue, motor_queue, speaker_queue, get_language, get_volume, get_tts_speed, pi, _cancel_scan),
            name="ocr_tts_worker", daemon=True,
        ),
        threading.Thread(target=speaker_worker, args=(speaker_queue, get_language), name="speaker_worker", daemon=True),
        threading.Thread(target=volume_watcher, args=(get_volume,), name="volume_watcher", daemon=True),
    ]
    for t in threads:
        t.start()
    logger.info("All threads started")


def loop(pi: pigpio.pi) -> None:
    global _language, _motor_running, _resetting, _ready_to_start, _homing_purpose

    sw1_last = False
    sw2_last = False
    limit1_last = False
    limit2_last = False

    # ── Startup: kalau SW1 OFF saat pertama kali run, homing dulu ──────
    sw1_initial = read_sw1(pi)
    if not sw1_initial:
        if not read_limit_sw1(pi):
            logger.info("Startup: SW1 OFF — homing to limit SW1")
            _homing_purpose = "startup"
            motor_queue.put("backward")
        else:
            logger.info("Startup: SW1 OFF — already at home")
            speaker_queue.put("place_book")
    sw1_last = sw1_initial

    while True:
        # ── SW1: on/off ──────────────────────────────────────────────────
        sw1 = read_sw1(pi)
        if sw1 and not sw1_last:
            _motor_running = True
            logger.info("SW1: ON")
            if not read_limit_sw1(pi):
                logger.info("Homing: moving backward to limit SW1")
                motor_queue.put("backward")
            else:
                run_ocr_tts(pi)
                _motor_running = True

        elif not sw1 and sw1_last and _motor_running:
            _motor_running = False
            _cancel_scan.set()
            logger.info("SW1: OFF — homing before shutdown")
            if not read_limit_sw1(pi):
                _homing_purpose = "shutdown"
                motor_queue.put("backward")
            else:
                motor_queue.put("stop")
                speaker_queue.put("shutdown")
        sw1_last = sw1

        # ── Language switch ───────────────────────────────────────────────
        _language = read_sw2_language(pi)
        if _language != sw2_last:
            logger.info(f"Language: {_language}")
            speaker_queue.put(f"language_{_language}")
        sw2_last = _language

        # ── Limit SW1: stop + OCR ─────────────────────────────────────────
        limit1 = read_limit_sw1(pi)
        if limit1 and not limit1_last:
            if _homing_purpose == "startup":
                logger.info("Startup homing complete")
                _homing_purpose = None
                motor_queue.put("stop")
                speaker_queue.put("place_book")

            elif _homing_purpose == "shutdown":
                logger.info("Shutdown homing complete")
                _homing_purpose = None
                motor_queue.put("stop")
                speaker_queue.put("shutdown")

            elif _resetting:
                logger.info("Reset complete")
                _ready_to_start = True
                _resetting = False
                _motor_running = False
                motor_queue.put("stop")
                speaker_queue.put("reset_success")
                set_page_seen(False)

            elif _motor_running and get_motor_direction() == "backward":
                logger.info("Limit SW1: pressed — stop + OCR")
                run_ocr_tts(pi)
        limit1_last = limit1

        # ── Limit SW2: set backward ───────────────────────────────────────
        limit2 = read_limit_sw2(pi)
        if limit2 and not limit2_last:
            logger.debug(f"{_motor_running} {get_motor_direction()}")
        if limit2 and not limit2_last and _motor_running and get_motor_direction() == "forward":
            if get_page_seen():
                logger.info("Page flip: SUCCESS")
                speaker_queue.put("page_success")
            else:
                logger.info("Page flip: FAILED")
                speaker_queue.put("page_failed")

            set_page_seen(False)
            logger.info("Limit SW2: pressed — going backward")
            motor_queue.put("backward")
        limit2_last = limit2

        # ── Buttons ───────────────────────────────────────────────────────
        if read_btn1(pi):
            logger.info("BTN1: explain on/off")
            speaker_queue.put("explain_onoff")

        if read_btn2(pi):
            logger.info("BTN2: explain restart")
            speaker_queue.put("explain_restart")

        if read_btn3(pi):
            logger.info("BTN3: explain language")
            speaker_queue.put("explain_lang")

        if read_btn6(pi):
            logger.info("BTN6: explain speed")
            speaker_queue.put("explain_speed")

        if read_btn4(pi):
            logger.info("BTN4: explain volume")
            speaker_queue.put("explain_volume")

        if read_btn5(pi):
            if _ready_to_start:
                # klik ke-2: mulai scan (sama kayak SW1 pas limit1 udah kepencet)
                logger.info("BTN5: start scan")
                _ready_to_start = False
                run_ocr_tts(pi)
                _motor_running = True

            elif not _resetting:
                logger.info("BTN5: reset")
                speaker_queue.put("start_restart")
                _resetting = True

                if get_motor_direction() == "backward":
                    motor_queue.put("bounce")

                motor_queue.put("backward")

        # ── Encoders ──────────────────────────────────────────────────────
        read_encoders(pi)

        time.sleep(0.01)


def main() -> None:
    pi = pigpio.pi()
    if not pi.connected:
        raise RuntimeError("Cannot connect to pigpiod. Run: sudo systemctl start pigpiod")

    try:
        setup(pi)
        start_threads(pi)
        loop(pi)
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    finally:
        motor_queue.put("hard_stop")
        speaker_queue.put("quit")
        ocr_queue.put("quit")
        time.sleep(0.5)   # wait for hard_stop to execute
        fan_off(pi)       # explicitly turn fan off after motor stops
        led_off(pi)
        pi.write(26, 0)   # force FAN pin LOW directly as backup
        pi.stop()
        logger.info("GPIO released. Bye.")


if __name__ == "__main__":
    main()