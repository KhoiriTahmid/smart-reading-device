import logging
import queue

from helper.capture import capture_both
from helper.ocr     import run_ocr
from helper.speak   import speak


def ocr_tts_worker(
    ocr_queue:     queue.Queue,
    motor_queue:   queue.Queue,
    speaker_queue: queue.Queue,
    get_language,
    get_volume,
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
            language = get_language()
            volume   = get_volume()

            logging.info(f"OCR/TTS sequence — lang={language}")

            # ── 1. Capture ───────────────────────────────────────────
            picam_path, usb_path, capture_index = capture_both(capture_index)
            if not picam_path or not usb_path:
                logging.error("Capture failed")
                speaker_queue.put("stuck")
                motor_queue.put("forward")
                continue

            # ── 2. OCR ───────────────────────────────────────────────
            text = (run_ocr(picam_path, language, 'right') + " " + run_ocr(usb_path, language, 'left')).strip()
            if not text:
                logging.warning("OCR: empty result")
                # speaker_queue.put("stuck")
                print("stuck")
                motor_queue.put("forward")
                continue

            # ── 3. Speak ─────────────────────────────────────────────
            speak(text, lang=language, volume=volume)

            # ── 4. Motor backward ────────────────────────────────────
            motor_queue.put("forward")
            logging.info("OCR/TTS done → motor backward")