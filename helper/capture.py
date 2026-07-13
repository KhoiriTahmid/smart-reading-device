import logging
import os
import cv2
from picamera2 import Picamera2

BASE_DIR   = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
IMAGES_DIR = os.path.join(BASE_DIR, "images")
os.makedirs(IMAGES_DIR, exist_ok=True)

def find_usb_camera(max_devices=5) -> int:
    for device in range(max_devices):
        cap = cv2.VideoCapture(device)

        if not cap.isOpened():
            cap.release()
            continue

        ret, frame = cap.read()
        cap.release()

        if ret and frame is not None:
            return device

    raise RuntimeError("No USB camera found")


def capture_picamera(index: int) -> tuple[str | None, int]:
    output_path = os.path.join(IMAGES_DIR, f"capture_{index}.jpg")
    try:
        logging.info(f"Capturing Pi Camera → capture_{index}.jpg")
        cam    = Picamera2()
        config = cam.create_still_configuration()
        cam.configure(config)
        cam.start()
        cam.capture_file(output_path)
        cam.stop()
        cam.close()
        logging.info(f"Pi Camera done: {output_path}")
        return output_path, index + 1
    except Exception as e:
        logging.error(f"capture_picamera: {e}", exc_info=True)
        return None, index + 1


def capture_usb(index: int) -> tuple[str | None, int]:
    output_path = os.path.join(IMAGES_DIR, f"capture_{index}.jpg")
    try:
        logging.info(f"Capturing USB Camera → capture_{index}.jpg")
        device = find_usb_camera()
        cap = cv2.VideoCapture(device)
        if not cap.isOpened():
            logging.error(f"capture_usb: cannot open device {device}")
            return None, index + 1

        cap.set(cv2.CAP_PROP_FRAME_WIDTH,  1280)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
        cap.set(cv2.CAP_PROP_AUTOFOCUS,    0)
        cap.set(cv2.CAP_PROP_FOCUS, 300)

        for _ in range(12):
            cap.read()

        ret, frame = cap.read()
        cap.release()

        if not ret or frame is None:
            logging.error("capture_usb: failed to read frame")
            return None, index + 1

        cv2.imwrite(output_path, frame)
        logging.info(f"USB Camera done: {output_path}")
        return output_path, index + 1
    except Exception as e:
        logging.error(f"capture_usb: {e}", exc_info=True)
        return None, index + 1


def capture_both(index: int) -> tuple[str | None, str | None, int]:
    picam_path, index = capture_picamera(index)
    usb_path,   index = capture_usb(index)
    return picam_path, usb_path, index