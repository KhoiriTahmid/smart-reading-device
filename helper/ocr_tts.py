import os
import logging
import queue
import time
import threading
import pigpio
import cv2
import numpy as np
import requests
from PIL import Image

from helper.capture import capture_both
from helper.ocr import run_ocr
from helper.speak import speak, _play
from helper.fan import fan_on
from helper.led import led_off
from helper.cloud_client import (
    send_state_update,
    get_preferred_lang,
    load_dotenv_file,
)

logger = logging.getLogger(__name__)

load_dotenv_file()

BACKEND_HTTP_URL = os.getenv("BACKEND_HTTP_URL", "http://localhost:3001")
DEVICE_SERIAL = os.getenv("DEVICE_SERIAL", "SR-RPI4-001")
DEVICE_API_KEY = os.getenv("DEVICE_API_KEY", "")


def turn_on_fan(pi: pigpio.pi):
    fan_on(pi)


def prepare_pages_as_pdf(
    usb_path: str | None,
    picam_path: str | None,
    output_pdf_path: str = "/tmp/captured_pages.pdf",
) -> str | None:
    """
    Preprocess left page (usb_path / webcam) and right page (picam_path / PiCam)
    INDEPENDENTLY without horizontal stitching, then package them as a 2-page PDF
    (Page 1 = Left Page, Page 2 = Right Page) so OCR never bleeds across the book spine.
    """
    pil_pages: list[Image.Image] = []

    # Page 1: Left Camera (USB Webcam)
    if usb_path and os.path.exists(usb_path):
        img_left = cv2.imread(usb_path)
        if img_left is not None:
            img_left = cv2.rotate(img_left, cv2.ROTATE_90_COUNTERCLOCKWISE)
            h, w = img_left.shape[:2]
            top = int(h * 0.13)
            left = int(w * 0.25)
            right = int(w * 0.90)
            img_left = img_left[top:h, left:right]
            rgb_left = cv2.cvtColor(img_left, cv2.COLOR_BGR2RGB)
            pil_pages.append(Image.fromarray(rgb_left))

    # Page 2: Right Camera (PiCam)
    if picam_path and os.path.exists(picam_path):
        img_right = cv2.imread(picam_path)
        if img_right is not None:
            try:
                h, w = img_right.shape[:2]
                src_pts = np.float32(
                    [
                        [200, 0],
                        [w - 50, 100],
                        [w, h - 200],
                        [0, h - 320],
                    ]
                )
                dst_pts = np.float32(
                    [
                        [0, 0],
                        [w, 0],
                        [w, h],
                        [0, h],
                    ]
                )
                matrix = cv2.getPerspectiveTransform(src_pts, dst_pts)
                img_right = cv2.warpPerspective(img_right, matrix, (w, h))
                img_right = cv2.rotate(img_right, cv2.ROTATE_90_CLOCKWISE)
                h, w = img_right.shape[:2]
                img_right = img_right[0:h, 0 : int(w * 0.90)]
            except Exception:
                logger.warning("PiCam warp fallback to raw frame")
            rgb_right = cv2.cvtColor(img_right, cv2.COLOR_BGR2RGB)
            pil_pages.append(Image.fromarray(rgb_right))

    if not pil_pages:
        return None

    pil_pages[0].save(
        output_pdf_path,
        "PDF",
        resolution=150.0,
        save_all=True,
        append_images=pil_pages[1:],
    )
    return output_pdf_path


