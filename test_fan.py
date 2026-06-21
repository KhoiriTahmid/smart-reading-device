import time
import pigpio

from helper.fan import setup_fan, fan_on, fan_off

pi = pigpio.pi()

if not pi.connected:
    print("❌ Cannot connect to pigpiod")
    exit(1)

try:
    print("Initializing fan...")
    setup_fan(pi)

    fan_on(pi)
    time.sleep(200)

finally:
    fan_off(pi)
    pi.stop()