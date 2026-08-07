import logging
import pigpio
import time
import threading
import queue

from helper.pins import IN3, IN4, ENB
from helper.fan import fan_on, fan_off

logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────
PWM_FREQUENCY   = 1000
FULL_SPEED      = 255
SLOW_SPEED      = 150
SLOW_DURATION   = 5

RAMP_START_SPEED = 60
RAMP_DURATION     = 1.0
RAMP_STEPS        = 20

BOUNCE_DURATION = 2.0

# ── Shared direction state ──────────────────────────────────────────────────
_direction_lock    = threading.Lock()
_current_direction = "stopped"

motor_idle = threading.Event()
motor_idle.set()


def get_motor_direction() -> str:
    with _direction_lock:
        return _current_direction


def _set_motor_direction(direction: str) -> None:
    global _current_direction
    with _direction_lock:
        _current_direction = direction


def _duty(speed: int) -> int:
    """0-255 speed, langsung dipakai apa adanya untuk software PWM pigpio (range 0-255)."""
    return max(0, min(255, int(speed)))


def _set_direction(pi: pigpio.pi, forward: bool) -> None:
    if forward:
        pi.write(IN3, pigpio.LOW)
        pi.write(IN4, pigpio.HIGH)
        logger.info("Direction: Forward")
    else:
        pi.write(IN3, pigpio.HIGH)
        pi.write(IN4, pigpio.LOW)
        logger.info("Direction: Backward")


def setup_motor(pi: pigpio.pi) -> None:
    pi.set_mode(IN3, pigpio.OUTPUT)
    pi.set_mode(IN4, pigpio.OUTPUT)
    pi.set_PWM_frequency(ENB, PWM_FREQUENCY)   # set frekuensi software PWM
    pi.set_PWM_dutycycle(ENB, 0)               # pastikan mulai dari 0
    _set_direction(pi, forward=True)
    logger.info("Motor initialised")


def _ramp_worker(pi: pigpio.pi, start_speed: int, target_speed: int, cancel_event: threading.Event) -> None:
    step_delay = RAMP_DURATION / RAMP_STEPS

    for i in range(1, RAMP_STEPS + 1):
        if cancel_event.is_set():
            return
        speed = start_speed + (target_speed - start_speed) * i / RAMP_STEPS
        pi.set_PWM_dutycycle(ENB, _duty(int(speed)))
        time.sleep(step_delay)

    if not cancel_event.is_set():
        logger.info(f"Motor: ramp complete ({target_speed}/255)")


def motor_worker(pi: pigpio.pi, motor_queue: queue.Queue) -> None:
    slow_timer: threading.Timer | None = None
    ramp_cancel: threading.Event | None = None

    def bounce() -> None:
        cancel_timer()
        cancel_ramp()

        current = get_motor_direction()

        if current == "stopped":
            logger.info("Motor: cannot bounce while stopped")
            return

        motor_idle.clear()

        opposite = "backward" if current == "forward" else "forward"

        logger.info(f"Motor: bounce ({current} -> {opposite})")

        _set_direction(pi, forward=(opposite == "forward"))
        pi.set_PWM_dutycycle(ENB, _duty(RAMP_START_SPEED))
        start_ramp(RAMP_START_SPEED, FULL_SPEED)

        time.sleep(BOUNCE_DURATION)

        logger.info(f"Motor: returning to {current}")

        _set_direction(pi, forward=(current == "forward"))
        pi.set_PWM_dutycycle(ENB, _duty(RAMP_START_SPEED))
        start_ramp(RAMP_START_SPEED, FULL_SPEED)

    def cancel_timer() -> None:
        nonlocal slow_timer
        if slow_timer is not None:
            slow_timer.cancel()
            slow_timer = None

    def cancel_ramp() -> None:
        nonlocal ramp_cancel
        if ramp_cancel is not None:
            ramp_cancel.set()
            ramp_cancel = None

    def start_ramp(start_speed: int, target_speed: int) -> None:
        nonlocal ramp_cancel
        cancel_ramp()
        ramp_cancel = threading.Event()
        threading.Thread(
            target=_ramp_worker,
            args=(pi, start_speed, target_speed, ramp_cancel),
            name="motor_ramp",
            daemon=True,
        ).start()

    def stop_motor(hard: bool = False) -> None:
        cancel_timer()
        cancel_ramp()
        pi.set_PWM_dutycycle(ENB, 0)
        if hard:
            pi.write(IN3, pigpio.LOW)
            pi.write(IN4, pigpio.LOW)
        # fan_off(pi)
        _set_motor_direction("stopped")
        motor_idle.set()
        logger.info("Motor: hard stop" if hard else "Motor: stop")

    def drive(forward: bool) -> None:
        cancel_timer()
        cancel_ramp()
        motor_idle.clear()
        _set_direction(pi, forward=forward)
        pi.set_PWM_dutycycle(ENB, _duty(RAMP_START_SPEED))
        if not forward:
            fan_off(pi)
        _set_motor_direction("forward" if forward else "backward")
        logger.info(f"Motor: {'forward' if forward else 'backward'}, ramping {RAMP_START_SPEED} -> {FULL_SPEED}")
        start_ramp(RAMP_START_SPEED, FULL_SPEED)

    while True:
        try:
            cmd = motor_queue.get(timeout=0.1)
        except queue.Empty:
            continue

        logger.info(f"Motor cmd: {cmd}")

        if cmd == "full":
            cancel_timer()
            cancel_ramp()
            pi.set_PWM_dutycycle(ENB, _duty(FULL_SPEED))
            logger.info(f"Motor: full ({FULL_SPEED}/255)")

        elif cmd == "slow":
            cancel_timer()
            cancel_ramp()
            fan_on(pi)
            pi.set_PWM_dutycycle(ENB, _duty(SLOW_SPEED))
            logger.info(f"Motor: slow ({SLOW_SPEED}/255)")
            slow_timer = threading.Timer(SLOW_DURATION, lambda: motor_queue.put("full"))
            slow_timer.daemon = True
            slow_timer.start()

        elif cmd == "bounce":
            bounce()

        elif cmd == "stop":
            stop_motor(hard=False)

        elif cmd == "forward":
            drive(forward=True)

        elif cmd == "backward":
            drive(forward=False)

        elif cmd == "hard_stop":
            stop_motor(hard=True)

        elif cmd == "quit":
            stop_motor(hard=True)
            break