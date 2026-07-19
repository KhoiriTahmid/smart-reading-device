#!/usr/bin/env python3
"""
Book Scanner Motor Controller — Raspberry Pi 4B
"""

import threading
import time

import pigpio

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
_language = "indonesian"
_motor_running = False
_page_seen = False
_page_lock = threading.Lock()
_resetting = False
_ready_to_start = False

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
            print(f"page detected {distance}")
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
    print("System ready")


def start_threads(pi: pigpio.pi) -> None:
    threads = [
        threading.Thread(target=motor_worker, args=(pi, motor_queue), daemon=True),
        threading.Thread(target=ultrasonic1_worker, args=(pi,), daemon=True),
        # threading.Thread(target=ultrasonic2_worker, args=(pi,), daemon=True),
        threading.Thread(
            target=ocr_tts_worker,
            args=(ocr_queue, motor_queue, speaker_queue, get_language, get_volume, get_tts_speed, pi),
            daemon=True,
        ),
        threading.Thread(target=speaker_worker, args=(speaker_queue, get_language), daemon=True),
        threading.Thread(target=volume_watcher, args=(get_volume,), daemon=True),
    ]
    for t in threads:
        t.start()
    print("All threads started")


def loop(pi: pigpio.pi) -> None:
    global _language, _motor_running, _resetting, _ready_to_start

    sw1_last = False
    sw2_last = False
    limit1_last = False
    limit2_last = False

    while True:
        # ── SW1: on/off ──────────────────────────────────────────────────
        sw1 = read_sw1(pi)
        if sw1 and not sw1_last:
            _motor_running = True
            print("SW1: ON")
            # check limit SW1 — if not pressed, go backward to find home
            if not read_limit_sw1(pi):
                print("Homing: moving backward to limit SW1")
                motor_queue.put("backward")
            else:
                _motor_running = False
                run_ocr_tts(pi)
                
        elif not sw1 and sw1_last and _motor_running:
            _motor_running = False
            speaker_queue.put("shutdown")
            motor_queue.put("stop")
            print("SW1: OFF — motor stopped")
        sw1_last = sw1

        # ── Language switch ───────────────────────────────────────────────
        _language = read_sw2_language(pi)
        if _language != sw2_last:
            print("Language:", _language)
            speaker_queue.put(f"language_{_language}")
        sw2_last = _language

        # ── Limit SW1: stop + OCR ─────────────────────────────────────────
        limit1 = read_limit_sw1(pi)
        if limit1 and not limit1_last:
            if _resetting:
                print("Reset complete")
                _ready_to_start = True
                _resetting = False
                _motor_running = False
                motor_queue.put("stop")
                speaker_queue.put("reset_success")
                set_page_seen(False)

            elif _motor_running and get_motor_direction() == "backward":
                print("Limit SW1: pressed — stop + OCR")
                run_ocr_tts(pi)
        limit1_last = limit1

        # ── Limit SW2: set backward ───────────────────────────────────────
        limit2 = read_limit_sw2(pi)
        if limit2 and not limit2_last:
            print(f"DEBUG: {_motor_running} {get_motor_direction()}")
        if limit2 and not limit2_last and _motor_running and get_motor_direction() == "forward":
            if get_page_seen():
                print("Page flip: SUCCESS")
                speaker_queue.put("page_success")
            else:
                print("Page flip: FAILED")
                speaker_queue.put("page_failed")

            set_page_seen(False)
            print("Limit SW2: pressed — going backward")
            motor_queue.put("backward")
        limit2_last = limit2

        # ── Buttons ───────────────────────────────────────────────────────
        if read_btn1(pi):
            print("BTN1: explain on/off")
            speaker_queue.put("explain_onoff")

        if read_btn2(pi):
            print("BTN2: explain restart")
            speaker_queue.put("explain_restart")

        if read_btn3(pi):
            print("BTN3: explain language")
            speaker_queue.put("explain_lang")

        if read_btn6(pi):
            print("BTN6: explain speed")
            speaker_queue.put("explain_speed")

        if read_btn4(pi):
            print("BTN4: explain volume")
            speaker_queue.put("explain_volume")

        if read_btn5(pi):
            if _ready_to_start:
                # klik ke-2: mulai scan (sama kayak SW1 pas limit1 udah kepencet)
                print("BTN5: start scan")
                _ready_to_start = False
                run_ocr_tts(pi)
                _motor_running = True

            elif not _resetting:
                print("BTN5: reset")
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
        speaker_queue.put("place_book")
        start_threads(pi)
        loop(pi)
    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        motor_queue.put("hard_stop")
        speaker_queue.put("quit")
        ocr_queue.put("quit")
        time.sleep(0.5)   # wait for hard_stop to execute
        fan_off(pi)       # explicitly turn fan off after motor stops
        led_off(pi)
        pi.write(26, 0)   # force FAN pin LOW directly as backup
        pi.stop()
        print("GPIO released. Bye.")


if __name__ == "__main__":
    main()