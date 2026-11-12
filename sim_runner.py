#!/usr/bin/env python3
"""
Entry point to run the REAL Smart Reading Device code in Simulation / Docker Mode.

This runner:
1. Installs fake hardware modules (pigpio, picamera2, pigpio_encoder, etc.)
2. Overrides hardware capture & speaker functions with simulated loggers / synthetic generators
3. Injects interactive CLI commands (simulating physical switches, buttons, and sensors)
4. Starts main.py's setup(), start_threads(), and loop()
"""

import os
import sys
import time
import logging
import threading

# ── 1. Install fake Pi hardware BEFORE importing anything from helper or main ──
from sim import fakes
fakes.install()

from sim.fakes import FakePi, find_rotary
from sim.mock_hardware import generate_synthetic_page

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(threadName)s] %(name)s: %(levelname)s: %(message)s",
)
logger = logging.getLogger("SIMULATOR")

# ── 2. Override hardware capture & sound functions with non-blocking simulation ──
import helper.capture as capture_mod
import helper.speaker as speaker_mod
import helper.speak as speak_mod

_spread_count = 0

def sim_capture_both(index: int) -> tuple[str | None, str | None, int]:
    global _spread_count
    _spread_count += 1
    left_page_num = (_spread_count - 1) * 2 + 1
    right_page_num = left_page_num + 1

    logger.info(f"📸 [SIM CAM] Memotret Kamera Kiri (Halaman {left_page_num}) & Kanan (Halaman {right_page_num})...")
    usb_path = generate_synthetic_page(left_page_num, "webcam")
    picam_path = generate_synthetic_page(right_page_num, "picam")
    return picam_path, usb_path, index + 2

def sim_play_sound(path: str, volume: int) -> None:
    sound_name = os.path.basename(path)
    logger.info(f"🔊 [SPEAKER ALAT] (sim) Memutar audio pemberitahuan: '{sound_name}' (volume={volume}%)")

def sim_play(filepath: str, volume: int = 50, min_timeout: int = 15) -> None:
    logger.info(f"🔊 [SPEAKER ALAT] (sim) Membacakan hasil TTS: '{filepath}' (volume={volume}%)")

capture_mod.capture_both = sim_capture_both
speaker_mod._play_sound = sim_play_sound
speak_mod._play = sim_play
speak_mod.set_volume = lambda vol: logger.info(f"🎚️ [ALSA VOLUME] (sim) Volume speaker diatur ke {vol}%")

# ── 3. Import device main logic ─────────────────────────────────────────────
import main
from helper.pins import (
    SW1, SW2, LIMIT_SW1, LIMIT_SW2,
    BTN1, BTN2, BTN3, BTN4, BTN5, BTN6,
    ENC1_CLK, ENC2_CLK
)

def print_help():
    print("""
==================================================================
  🎛️  SMART READING DEVICE — VIRTUAL HARDWARE CLI
==================================================================
  Kontrol simulasi fisik alat:
    [s] / [enter] : Tekan Tombol SCAN / START (BTN5) -> memicu alur scan, OCR, & TTS
    [1]           : Toggle Sakelar Power ON / OFF (SW1)
    [l]           : Toggle Sakelar Bahasa (SW2: Indonesia <-> English)
    [b]           : Tekan Tombol Reset / Bounce (BTN5 reset)
    [+] / [-]     : Putar Knob Volume (KY-040 #1)
    [>] / [<]     : Putar Knob Kecepatan TTS (KY-040 #2)
    [h]           : Tekan Limit Switch Home (LIMIT_SW1)
    [f]           : Tekan Limit Switch Flip (LIMIT_SW2)
    [?]           : Tampilkan menu bantuan ini
    [q]           : Matikan alat dan keluar
==================================================================
""")

def run_interactive_cli(pi: FakePi):
    time.sleep(1.0)
    print_help()

    sw1_state = False
    sw2_lang = "indonesian"

    while True:
        try:
            line = sys.stdin.readline()
            if not line:
                break
            cmd = line.strip().lower()

            if cmd in ("s", ""):
                logger.info("👉 [TOMBOL FISIK] Menekan BTN5 (Start Scan)...")
                # Trigger BTN5 press
                pi.sim_set_input(BTN5, fakes.LOW)
                time.sleep(0.06)
                pi.sim_set_input(BTN5, fakes.HIGH)

            elif cmd == "1":
                sw1_state = not sw1_state
                level = fakes.LOW if sw1_state else fakes.HIGH
                logger.info(f"👉 [SAKELAR FISIK SW1] Power diubah ke: {'ON' if sw1_state else 'OFF'}")
                pi.sim_set_input(SW1, level)

            elif cmd == "l":
                sw2_lang = "english" if sw2_lang == "indonesian" else "indonesian"
                level = fakes.HIGH if sw2_lang == "english" else fakes.LOW
                logger.info(f"👉 [SAKELAR BAHASA SW2] Bahasa diubah ke: {sw2_lang}")
                pi.sim_set_input(SW2, level)

            elif cmd == "+":
                r = find_rotary(ENC1_CLK)
                if r:
                    r.sim_turn(2)

            elif cmd == "-":
                r = find_rotary(ENC1_CLK)
                if r:
                    r.sim_turn(-2)

            elif cmd == ">":
                r = find_rotary(ENC2_CLK)
                if r:
                    r.sim_turn(2)

            elif cmd == "<":
                r = find_rotary(ENC2_CLK)
                if r:
                    r.sim_turn(-2)

            elif cmd == "h":
                logger.info("👉 [LIMIT SWITCH] Menekan LIMIT_SW1 (Home position)...")
                pi.sim_set_input(LIMIT_SW1, fakes.LOW)
                time.sleep(0.1)
                pi.sim_set_input(LIMIT_SW1, fakes.HIGH)

            elif cmd == "f":
                logger.info("👉 [LIMIT SWITCH] Menekan LIMIT_SW2 (Pembalikan halaman selesai)...")
                pi.sim_set_input(LIMIT_SW2, fakes.LOW)
                time.sleep(0.1)
                pi.sim_set_input(LIMIT_SW2, fakes.HIGH)

            elif cmd == "?":
                print_help()

            elif cmd == "q":
                logger.info("Menghentikan simulator...")
                os._exit(0)

        except (EOFError, KeyboardInterrupt):
            break

def main_sim():
    logger.info("Inisialisasi perangkat dalam mode SIMULASI DOCKER...")
    pi = FakePi()

    # Initial physical states
    pi.sim_set_input(SW1, fakes.HIGH)        # SW1 OFF initially
    pi.sim_set_input(SW2, fakes.LOW)         # Indonesian
    pi.sim_set_input(LIMIT_SW1, fakes.LOW)   # At home position
    pi.sim_set_input(LIMIT_SW2, fakes.HIGH)

    for btn in (BTN1, BTN2, BTN3, BTN4, BTN5, BTN6):
        pi.sim_set_input(btn, fakes.HIGH)

    main.setup(pi)
    main.start_threads(pi)

    # Start CLI thread
    cli_thread = threading.Thread(target=run_interactive_cli, args=(pi,), daemon=True)
    cli_thread.start()

    # Run main device loop
    try:
        main.loop(pi)
    except KeyboardInterrupt:
        logger.info("Simulator dihentikan oleh pengguna.")

if __name__ == "__main__":
    main_sim()
