import logging

from pigpio_encoder.rotary import Rotary

from helper.pins import ENC1_CLK, ENC1_DT, ENC2_CLK, ENC2_DT

logger = logging.getLogger(__name__)

Rotary.sw_gpio = None

_volume    = 80
_tts_speed = 50

_rotary1: Rotary | None = None
_rotary2: Rotary | None = None


def _on_volume_change(counter: int) -> None:
    global _volume

    if counter > _volume and _speaker_queue:
        _speaker_queue.put("beep_up")
    elif counter < _volume and _speaker_queue:
        _speaker_queue.put("beep_down")

    _volume = counter
    logger.info(f"Volume: {_volume}")


def _on_tts_speed_change(counter: int) -> None:
    global _tts_speed

    if counter > _tts_speed and _speaker_queue:
        _speaker_queue.put("beep_up")
    elif counter < _tts_speed and _speaker_queue:
        _speaker_queue.put("beep_down")

    _tts_speed = counter
    logger.info(f"TTS speed: {_tts_speed}")


def setup_encoders(pi=None, speaker_queue=None):
    """
    `pi` is accepted but unused — pigpio_encoder.Rotary() opens its
    own internal pigpio.pi() connection, so it doesn't reuse an
    existing one. Kept as a param so call sites elsewhere don't break.
    """
    global _rotary1, _rotary2, _speaker_queue

    _speaker_queue = speaker_queue

    _rotary1 = Rotary(clk_gpio=ENC1_CLK, dt_gpio=ENC1_DT)
    _rotary1.setup_rotary(
        min=0,
        max=100,
        scale=5,
        debounce=1000,          # microseconds — raise if still noisy
        rotary_callback=_on_volume_change,
    )
    _rotary1.counter = _volume  # seed to current default so it doesn't jump on first turn

    _rotary2 = Rotary(clk_gpio=ENC2_CLK, dt_gpio=ENC2_DT)
    _rotary2.setup_rotary(
        min=0,
        max=100,
        scale=5,
        debounce=1000,
        rotary_callback=_on_tts_speed_change,
    )
    _rotary2.counter = _tts_speed


def get_volume() -> int:
    return _volume


def get_tts_speed() -> int:
    return _tts_speed


def read_encoders(pi=None) -> None:
    """
    No-op kept for backward compatibility with old polling-based call sites.
    Values now update automatically via pigpio callbacks — nothing to do here.
    """
    pass