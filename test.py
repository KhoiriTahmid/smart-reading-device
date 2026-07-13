import pigpio
import time

pi = pigpio.pi()

pin = 19
pi.set_mode(pin, pigpio.INPUT)
pi.set_pull_up_down(pin, pigpio.PUD_UP)

while True:
    print(pi.read(pin))
    time.sleep(0.1)