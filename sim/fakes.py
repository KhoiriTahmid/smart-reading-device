"""
Fake replacements for Raspberry-Pi-only libraries so the REAL device code
(main.py + helper/*) can be imported and executed on a laptop / in Docker.

Nothing here drives real hardware. Every output pin change that matters
(fan, LED, motor H-bridge/PWM) is printed as a log line instead.
"""

from __future__ import annotations

import logging
import sys
import threading
import types

log = logging.getLogger("SIM.gpio")

# ── pigpio constants ────────────────────────────────────────────────────────
INPUT, OUTPUT = 0, 1
LOW, HIGH = 0, 1
PUD_OFF, PUD_DOWN, PUD_UP = 0, 1, 2

# Pin numbers are imported lazily from helper.pins (single source of truth).
_PINS: dict[str, int] = {}


def _pin(name: str) -> int | None:
    if not _PINS:
        from helper import pins as p

        _PINS.update({k: v for k, v in vars(p).items() if k.isupper()})
    return _PINS.get(name)


def pin_name(pin: int) -> str:
    _pin("FAN")  # ensure loaded
    for name, num in _PINS.items():
        if num == pin:
            return name
    return f"GPIO{pin}"


class FakePi:
    """Drop-in replacement for pigpio.pi() — a single shared virtual GPIO bank."""

    _instance: "FakePi | None" = None
    _instance_lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        with cls._instance_lock:
            if cls._instance is None:
                inst = super().__new__(cls)
                inst._init()
                cls._instance = inst
            return cls._instance

    def _init(self) -> None:
        self.connected = True
        self._lock = threading.RLock()
        self._levels: dict[int, int] = {}
        self._modes: dict[int, int] = {}
        self._pwm: dict[int, int] = {}
        self._pwm_freq: dict[int, int] = {}
        self._motor_logged: tuple[bool, str] = (False, "stopped")

    # ── pigpio API used by the device code ──────────────────────────────────
    def set_mode(self, pin: int, mode: int) -> int:
        with self._lock:
            self._modes[pin] = mode
        return 0

    def set_pull_up_down(self, pin: int, pud: int) -> int:
        with self._lock:
            if pin not in self._levels:
                self._levels[pin] = LOW if pud == PUD_DOWN else HIGH
        return 0

    def set_glitch_filter(self, pin: int, steady: int) -> int:
        return 0

    def read(self, pin: int) -> int:
        with self._lock:
            return self._levels.get(pin, HIGH)

    def write(self, pin: int, level: int) -> int:
        level = HIGH if level else LOW
        with self._lock:
            prev = self._levels.get(pin)
            self._levels[pin] = level
        if prev is not None and prev != level:
            self._log_output_change(pin, level)
        return 0

    def set_PWM_frequency(self, pin: int, freq: int) -> int:
        with self._lock:
            self._pwm_freq[pin] = freq
        return freq

    def set_PWM_dutycycle(self, pin: int, duty: int) -> int:
        with self._lock:
            self._pwm[pin] = int(duty)
        if pin == _pin("ENB"):
            self._log_motor_if_changed()
        return 0

    def get_PWM_dutycycle(self, pin: int) -> int:
        with self._lock:
            return self._pwm.get(pin, 0)

    def stop(self) -> None:
        log.info("[GPIO] pigpio connection closed (simulated)")

    # ── Simulator-side helpers (not part of pigpio) ─────────────────────────
    def sim_set_input(self, pin: int, level: int) -> None:
        """Change an INPUT pin as if the physical world changed it."""
        with self._lock:
            self._levels[pin] = HIGH if level else LOW

    def motor_direction(self) -> str:
        in3 = self.read(_pin("IN3"))
        in4 = self.read(_pin("IN4"))
        if (in3, in4) == (LOW, HIGH):
            return "forward"
        if (in3, in4) == (HIGH, LOW):
            return "backward"
        return "stopped"

    def motor_duty(self) -> int:
        return self.get_PWM_dutycycle(_pin("ENB"))

    # ── Logging of meaningful hardware actions ──────────────────────────────
    def _log_output_change(self, pin: int, level: int) -> None:
        if pin == _pin("FAN"):
            if level:
                log.info("🌀 [FAN  GPIO%s] ON  — kipas pembalik halaman BERPUTAR", pin)
            else:
                log.info("🌀 [FAN  GPIO%s] OFF — kipas berhenti", pin)
        elif pin == _pin("LED"):
            log.info("💡 [LED  GPIO%s] %s", pin, "ON  — lampu kamera menyala" if level else "OFF")
        elif pin in (_pin("IN3"), _pin("IN4")):
            self._log_motor_if_changed()
        elif pin == _pin("ULTRA1_TRIG"):
            pass  # trigger pulses are noise
        else:
            log.debug("[GPIO] %s(%s) -> %s", pin_name(pin), pin, level)

    def _log_motor_if_changed(self) -> None:
        duty = self.motor_duty()
        direction = self.motor_direction()
        running = duty > 0 and direction != "stopped"
        state = (running, direction if running else "stopped")
        with self._lock:
            if state == self._motor_logged:
                return
            self._motor_logged = state
        if running:
            label = "MAJU (forward)" if direction == "forward" else "MUNDUR (backward)"
            log.info("⚙️  [MOTOR ENB GPIO%s] BERGERAK %s — PWM %s/255", _pin("ENB"), label, duty)
            # Physical switch mechanical interlock:
            # When motor moves forward, arm leaves LIMIT_SW1 (home switch releases)
            if direction == "forward":
                self._levels[_pin("LIMIT_SW1")] = HIGH
            # When motor moves backward, arm leaves LIMIT_SW2 (flip switch releases)
            elif direction == "backward":
                self._levels[_pin("LIMIT_SW2")] = HIGH
        else:
            log.info("⚙️  [MOTOR ENB GPIO%s] BERHENTI", _pin("ENB"))


