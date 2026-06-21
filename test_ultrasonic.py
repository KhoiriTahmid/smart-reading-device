import pigpio
import time

from helper.ultrasonic import (
    setup_ultrasonic,
    read_ultra1,
    read_ultra2,
)

pi = pigpio.pi()

if not pi.connected:
    print("Failed to connect to pigpio daemon")
    exit(1)

setup_ultrasonic(pi)

print("Testing ultrasonic sensors...")
print("Press Ctrl+C to stop\n")

try:
    while True:
        d1 = read_ultra1(pi)
        d2 = read_ultra2(pi)

        d1_text = f"{d1:.1f} cm" if d1 is not None else "TIMEOUT"
        d2_text = f"{d2:.1f} cm" if d2 is not None else "TIMEOUT"

        print(
            f"\rUltra1: {d1_text:<12} | Ultra2: {d2_text:<12}",
            end="",
            flush=True
        )

        time.sleep(0.2)

except KeyboardInterrupt:
    print("\nStopped")

finally:
    pi.stop()