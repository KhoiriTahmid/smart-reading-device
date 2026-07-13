"""
test_sensors.py
Quick manual test for the page-turn ultrasonic (HC-SR04-style) and
the VL53L0X ToF "book presence" sensor.

Run with: python3 test_sensors.py
Ctrl+C to stop.
"""

import time
import pigpio

from helper.pins import ULTRA1_TRIG, ULTRA1_ECHO
from helper.ultrasonic import setup_ultrasonic, read_ultra1, read_ultra2  # adjust import path as needed


def main():
    pi = pigpio.pi()
    if not pi.connected:
        print("ERROR: could not connect to pigpio daemon. Is `sudo pigpiod` running?")
        return

    try:
        setup_ultrasonic(pi)
        print("Sensors initialized. Reading... (Ctrl+C to stop)\n")

        while True:
            d1 = read_ultra1(pi)
            d2 = read_ultra2(pi)

            d1_str = f"{d1:6.2f} cm" if d1 is not None else "  FAIL   "
            d2_str = f"{d2:6.2f} cm" if d2 is not None else "  FAIL   "

            print(f"ultra1 (HC-SR04): {d1_str}   |   ultra2 (VL53L0X): {d2_str}")

            time.sleep(0.2)

    except KeyboardInterrupt:
        print("\nStopping.")

    finally:
        pi.stop()


if __name__ == "__main__":
    main()