def _make_pigpio_module() -> types.ModuleType:
    m = types.ModuleType("pigpio")
    m.pi = FakePi
    m.INPUT, m.OUTPUT = INPUT, OUTPUT
    m.LOW, m.HIGH = LOW, HIGH
    m.PUD_OFF, m.PUD_DOWN, m.PUD_UP = PUD_OFF, PUD_DOWN, PUD_UP
    m.__sim__ = True
    return m


# ── pigpio_encoder (KY-040 rotary encoders) ─────────────────────────────────
class FakeRotary:
    instances: list["FakeRotary"] = []
    sw_gpio = None

    def __init__(self, clk_gpio=None, dt_gpio=None, sw_gpio=None):
        self.clk_gpio = clk_gpio
        self.dt_gpio = dt_gpio
        self.counter = 0
        self._min, self._max, self._scale = 0, 100, 1
        self._cb = None
        FakeRotary.instances.append(self)

    def setup_rotary(self, min=0, max=100, scale=1, debounce=0,
                     rotary_callback=None, up_callback=None, down_callback=None):
        self._min, self._max, self._scale = min, max, scale
        self._cb = rotary_callback

    def setup_switch(self, *args, **kwargs):
        pass

    def watch(self):
        pass

    def sim_turn(self, steps: int) -> None:
        """Simulate turning the knob `steps` detents (negative = counter-clockwise)."""
        self.counter = max(self._min, min(self._max, self.counter + steps * self._scale))
        if self._cb:
            self._cb(self.counter)


def find_rotary(clk_gpio: int) -> FakeRotary | None:
    for r in FakeRotary.instances:
        if r.clk_gpio == clk_gpio:
            return r
    return None


# ── Misc Pi-only modules ────────────────────────────────────────────────────
class FakePicamera2:
    def __init__(self, *args, **kwargs):
        raise RuntimeError("Picamera2 is not available in the simulator")


class FakeVL53L0X:
    def __init__(self, *args, **kwargs):
        raise RuntimeError("VL53L0X is not available in the simulator")


class FakePiperVoice:
    @staticmethod
    def load(model_path, *args, **kwargs):
        log.info("[PIPER] (sim) voice model '%s' pretended loaded", model_path)
        return FakePiperVoice()


def install() -> None:
    """Register fake modules in sys.modules BEFORE the device code is imported."""
    rotary_pkg = types.ModuleType("pigpio_encoder")
    rotary_mod = types.ModuleType("pigpio_encoder.rotary")
    rotary_mod.Rotary = FakeRotary
    rotary_pkg.rotary = rotary_mod

    picam = types.ModuleType("picamera2")
    picam.Picamera2 = FakePicamera2

    board = types.ModuleType("board")
    board.SCL, board.SDA = 3, 2

    busio = types.ModuleType("busio")
    busio.I2C = lambda *a, **k: object()

    vl53 = types.ModuleType("adafruit_vl53l0x")
    vl53.VL53L0X = FakeVL53L0X

    piper = types.ModuleType("piper")
    piper.PiperVoice = FakePiperVoice

    sys.modules.update({
        "pigpio": _make_pigpio_module(),
        "pigpio_encoder": rotary_pkg,
        "pigpio_encoder.rotary": rotary_mod,
        "picamera2": picam,
        "board": board,
        "busio": busio,
        "adafruit_vl53l0x": vl53,
        "piper": piper,
    })
