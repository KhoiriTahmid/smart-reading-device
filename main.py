#!/usr/bin/env python3
"""
Book Scanner Motor Controller — Raspberry Pi 4B
"""

import pigpio
import time
import threading

from queues import motor_queue, ocr_queue, speaker_queue

from helper.fan          import setup_fan, fan_off
from helper.led          import setup_led, led_on, led_off
from helper.motor        import setup_motor, motor_worker
from helper.switch       import setup_switches, read_sw1, read_sw2_language
from helper.button       import setup_buttons, read_btn1, read_btn2, read_btn3, read_btn4, read_btn5, read_btn6
from helper.limit_switch import setup_limit_switches, read_limit_sw1, read_limit_sw2
from helper.ultrasonic   import setup_ultrasonic, read_ultra1, read_ultra2
from helper.encoder      import setup_encoders, read_encoders, get_tts_speed
from helper.speaker      import setup_speaker, speaker_worker
from helper.ocr_tts      import ocr_tts_worker

# ── State ───────────────────────────────────────────────────────────────────
_language       = "indonesian"
_motor_running  = False

ULTRA1_SLOW_CM  = 20.0   # cm — slow motor
ULTRA1_STUCK_CM = 0.5    # cm — stuck threshold (distance not changing)
ULTRA2_BOOK_CM  = 10.0   # cm — book presence threshold
ULTRA1_INTERVAL = 0.1    # seconds between readings
STUCK_READINGS  = 10     # consecutive same readings = stuck


def get_language() -> str:
    return _language


# ── Ultrasonic workers ───────────────────────────────────────────────────────
def ultrasonic1_worker(pi: pigpio.pi) -> None:
    """Monitors page turn and stuck detection."""
    last_distances = []

    while True:
        distance = read_ultra1(pi)
        if distance is not None:
            # print(f"Ultra1: {distance:.1f}cm")

            # slow motor if close
            # if distance < ULTRA1_SLOW_CM:
            #     motor_queue.put("slow")

            # stuck detection — collect last N readings
            last_distances.append(round(distance, 1))
            if len(last_distances) > STUCK_READINGS:
                last_distances.pop(0)
                if len(set(last_distances)) == 1:  # all same = stuck
                    print("Ultra1: motor stuck detected")
                    motor_queue.put("stop")
                    speaker_queue.put("stuck")
                    last_distances.clear()

        time.sleep(ULTRA1_INTERVAL)


def ultrasonic2_worker(pi: pigpio.pi) -> None:
    """Monitors book presence."""
    while True:
        distance = read_ultra2(pi)
        if distance is not None and distance < ULTRA2_BOOK_CM:
            print(f"Ultra2: book detected at {distance:.1f}cm")
            speaker_queue.put("letakan_buku")
            time.sleep(3)  # cooldown before next trigger
        time.sleep(0.2)


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
        threading.Thread(target=motor_worker,       args=(pi, motor_queue),                                              daemon=True),
        threading.Thread(target=ultrasonic1_worker, args=(pi,),                                                          daemon=True),
        threading.Thread(target=ultrasonic2_worker, args=(pi,),                                                          daemon=True),
        threading.Thread(target=ocr_tts_worker,     args=(ocr_queue, motor_queue, speaker_queue, get_language, get_tts_speed), daemon=True),
        threading.Thread(target=speaker_worker,     args=(speaker_queue,),                                               daemon=True),
    ]
    for t in threads:
        t.start()
    print("All threads started")


def loop(pi: pigpio.pi) -> None:
    global _language, _motor_running

    sw1_last      = False
    sw2_last      = False
    limit1_last   = False
    limit2_last   = False

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
                motor_queue.put("stop")
                led_on(pi)
                ocr_queue.put("start")
        elif not sw1 and sw1_last and _motor_running:
            _motor_running = False
            motor_queue.put("stop")
            print("SW1: OFF — motor stopped")
        sw1_last = sw1

        # ── Language switch ───────────────────────────────────────────────
        _language = read_sw2_language(pi)
        if _language != sw2_last:
            print("Language:", _language)
        sw2_last = _language

        # ── Limit SW1: stop + OCR ─────────────────────────────────────────
        limit1 = read_limit_sw1(pi)
        if limit1 and not limit1_last and _motor_running:
            print("Limit SW1: pressed — stop + OCR")
            motor_queue.put("stop")
            led_on(pi)
            ocr_queue.put("start")
        limit1_last = limit1

        # ── Limit SW2: set backward ───────────────────────────────────────
        limit2 = read_limit_sw2(pi)
        if limit2 and not limit2_last and _motor_running:
            print("Limit SW2: pressed — going backward")
            motor_queue.put("backward")
        limit2_last = limit2

        # ── Buttons ───────────────────────────────────────────────────────
        # if read_btn1(pi):
        #     print("BTN1: restart")
        #     _motor_running = False
        #     motor_queue.put("stop")
        #     time.sleep(0.5)
        #     motor_queue.put("forward")
        #     time.sleep(1)
        #     motor_queue.put("backward")
        #     _motor_running = True

        if read_btn2(pi):
            speaker_queue.put("explain_onoff")

        if read_btn3(pi):
            speaker_queue.put("explain_lang")

        if read_btn6(pi):
            speaker_queue.put("explain_speed")

        if read_btn4(pi):
            speaker_queue.put("explain_volume")

        # if read_btn5(pi):
        #     motor_queue.put("forward")
        #     time.sleep(1)
        #     motor_queue.put("backward")

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
        print("\nShutting down...")
    finally:
        motor_queue.put("hard_stop")
        speaker_queue.put("quit")
        ocr_queue.put("quit")
        time.sleep(0.5)        # wait for hard_stop to execute
        fan_off(pi)            # explicitly turn fan off after motor stops
        led_off(pi)
        pi.write(26, 0)        # force FAN pin LOW directly as backup
        pi.stop()
        print("GPIO released. Bye.")


if __name__ == "__main__":
    main()