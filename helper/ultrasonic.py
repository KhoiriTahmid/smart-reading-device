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


def read_ultra1(pi: pigpio.pi) -> float | None:
    return _read(pi, ULTRA1_TRIG, ULTRA1_ECHO)


def read_ultra2(pi: pigpio.pi) -> float | None:
    return _read(pi, ULTRA2_TRIG, ULTRA2_ECHO)


# import pigpio
# import time
# import board
# import busio
# import adafruit_vl53l0x
# from helper.pins import ULTRA1_TRIG, ULTRA1_ECHO

# _vl53: adafruit_vl53l0x.VL53L0X | None = None


# def setup_ultrasonic(pi: pigpio.pi) -> None:
#     """Set up the page-turn ultrasonic (GPIO) and the VL53L0X (I2C)."""
#     pi.set_mode(ULTRA1_TRIG, pigpio.OUTPUT)
#     pi.write(ULTRA1_TRIG, 0)
#     pi.set_mode(ULTRA1_ECHO, pigpio.INPUT)
#     time.sleep(0.1)

#     global _vl53
#     i2c = busio.I2C(board.SCL, board.SDA)  # GPIO3 = SCL, GPIO2 = SDA
#     _vl53 = adafruit_vl53l0x.VL53L0X(i2c)


# def _read(pi: pigpio.pi, trig: int, echo: int) -> float | None:
#     """Raw distance read — returns cm or None if failed."""
#     pi.write(trig, 1)
#     time.sleep(0.00001)
#     pi.write(trig, 0)

#     timeout = time.time() + 0.04
#     while pi.read(echo) == 0:
#         if time.time() > timeout:
#             return None

#     start = time.time()
#     timeout = time.time() + 0.04
#     while pi.read(echo) == 1:
#         if time.time() > timeout:
#             return None

#     return (time.time() - start) * 17150


# def read_ultra1(pi: pigpio.pi) -> float | None:
#     return _read(pi, ULTRA1_TRIG, ULTRA1_ECHO)


# # --- VL53L0X (book presence) -------------------------------------------

# def read_ultra2(pi: pigpio.pi | None = None) -> float | None:
#     """Drop-in replacement for the old book-presence ultrasonic.
#     `pi` is accepted but unused — kept so existing call sites don't break.
#     Returns distance in cm to match the old ultrasonic's units."""
#     if _vl53 is None:
#         return None
#     try:
#         return _vl53.range / 10.0  # range is in mm, convert to cm
#     except OSError:
#         return None