def process_via_cloud(
    pdf_path: str,
    lang: str,
    volume: int,
    speed: int,
    speaker_queue: queue.Queue,
    cancel_event: threading.Event,
) -> bool:
    """
    Upload 2-page PDF to NestJS backend (POST /reading-histories/device),
    poll job status until COMPLETED, then download and play each newly scanned page's
    audio sequentially (Left Page first, then Right Page).
    """
    if not DEVICE_API_KEY:
        return False

    headers = {
        "x-device-serial": DEVICE_SERIAL,
        "x-device-key": DEVICE_API_KEY,
    }
    lang_code = "en" if lang in ("english", "en") else "id"

    try:
        with open(pdf_path, "rb") as f:
            files = {"file": ("scan_pages.pdf", f, "application/pdf")}
            data = {
                "lang": lang_code,
                "voice": "female",
                "name": f"Scan {DEVICE_SERIAL}",
            }
            resp = requests.post(
                f"{BACKEND_HTTP_URL}/reading-histories/device",
                headers=headers,
                files=files,
                data=data,
                timeout=20,
            )
        resp.raise_for_status()
        raw_job = resp.json()
        job = raw_job.get("payload") if isinstance(raw_job.get("payload"), dict) else raw_job
        history_id = job.get("historyId")
        start_page = int(job.get("startPage", 1))
        if not history_id:
            return False

        logger.info(
            f"Uploaded 2-page PDF to cloud: historyId={history_id}, startPage={start_page}"
        )
        speaker_queue.put("start_tts")

        # Poll up to 90 seconds (45 * 2s)
        for _ in range(45):
            if cancel_event.is_set():
                return True
            time.sleep(2.0)

            poll_resp = requests.get(
                f"{BACKEND_HTTP_URL}/reading-histories/device/{history_id}",
                headers=headers,
                timeout=10,
            )
            poll_resp.raise_for_status()
            raw_status = poll_resp.json()
            status_data = (
                raw_status.get("payload")
                if isinstance(raw_status.get("payload"), dict)
                else raw_status
            )
            state = status_data.get("status")

            if state == "COMPLETED":
                pages = status_data.get("pages") or []
                new_pages = [
                    p for p in pages if int(p.get("pageNumber", 1)) >= start_page
                ]

                if new_pages:
                    for page in sorted(
                        new_pages, key=lambda p: int(p.get("pageNumber", 1))
                    ):
                        if cancel_event.is_set():
                            return True
                        page_num = page.get("pageNumber", 1)
                        page_audio_url = page.get("audioUrl")
                        page_text = (
                            page.get("ocrText") or page.get("text") or ""
                        ).strip()

                        send_state_update(mode="reading", page=int(page_num))

                        played_cloud_audio = False
                        if page_audio_url:
                            logger.info(
                                f"Playing cloud TTS audio for Page {page_num}"
                            )
                            audio_bin = requests.get(page_audio_url, timeout=20)
                            if audio_bin.ok and len(audio_bin.content) > 100:
                                url_path = page_audio_url.lower().split("?")[0]
                                ext = "wav" if url_path.endswith(".wav") else "mp3"
                                tmp_audio = f"/tmp/cloud_tts_p{page_num}.{ext}"
                                with open(tmp_audio, "wb") as af:
                                    af.write(audio_bin.content)
                                _play(tmp_audio, volume=volume)
                                played_cloud_audio = True

                        if not played_cloud_audio and page_text:
                            logger.info(
                                f"Cloud audio missing for Page {page_num}, speaking text locally"
                            )
                            speak(
                                text=page_text,
                                lang=lang,
                                volume=volume,
                                speaker_queue=speaker_queue,
                                speed=speed,
                            )
                    return True

                # Fallback if backend returned single audioUrl
                audio_url = status_data.get("audioUrl")
                extracted_text = status_data.get("extractedText", "")
                if audio_url:
                    audio_bin = requests.get(audio_url, timeout=20)
                    if audio_bin.ok and len(audio_bin.content) > 100:
                        url_path = audio_url.lower().split("?")[0]
                        ext = "wav" if url_path.endswith(".wav") else "mp3"
                        tmp_audio = f"/tmp/cloud_tts.{ext}"
                        with open(tmp_audio, "wb") as af:
                            af.write(audio_bin.content)
                        _play(tmp_audio, volume=volume)
                        return True
                if extracted_text:
                    speak(
                        text=extracted_text,
                        lang=lang,
                        volume=volume,
                        speaker_queue=speaker_queue,
                        speed=speed,
                    )
                    return True
                return False

            if state == "FAILED":
                logger.error(f"Cloud job failed: {status_data.get('errorMessage')}")
                return False

    except Exception as e:
        logger.warning(f"Cloud OCR/TTS unavailable, falling back to local: {e}")

    return False


def ocr_tts_worker(
    ocr_queue: queue.Queue,
    motor_queue: queue.Queue,
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
      1. Capture left (webcam) and right (picam) images
      2. Package as 2-page PDF (no horizontal stitching) and try Cloud OCR+TTS
      3. If Cloud unavailable, run local OCR+TTS sequentially: Left Page first, then Right Page
      4. Advance motor forward
    """
    capture_index = 0

    while True:
        cmd = ocr_queue.get()

        if cmd == "quit":
            break

        if cmd == "start":
            try:
                pref_lang = get_preferred_lang()
                if pref_lang == "en":
                    language = "english"
                elif pref_lang == "id":
                    language = "indonesian"
                else:
                    language = get_language()
                volume = get_volume()
                speed = get_tts_speed()
                speaker_queue.put("start_scan")
                send_state_update(mode="reading", page=capture_index + 1)
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

                # ── 2. Try Cloud OCR + TTS (2-Page PDF, no stitching) ────
                pdf_path = prepare_pages_as_pdf(usb_path, picam_path)
                cloud_ok = False
                if pdf_path:
                    cloud_ok = process_via_cloud(
                        pdf_path=pdf_path,
                        lang=language,
                        volume=volume,
                        speed=speed,
                        speaker_queue=speaker_queue,
                        cancel_event=cancel_event,
                    )

                # ── 3. Local Fallback (Left Page then Right Page) ────────
                if not cloud_ok and not cancel_event.is_set():
                    left_text = run_ocr(usb_path, language, "webcam").strip()
                    right_text = run_ocr(picam_path, language, "picam").strip()

                    if cancel_event.is_set():
                        logger.info("OCR/TTS cancelled (SW1 off)")
                        continue

                    if not left_text and not right_text:
                        logger.warning("OCR: empty result on both pages")
                        speaker_queue.put("ocr_empty")
                        if not cancel_event.is_set():
                            motor_queue.put("forward")
                        turn_on_fan(pi)
                        continue

                    if left_text and not cancel_event.is_set():
                        logger.info("Speaking Left Page (webcam)...")
                        speak(
                            text=left_text,
                            lang=language,
                            volume=volume,
                            speaker_queue=speaker_queue,
                            speed=speed,
                        )

                    if right_text and not cancel_event.is_set():
                        logger.info("Speaking Right Page (picam)...")
                        speak(
                            text=right_text,
                            lang=language,
                            volume=volume,
                            speaker_queue=speaker_queue,
                            speed=speed,
                        )

                if cancel_event.is_set():
                    logger.info("OCR/TTS cancelled (SW1 off)")
                    continue

                # ── 4. Advance motor & return to standby ─────────────────
                send_state_update(mode="standby", page=capture_index)
                motor_queue.put("forward")
                turn_on_fan(pi)
            except Exception:
                logging.exception(
                    "ocr_tts_worker: unhandled error during scan sequence"
                )
                speaker_queue.put("tts_failed")
