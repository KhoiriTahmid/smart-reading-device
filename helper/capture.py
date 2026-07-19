import logging
import os
import subprocess
import cv2
from picamera2 import Picamera2

BASE_DIR   = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
IMAGES_DIR = os.path.join(BASE_DIR, "images")
os.makedirs(IMAGES_DIR, exist_ok=True)

# Cache the resolved device index so we only probe once per process,
# not on every single capture call.
_usb_device_index: int | None = None


def _find_usb_camera_by_name(name_hint: str = "AF640") -> int | None:
    """
    Uses v4l2-ctl to list actual camera devices and match by name,
    instead of blindly opening every /dev/videoN index (which can
    hit the CSI camera's unicam node and break its pipeline).
    """
    try:
        result = subprocess.run(
            ["v4l2-ctl", "--list-devices"],
            capture_output=True, text=True, check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        logging.error(f"find_usb_camera: v4l2-ctl failed: {e}")
        return None

    lines = result.stdout.splitlines()
    current_name = None
    for line in lines:
        if line and not line.startswith("\t"):
            current_name = line.strip()
        elif line.strip().startswith("/dev/video") and current_name:
            if name_hint.lower() in current_name.lower():
                # Take the first video node listed under this device
                dev_path = line.strip()
                index = int(dev_path.replace("/dev/video", ""))
                logging.info(f"find_usb_camera: matched '{current_name}' -> {dev_path}")
                return index

    return None


def find_usb_camera(max_devices: int = 5) -> int:
    global _usb_device_index

    if _usb_device_index is not None:
        return _usb_device_index

    # Preferred: match by device name so we never touch the CSI camera
    index = _find_usb_camera_by_name("AF640")
    if index is not None:
        _usb_device_index = index
        return index

    # Fallback: probe, but explicitly request MJPG/a real resolution
    # and use CAP_V4L2 so we don't send a bad default format that
    # unicam chokes on. Still not bulletproof, but better than default.
    logging.warning("find_usb_camera: name match failed, falling back to probing")
    for device in range(max_devices):
        cap = cv2.VideoCapture(device, cv2.CAP_V4L2)
        if not cap.isOpened():
            cap.release()
            continue

        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

        ret, frame = cap.read()
        cap.release()

        if ret and frame is not None:
            _usb_device_index = device
            return device

    raise RuntimeError("No USB camera found")


def capture_picamera(index: int) -> tuple[str | None, int]:
    output_path = os.path.join(IMAGES_DIR, f"capture_{index}.jpg")
    try:
        logging.info(f"Capturing Pi Camera → capture_{index}.jpg")
        cam    = Picamera2()
        config = cam.create_still_configuration(
            main={"size": (1600, 1200)}   # turun dari 2592x1944 (5MP) ke ~2MP, cukup untuk OCR teks buku
        )
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
        cap = cv2.VideoCapture(device, cv2.CAP_V4L2)
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