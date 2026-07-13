"""
test_tts.py
Quick manual test for the speak() function.

To test Piper specifically: disconnect WiFi first, since speak()
auto-falls-back to Piper only when is_wifi_connected() is False.

Run with: python3 test_tts.py
"""

import logging
from helper.speak import speak

logging.basicConfig(level=logging.INFO)

DUMMY_TEXT = {
    "english":    "Hello, this is a test of the text to speech engine.",
    "indonesian": "Halo, ini adalah tes mesin text to speech.",
}


def main():
    for lang, text in DUMMY_TEXT.items():
        print(f"\n--- Testing: {lang} ---")
        filepath = speak(text, lang=lang, volume=20, speed=20)
        if filepath:
            print(f"Done: {filepath}")
        else:
            print("speak() returned None — check logs above.")


if __name__ == "__main__":
    main()