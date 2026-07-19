import pigpio
import time
from helper.pins import SW1, SW2

# ------------------------------------------------------------------
# Debounce config
# ------------------------------------------------------------------
DEBOUNCE_MS = 50  # minimum stable time before accepting a state change


class DebouncedSwitch:
    """
    Only accepts a new reading as 'real' if the raw pin value stays
    consistent for DEBOUNCE_MS. Filters out bounce/noise flicker.
    """
    def __init__(self, pi: pigpio.pi, pin: int, debounce_ms: int = DEBOUNCE_MS):
        self.pi = pi
        self.pin = pin
        self.debounce_s = debounce_ms / 1000.0

        raw = pi.read(pin)
        self.stable_state = raw          # last confirmed/accepted value
        self.last_raw = raw              # last raw reading seen
        self.last_change_time = time.monotonic()

    def read(self) -> int:
        raw = self.pi.read(self.pin)
        now = time.monotonic()

        if raw != self.last_raw:
            # raw value changed -> restart the debounce timer
            self.last_raw = raw
            self.last_change_time = now
        else:
            # raw value has been steady -> check if it's been steady long enough
            if (now - self.last_change_time) >= self.debounce_s and raw != self.stable_state:
                self.stable_state = raw

        return self.stable_state


_sw1_debounced: DebouncedSwitch | None = None
_sw2_debounced: DebouncedSwitch | None = None


def setup_switches(pi: pigpio.pi) -> None:
    pi.set_mode(SW1, pigpio.INPUT)
    pi.set_pull_up_down(SW1, pigpio.PUD_UP)
    pi.set_mode(SW2, pigpio.INPUT)
    pi.set_pull_up_down(SW2, pigpio.PUD_UP)

    # Hardware-level noise filter (pigpio built-in): ignore pulses
    # shorter than this on the GPIO before pigpio even reports a change.
    # Cheap, catches electrical/EMI glitches before software sees them.
    pi.set_glitch_filter(SW1, 10000)  # 10,000 us = 10 ms
    pi.set_glitch_filter(SW2, 10000)

    global _sw1_debounced, _sw2_debounced
    _sw1_debounced = DebouncedSwitch(pi, SW1)
    _sw2_debounced = DebouncedSwitch(pi, SW2)


def read_sw1(pi: pigpio.pi) -> bool:
    return _sw1_debounced.read() == 0


def read_sw2_language(pi: pigpio.pi) -> str:
    """Returns 'english' if up, 'indonesian' if down."""
    return "english" if _sw2_debounced.read() == 1 else "indonesian"