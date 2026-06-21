import pigpio
import time
from helper.pins import BTN1, BTN2, BTN3, BTN4, BTN5, BTN6

DEBOUNCE = 0.3  # seconds

_last_time = {
    BTN1: 0.0,
    BTN2: 0.0,
    BTN3: 0.0,
    BTN4: 0.0,
    BTN5: 0.0,
    BTN6: 0.0,
}
_last_state = {
    BTN1: 1,
    BTN2: 1,
    BTN3: 1,
    BTN4: 1,
    BTN5: 1,
    BTN6: 1,
}


def setup_buttons(pi: pigpio.pi) -> None:
    for pin in [BTN1, BTN2, BTN3, BTN4, BTN5]:
        pi.set_mode(pin, pigpio.INPUT)
        pi.set_pull_up_down(pin, pigpio.PUD_UP)


def _read(pi: pigpio.pi, pin: int) -> bool:
    """Returns True once per press with 0.3s debounce."""
    global _last_time, _last_state
    state = pi.read(pin)
    now   = time.monotonic()

    if state == 0 and _last_state[pin] == 1:  # falling edge = pressed
        if now - _last_time[pin] > DEBOUNCE:
            _last_time[pin]  = now
            _last_state[pin] = state
            return True

    _last_state[pin] = state
    return False


def read_btn1(pi: pigpio.pi) -> bool:
    return _read(pi, BTN1)

def read_btn2(pi: pigpio.pi) -> bool:
    return _read(pi, BTN2)

def read_btn3(pi: pigpio.pi) -> bool:
    return _read(pi, BTN3)

def read_btn4(pi: pigpio.pi) -> bool:
    return _read(pi, BTN4)

def read_btn5(pi: pigpio.pi) -> bool:
    return _read(pi, BTN5)

def read_btn6(pi: pigpio.pi) -> bool:
    return _read(pi, BTN6)