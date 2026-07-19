"""
Test beep_up / beep_down sound playback.
Two modes:
  1. Dummy  — simulate encoder turns from keyboard input (no hardware needed)
  2. Real   — actually read the physical encoder via pigpio

Run: python3 test_beep.py
"""
import sys
import time
import queue
import threading
import logging

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

from helper.speaker import setup_speaker, speaker_worker, _play_sound, SOUNDS


def test_dummy_mode() -> None:
    """No hardware needed — just directly call _play_sound with beep files."""
    print("\n=== DUMMY MODE — no encoder needed ===")
    print("Press ENTER to play beep_up, type 'd' + ENTER for beep_down, 'q' to quit\n")

    setup_speaker()

    # Fixed test volume — adjust if you want to test at different levels
    volume = 80

    while True:
        cmd = input("> ").strip().lower()
        if cmd == "q":
            break
        elif cmd == "d":
            print("Playing beep_down...")
            _play_sound(f"sounds/{SOUNDS['beep_down']}", volume)
            print("Done.\n")
        else:
            print("Playing beep_up...")
            _play_sound(f"sounds/{SOUNDS['beep_up']}", volume)
            print("Done.\n")


def test_real_encoder_mode() -> None:
    """Use the actual physical encoder, routed through the real speaker_worker/queue."""
    print("\n=== REAL ENCODER MODE — turn the volume/speed knob ===")
    print("Ctrl+C to quit\n")

    import pigpio
    from helper.encoder import setup_encoders, get_volume

    pi = pigpio.pi()
    if not pi.connected:
        print("ERROR: cannot connect to pigpiod. Run: sudo systemctl start pigpiod")
        sys.exit(1)

    speaker_queue = queue.Queue()
    setup_speaker()
    setup_encoders(pi, speaker_queue=speaker_queue)

    t = threading.Thread(
        target=speaker_worker,
        args=(speaker_queue, lambda: "indonesian"),
        daemon=True,
    )
    t.start()

    try:
        while True:
            time.sleep(0.1)
    except KeyboardInterrupt:
        print("\nStopping...")
        speaker_queue.put("quit")
        pi.stop()


if __name__ == "__main__":
    print("Beep test — choose mode:")
    print("  1) Dummy  (no encoder needed, keyboard input)")
    print("  2) Real   (actual physical encoder)")
    choice = input("Choice [1/2]: ").strip()

    if choice == "2":
        test_real_encoder_mode()
    else:
        test_dummy_mode()