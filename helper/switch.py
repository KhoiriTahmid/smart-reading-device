import pigpio
from helper.pins import SW1, SW2


def setup_switches(pi: pigpio.pi) -> None:
    pi.set_mode(SW1, pigpio.INPUT)
    pi.set_pull_up_down(SW1, pigpio.PUD_UP)  # was PUD_DOWN
    pi.set_mode(SW2, pigpio.INPUT)
    pi.set_pull_up_down(SW2, pigpio.PUD_UP)  # was PUD_DOWN


def read_sw1(pi: pigpio.pi) -> bool:
    return pi.read(SW1) == 1


def read_sw2_language(pi: pigpio.pi) -> str:
    """Returns 'english' if up, 'indonesian' if down."""
    return "english" if pi.read(SW2) == 1 else "indonesian"