import pigpio
import time

pi = pigpio.pi()

pi.set_mode(19, pigpio.INPUT)
pi.set_pull_up_down(19, pigpio.PUD_UP)

while True:
    print(pi.read(19))
    time.sleep(0.1)