import logging
import os
import time
import pigpio
from helper.led import setup_led, led_on, led_off



from helper.capture import capture_picamera, capture_usb, capture_both

pi = pigpio.pi()

if not pi.connected:
    raise RuntimeError("Could not connect to pigpio daemon")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

def check_file(path):
    if path and os.path.exists(path):
        print(f"✅ File created: {path}")
        print(f"   Size: {os.path.getsize(path)} bytes")
    else:
        print(f"❌ File not found: {path}")
        
def tes():
    index = 1

    led_on(pi)

    print("\n=== TEST PICAMERA ===", index)
    picam_path, index = capture_picamera(index)
    check_file(picam_path)

    index+=1

    print("\n=== TEST USB CAMERA ===", index)
    usb_path, index = capture_usb(index)
    check_file(usb_path)

    index+=1

    print("\n=== TEST BOTH ===", index)
    picam_path, usb_path, index = capture_both(index)
    check_file(picam_path)
    check_file(usb_path)

    print(f"\nFinal index = {index}")

    while True:
        time.sleep(10)

setup_led(pi)

try:
    tes()
except KeyboardInterrupt:
    print("Stopping...")

finally:
    led_off(pi)
    pi.stop()

