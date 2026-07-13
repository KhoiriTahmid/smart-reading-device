import logging
import os
import cv2
import numpy as np
import pytesseract
from pytesseract import Output


def run_ocr(
    image_path: str,
    lang: str,
    camera: str | None = None,
    debug_dir: str = "debug",
) -> str:
    """Run OCR pipeline.

    Args:
        image_path: Path to image.
        lang: 'english' or 'ind'.
        camera: 'picam', 'webcam', or None.
        debug_dir: Directory to save cleaned images.
    """
    try:
        tess_lang = "eng" if lang == "english" else "ind"

        img = cv2.imread(image_path)
        if img is None:
            raise FileNotFoundError(f"Image not found: {image_path}")

        # ==========================================
        # Perspective correction (PiCam only)
        # ==========================================
        if camera == "picam":
            h, w = img.shape[:2]

            src_pts = np.float32([
                [200, 0],          # top-left
                [w - 50, 100],     # top-right
                [w, h - 200],      # bottom-right
                [0, h - 320],      # bottom-left
            ])

            dst_pts = np.float32([
                [0, 0],
                [w, 0],
                [w, h],
                [0, h],
            ])

            matrix = cv2.getPerspectiveTransform(src_pts, dst_pts)
            img = cv2.warpPerspective(img, matrix, (w, h))

        # ==========================================
        # Camera-specific rotation (same as before)
        # ==========================================
        if camera == "picam":
            # old rotate="right"
            img = cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE)

        elif camera == "webcam":
            # old rotate="left"
            img = cv2.rotate(img, cv2.ROTATE_90_COUNTERCLOCKWISE)

        # ==========================================
        # OCR preprocessing
        # ==========================================
        h, w = img.shape[:2]
        cropped = img[0:h, 0:int(w * 0.90)]

        gray = cv2.cvtColor(cropped, cv2.COLOR_BGR2GRAY)

        clahe = cv2.createCLAHE(
            clipLimit=2.0,
            tileGridSize=(8, 8)
        )
        gray = clahe.apply(gray)

        gray = cv2.GaussianBlur(gray, (3, 3), 0)

        ocr_img = cv2.adaptiveThreshold(
            gray,
            255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY,
            31,
            15,
        )

        # ==========================================
        # Save cleaned image
        # ==========================================
        os.makedirs(debug_dir, exist_ok=True)

        base_name = os.path.splitext(os.path.basename(image_path))[0]
        camera_tag = f"_{camera}" if camera else ""

        debug_path = os.path.join(
            debug_dir,
            f"{base_name}{camera_tag}_cleaned.png"
        )

        cv2.imwrite(debug_path, ocr_img)
        logging.info(f"Cleaned image saved → {debug_path}")

        # ==========================================
        # OCR
        # ==========================================
        data = pytesseract.image_to_data(
            ocr_img,
            lang=tess_lang,
            config="--oem 3 --psm 3",
            output_type=Output.DICT,
        )

        filtered_words = []
        text = " ".join(data["text"])

        print(f"\n{'─'*40}")
        print(f"Raw OCR Text  : {text or '(empty)'}")

        for i in range(len(data["text"])):
            word = data["text"][i].strip()
            if not word:
                continue

            try:
                conf = float(data["conf"][i])
            except (ValueError, TypeError):
                continue

            if conf >= 60:
                filtered_words.append(word)

        result = " ".join(filtered_words)


        result = result.replace("- ","")
        result = result.replace("| ","")

        print(f"  Image : {base_name}{camera_tag}")
        print(f"  Lang  : {tess_lang} | Words: {len(filtered_words)}")
        print(f"  Text  : {result or '(empty)'}")
        print(f"{'─'*40}\n")
        logging.info(f"OCR done — {len(filtered_words)} words")
        return result

    except Exception as e:
        logging.error(f"OCR error: {e}", exc_info=True)
        return ""