import pigpio
import time
from helper.pins import ULTRA1_TRIG, ULTRA1_ECHO, ULTRA2_TRIG, ULTRA2_ECHO


def setup_ultrasonic(pi: pigpio.pi) -> None:
    for trig in [ULTRA1_TRIG, ULTRA2_TRIG]:
        pi.set_mode(trig, pigpio.OUTPUT)
        pi.write(trig, 0)
    for echo in [ULTRA1_ECHO, ULTRA2_ECHO]:
        pi.set_mode(echo, pigpio.INPUT)
    time.sleep(0.1)


def _read(pi: pigpio.pi, trig: int, echo: int) -> float | None:
    """Raw distance read — returns cm or None if failed."""
    pi.write(trig, 1)
    time.sleep(0.00001)
    pi.write(trig, 0)

    timeout = time.time() + 0.04
    while pi.read(echo) == 0:
        if time.time() > timeout:
            return None

    start = time.time()
    timeout = time.time() + 0.04
    while pi.read(echo) == 1:
        if time.time() > timeout:
            return None

    return (time.time() - start) * 17150


def read_ultra2(pi: pigpio.pi) -> float | None:
    return _read(pi, ULTRA1_TRIG, ULTRA1_ECHO)


def read_ultra1(pi: pigpio.pi) -> float | None:
    return _read(pi, ULTRA2_TRIG, ULTRA2_ECHO)