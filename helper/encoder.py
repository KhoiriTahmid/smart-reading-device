import pigpio
import time
from helper.pins import ENC1_CLK, ENC1_DT, ENC2_CLK, ENC2_DT

_volume    = 50
_tts_speed = 50

_enc1_last_clk = None
_enc2_last_clk = None
_enc1_last_time = 0
_enc2_last_time = 0

DEBOUNCE = 0.05  # 50ms — ignore bounces faster than this


def setup_encoders(pi: pigpio.pi) -> None:
    global _enc1_last_clk, _enc2_last_clk
    for pin in [ENC1_CLK, ENC1_DT, ENC2_CLK, ENC2_DT]:
        pi.set_mode(pin, pigpio.INPUT)
        pi.set_pull_up_down(pin, pigpio.PUD_UP)
    _enc1_last_clk = pi.read(ENC1_CLK)
    _enc2_last_clk = pi.read(ENC2_CLK)


DEBOUNCE = 0.1  # increase from 0.05 to 0.1

def read_encoders(pi: pigpio.pi) -> None:
    global _volume, _tts_speed
    global _enc1_last_clk, _enc2_last_clk
    global _enc1_last_time, _enc2_last_time

    now = time.monotonic()

    # KY-040 #1 — volume
    clk = pi.read(ENC1_CLK)
    if clk != _enc1_last_clk and clk == 0:
        if now - _enc1_last_time > DEBOUNCE:
            time.sleep(0.001)        # small delay to let DT settle
            dt = pi.read(ENC1_DT)
            print(f"CLK=0, DT={dt}")
            if dt == 1:
                _volume = min(100, _volume + 5)
            else:
                _volume = max(0, _volume - 5)
            print(f"Volume: {_volume}")
            _enc1_last_time = now
    _enc1_last_clk = clk

    # KY-040 #2 — TTS speed
    clk = pi.read(ENC2_CLK)
    if clk != _enc2_last_clk and clk == 0:
        if now - _enc2_last_time > DEBOUNCE:
            time.sleep(0.001)        # small delay to let DT settle
            dt = pi.read(ENC2_DT)
            print(f"CLK=0, DT={dt}")
            if dt == 1:
                _tts_speed = min(100, _tts_speed + 5)
            else:
                _tts_speed = max(0, _tts_speed - 5)
            print(f"TTS speed: {_tts_speed}")
            _enc2_last_time = now
    _enc2_last_clk = clk
def get_volume() -> int:
    return _volume


def get_tts_speed() -> int:
    return _tts_speed