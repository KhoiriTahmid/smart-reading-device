import pigpio
import time
import threading
import queue
from helper.pins import IN3, IN4, ENB, FAN
from helper.fan  import fan_on, fan_off

REVERSE_PAUSE  = 0.2
PWM_FREQUENCY  = 1000
SLOW_SPEED     = 255
FULL_SPEED     = 255
SLOW_DURATION  = 5


def _duty(speed: int) -> int:
    return int(speed / 255 * 1_000_000)


def setup_motor(pi: pigpio.pi) -> None:
    pi.set_mode(IN3, pigpio.OUTPUT)
    pi.set_mode(IN4, pigpio.OUTPUT)
    _set_direction(pi, forward=True)
    print("Motor initialised")


def _set_direction(pi: pigpio.pi, forward: bool) -> None:
    if forward:
        pi.write(IN3, pigpio.LOW)
        pi.write(IN4, pigpio.HIGH)
        print("Direction: Forward")
    else:
        pi.write(IN3, pigpio.HIGH)
        pi.write(IN4, pigpio.LOW)
        print("Direction: Backward")


def motor_worker(pi: pigpio.pi, motor_queue: queue.Queue) -> None:
    """
    Permanent thread — only function that touches motor hardware.
    Commands: full, slow, stop, forward, backward, hard_stop, quit
    """
    slow_timer: threading.Timer | None = None
    direction  = True  # True = forward

    def cancel_timer():
        nonlocal slow_timer
        if slow_timer is not None:
            slow_timer.cancel()
            slow_timer = None

    def go_full():
        pi.hardware_PWM(ENB, PWM_FREQUENCY, _duty(FULL_SPEED))
        print(f"Motor: back to full ({FULL_SPEED}/255)")

    while True:
        try:
            cmd = motor_queue.get(timeout=0.1)
        except queue.Empty:
            continue

        print(f"Motor cmd: {cmd}")

        if cmd == "full":
            cancel_timer()
            fan_on(pi)
            pi.hardware_PWM(ENB, PWM_FREQUENCY, _duty(FULL_SPEED))
            print(f"Motor: full ({FULL_SPEED}/255)")

        elif cmd == "slow":
            cancel_timer()
            fan_on(pi)
            pi.hardware_PWM(ENB, PWM_FREQUENCY, _duty(SLOW_SPEED))
            print(f"Motor: slow ({SLOW_SPEED}/255)")
            slow_timer = threading.Timer(SLOW_DURATION, lambda: motor_queue.put("full"))
            slow_timer.daemon = True
            slow_timer.start()

        elif cmd == "stop":
            cancel_timer()
            pi.hardware_PWM(ENB, PWM_FREQUENCY, 0)
            fan_off(pi)
            print("Motor: stop")

        elif cmd == "forward":
            cancel_timer()
            direction = True
            _set_direction(pi, forward=True)
            pi.hardware_PWM(ENB, PWM_FREQUENCY, _duty(FULL_SPEED))
            fan_on(pi)

        elif cmd == "backward":
            cancel_timer()
            direction = False
            _set_direction(pi, forward=False)
            pi.hardware_PWM(ENB, PWM_FREQUENCY, _duty(FULL_SPEED))
            fan_on(pi)

        elif cmd == "hard_stop":
            cancel_timer()
            pi.hardware_PWM(ENB, PWM_FREQUENCY, 0)
            pi.write(IN3, pigpio.LOW)
            pi.write(IN4, pigpio.LOW)
            fan_off(pi)
            print("Motor: hard stop")

        elif cmd == "quit":
            cancel_timer()
            pi.hardware_PWM(ENB, PWM_FREQUENCY, 0)
            pi.write(IN3, pigpio.LOW)
            pi.write(IN4, pigpio.LOW)
            fan_off(pi)
            break