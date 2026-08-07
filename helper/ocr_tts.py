import logging
import queue
import pigpio
import time
import threading

from helper.capture import capture_both
from helper.ocr     import run_ocr
from helper.speak   import speak
from helper.fan   import fan_on
from helper.led import led_off

logger = logging.getLogger(__name__)


def turn_on_fan(pi: pigpio.pi):
    fan_on(pi)


def ocr_tts_worker(
    ocr_queue:     queue.Queue,
    motor_queue:   queue.Queue,
    speaker_queue: queue.Queue,
    get_language,
    get_volume,
    get_tts_speed,
    pi: pigpio.pi,
    cancel_event: threading.Event,
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
            try:
                # motor_queue.put("forward")
                # fan_on(pi)
                # continue
                language = get_language()
                volume   = get_volume()
                speed   = get_tts_speed()
                speaker_queue.put("start_scan")
                logger.info(f"OCR/TTS sequence — lang={language}")

                # ── 1. Capture ───────────────────────────────────────────
                picam_path, usb_path, capture_index = capture_both(capture_index)
                led_off(pi)
                if not picam_path or not usb_path:
                    logger.error("Capture failed")
                    speaker_queue.put("capture_failed")
                    turn_on_fan(pi)
                    continue

                if cancel_event.is_set():
                    logger.info("OCR/TTS cancelled (SW1 off)")
                    continue

                # ── 2. OCR ───────────────────────────────────────────────
                text = (run_ocr(usb_path, language, 'webcam') + " " + run_ocr(picam_path, language, 'picam')).strip()

                if cancel_event.is_set():
                    logger.info("OCR/TTS cancelled (SW1 off)")
                    continue

                if not text:
                    logger.warning("OCR: empty result")
                    speaker_queue.put("ocr_empty")
                    if not cancel_event.is_set():
                        motor_queue.put("forward")
                    turn_on_fan(pi)
                    continue

                # ── 3. Speak ─────────────────────────────────────────────
                speak(text=text, lang=language, volume=volume, speaker_queue=speaker_queue, speed=speed)

                if cancel_event.is_set():
                    logger.info("OCR/TTS cancelled (SW1 off)")
                    continue

                # ── 4. Motor backward ────────────────────────────────────
                motor_queue.put("forward")
                turn_on_fan(pi)
            except Exception:
                logging.exception("ocr_tts_worker: unhandled error during scan sequence")
                speaker_queue.put("tts_failed")
                # motor_queue.put("forward")
                # turn_on_fan(pi)