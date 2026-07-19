import pigpio
import time
from helper.pins import BTN1, BTN2, BTN3, BTN4, BTN5, BTN6

# ------------------------------------------------------------------
# Debounce config
# ------------------------------------------------------------------
DEBOUNCE_MS = 30  # Button must stay stable for 30 ms


class DebouncedButton:
    """
    Debounces an active-low push button and returns True only once
    for each physical press.
    """

    def __init__(self, pi: pigpio.pi, pin: int, debounce_ms: int = DEBOUNCE_MS):
        self.pi = pi
        self.pin = pin
        self.debounce_s = debounce_ms / 1000.0

        raw = pi.read(pin)
        self.stable_state = raw
        self.last_raw = raw
        self.last_change_time = time.monotonic()

        # Prevent repeated events while button is held
        self.press_reported = False

    def pressed(self) -> bool:
        raw = self.pi.read(self.pin)
        now = time.monotonic()

        # Raw state changed -> restart debounce timer
        if raw != self.last_raw:
            self.last_raw = raw
            self.last_change_time = now
            return False

        # Raw state has remained stable long enough
        if (
            raw != self.stable_state
            and (now - self.last_change_time) >= self.debounce_s
        ):
            self.stable_state = raw

            # Button pressed (active LOW)
            if raw == 0:
                if not self.press_reported:
                    self.press_reported = True
                    return True

            # Button released
            else:
                self.press_reported = False

        return False


_buttons: dict[int, DebouncedButton] = {}


def setup_buttons(pi: pigpio.pi) -> None:
    global _buttons

    for pin in (BTN1, BTN2, BTN3, BTN4, BTN5, BTN6):
        pi.set_mode(pin, pigpio.INPUT)
        pi.set_pull_up_down(pin, pigpio.PUD_UP)

        # Ignore electrical glitches shorter than 10 ms
        pi.set_glitch_filter(pin, 10000)

        _buttons[pin] = DebouncedButton(pi, pin)


def _read(pin: int) -> bool:
    return _buttons[pin].pressed()


def read_btn1(pi: pigpio.pi) -> bool:
    return _read(BTN1)


def read_btn2(pi: pigpio.pi) -> bool:
    return _read(BTN2)


def read_btn3(pi: pigpio.pi) -> bool:
    return _read(BTN3)


def read_btn4(pi: pigpio.pi) -> bool:
    return _read(BTN4)


def read_btn5(pi: pigpio.pi) -> bool:
    return _read(BTN5)


def read_btn6(pi: pigpio.pi) -> bool:
    return _read(BTN6)