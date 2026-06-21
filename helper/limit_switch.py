import pigpio
from helper.pins import LIMIT_SW1, LIMIT_SW2


def setup_limit_switches(pi: pigpio.pi) -> None:
    for pin in [LIMIT_SW1, LIMIT_SW2]:
        pi.set_mode(pin, pigpio.INPUT)
        pi.set_pull_up_down(pin, pigpio.PUD_UP)  # normally HIGH, LOW when pressed


def read_limit_sw1(pi: pigpio.pi) -> bool:
    """Returns True when pressed."""
    return pi.read(LIMIT_SW1) == 0


def read_limit_sw2(pi: pigpio.pi) -> bool:
    """Returns True when pressed."""
    return pi.read(LIMIT_SW2) == 0