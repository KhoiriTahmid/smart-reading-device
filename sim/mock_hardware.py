"""
Synthetic test page generator for camera capture in simulation.
Generates images for:
- Page 1: Left camera (USB Webcam)
- Page 2: Right camera (PiCam)
Each image contains clear readable text and labels so OCR can extract it.
"""

import os
from PIL import Image, ImageDraw, ImageFont

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
IMAGES_DIR = os.path.join(BASE_DIR, "images")
os.makedirs(IMAGES_DIR, exist_ok=True)

def _get_font(size: int = 36):
    font_paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    ]
    for p in font_paths:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                pass
    return ImageFont.load_default()

def generate_synthetic_page(
    page_number: int,
    camera_type: str, # "webcam" (left) or "picam" (right)
    lang: str = "id",
) -> str:
    # 1600x1200 white canvas
    width, height = 1600, 1200
    img = Image.new("RGB", (width, height), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)

    title_font = _get_font(48)
    body_font = _get_font(34)
    footer_font = _get_font(26)

    # Header / Page Title
    cam_label = "Kamera Kiri (Webcam)" if camera_type == "webcam" else "Kamera Kanan (PiCam)"
    if lang == "en":
        title = f"Chapter {page_number}: Smart Reading Device"
        sub = f"Simulated capture from {cam_label}"
        paragraphs = [
            f"This is page {page_number} captured during hardware simulation.",
            "Assistive reading technology allows autonomous book reading.",
            "Each camera captures one side of the open book spread without horizontal stitching.",
            "Left and right pages are saved into a multi-page PDF document.",
            "The optical character recognition pipeline processes text page by page sequentially.",
            "TTS audio is synthesized and synced with the user interface dashboard.",
        ]
    else:
        title = f"Bab {page_number}: Perangkat Pembaca Cerdas"
        sub = f"Hasil simulasi pemotretan dari {cam_label}"
        paragraphs = [
            f"Ini adalah halaman {page_number} yang dipindai dalam mode simulasi perangkat.",
            "Teknologi alat bantu baca cerdas memungkinkan membaca buku secara mandiri.",
            "Kamera kiri dan kanan memotret masing-masing lembaran buku tanpa penyambungan horizontal.",
            "Hasil pindaian dibungkus menjadi dokumen PDF multi-halaman yang rapi.",
            "Sistem OCR mengekstrak baris teks berurutan dan mengonversinya menjadi suara (TTS).",
            "Suara hasil sintesis diputar bergantian mulai dari halaman kiri lalu halaman kanan.",
        ]

    # Draw border
    draw.rectangle([(60, 60), (width - 60, height - 60)], outline=(180, 180, 180), width=4)

    # Draw Title & subtitle
    y = 120
    draw.text((120, y), title, fill=(20, 20, 20), font=title_font)
    y += 70
    draw.text((120, y), sub, fill=(100, 100, 100), font=footer_font)
    y += 60
    draw.line([(120, y), (width - 120, y)], fill=(200, 200, 200), width=2)
    y += 50

    # Draw paragraphs
    for p in paragraphs:
        draw.text((120, y), p, fill=(30, 30, 30), font=body_font)
        y += 65

    # Footer
    footer_text = f"Smart Reading IoT Project — Halaman {page_number}"
    draw.text((120, height - 120), footer_text, fill=(120, 120, 120), font=footer_font)

    file_name = f"sim_capture_{camera_type}_{page_number}.jpg"
    out_path = os.path.join(IMAGES_DIR, file_name)
    img.save(out_path, "JPEG", quality=95)
    return out_path
