import logging
import queue
import pigpio
import time

from helper.capture import capture_both
from helper.ocr     import run_ocr
from helper.speak   import speak
from helper.fan   import fan_on
from helper.led import led_off

def turn_on_fan(pi: pigpio.pi):
    time.sleep(1)
    fan_on(pi) #worst case, can be disabled

def ocr_tts_worker(
    ocr_queue:     queue.Queue,
    motor_queue:   queue.Queue,
    speaker_queue: queue.Queue,
    get_language,
    get_volume,
    get_tts_speed,
    pi: pigpio.pi,
) -> None:
    """
    Permanent thread.
    Sequence on 'start':
      1. Capture image
      2. Run OCR
      3. Speak result via Edge TTS
      4. Motor backward
    """
    capture_index = 0

    while True:
        cmd = ocr_queue.get()

        if cmd == "quit":
            break

        if cmd == "start":
            # motor_queue.put("forward")
            # time.sleep(1)
            # fan_on(pi)
            # continue
            language = get_language()
            volume   = get_volume()
            speed   = get_tts_speed()
            speaker_queue.put("start_scan")
            logging.info(f"OCR/TTS sequence — lang={language}")

            # ── 1. Capture ───────────────────────────────────────────
            picam_path, usb_path, capture_index = capture_both(capture_index)
            led_off(pi)
            if not picam_path or not usb_path:
                logging.error("Capture failed")
                speaker_queue.put("capture_failed")
                turn_on_fan(pi)
                continue

            # ── 2. OCR ───────────────────────────────────────────────
            text = (run_ocr(usb_path, language, 'webcam') + " " + run_ocr(picam_path, language, 'picam')).strip()
            if not text:
                logging.warning("OCR: empty result")
                speaker_queue.put("ocr_empty")
                motor_queue.put("forward")
                turn_on_fan(pi)
                continue

            # ── 3. Speak ─────────────────────────────────────────────
            speak(text=text, lang=language, volume=volume, speaker_queue=speaker_queue, speed=speed)

            # ── 4. Motor backward ────────────────────────────────────
            motor_queue.put("forward")
            turn_on_fan(pi)
            # logging.info("OCR/TTS done → motor backward")