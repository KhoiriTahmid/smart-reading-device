import pigpio
import time
import threading
import queue

from helper.pins import IN3, IN4, ENB
from helper.fan import fan_on, fan_off

# ── Config ────────────────────────────────────────────────────────────────
PWM_FREQUENCY   = 1000
FULL_SPEED      = 255
SLOW_SPEED      = 150
SLOW_DURATION   = 5      # seconds before auto-resuming to full after "slow"

RAMP_START_SPEED = 60    # initial duty on forward/backward (overcomes stall torque)
RAMP_DURATION     = 1.0  # seconds to ramp RAMP_START_SPEED -> FULL_SPEED
RAMP_STEPS        = 20   # PWM updates during the ramp

BOUNCE_DURATION = 2.0

# ── Shared direction state ──────────────────────────────────────────────────
_direction_lock    = threading.Lock()
_current_direction = "stopped"  # "forward" | "backward" | "stopped"


def get_motor_direction() -> str:
    with _direction_lock:
        return _current_direction


def _set_motor_direction(direction: str) -> None:
    global _current_direction
    with _direction_lock:
        _current_direction = direction


def _duty(speed: int) -> int:
    """Convert a 0-255 speed value into a pigpio hardware_PWM duty (0-1,000,000)."""
    return int(speed / 255 * 1_000_000)


def _set_direction(pi: pigpio.pi, forward: bool) -> None:
    if forward:
        pi.write(IN3, pigpio.LOW)
        pi.write(IN4, pigpio.HIGH)
        print("Direction: Forward")
    else:
        pi.write(IN3, pigpio.HIGH)
        pi.write(IN4, pigpio.LOW)
        print("Direction: Backward")


def setup_motor(pi: pigpio.pi) -> None:
    pi.set_mode(IN3, pigpio.OUTPUT)
    pi.set_mode(IN4, pigpio.OUTPUT)
    _set_direction(pi, forward=True)
    print("Motor initialised")


def _ramp_worker(pi: pigpio.pi, start_speed: int, target_speed: int, cancel_event: threading.Event) -> None:
    """Steps PWM duty from start_speed to target_speed. Exits early if cancelled."""
    step_delay = RAMP_DURATION / RAMP_STEPS

    for i in range(1, RAMP_STEPS + 1):
        if cancel_event.is_set():
            return
        speed = start_speed + (target_speed - start_speed) * i / RAMP_STEPS
        pi.hardware_PWM(ENB, PWM_FREQUENCY, _duty(int(speed)))
        time.sleep(step_delay)

    if not cancel_event.is_set():
        print(f"Motor: ramp complete ({target_speed}/255)")


def motor_worker(pi: pigpio.pi, motor_queue: queue.Queue) -> None:
    """
    Permanent thread — only function that touches motor hardware.
    Commands: full, slow, stop, forward, backward, hard_stop, quit
    """
    slow_timer: threading.Timer | None = None
    ramp_cancel: threading.Event | None = None
    def bounce() -> None:
        cancel_timer()
        cancel_ramp()

        current = get_motor_direction()

        if current == "stopped":
            print("Motor: cannot bounce while stopped")
            return

        opposite = "backward" if current == "forward" else "forward"

        print(f"Motor: bounce ({current} -> {opposite})")

        _set_direction(pi, forward=(opposite == "forward"))
        pi.hardware_PWM(ENB, PWM_FREQUENCY, _duty(RAMP_START_SPEED))
        start_ramp(RAMP_START_SPEED, FULL_SPEED)

        time.sleep(BOUNCE_DURATION)

        print(f"Motor: returning to {current}")

        _set_direction(pi, forward=(current == "forward"))
        pi.hardware_PWM(ENB, PWM_FREQUENCY, _duty(RAMP_START_SPEED))
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
            daemon=True,
        ).start()

    def stop_motor(hard: bool = False) -> None:
        cancel_timer()
        cancel_ramp()
        pi.hardware_PWM(ENB, PWM_FREQUENCY, 0)
        if hard:
            pi.write(IN3, pigpio.LOW)
            pi.write(IN4, pigpio.LOW)
        fan_off(pi)
        _set_motor_direction("stopped")
        print("Motor: hard stop" if hard else "Motor: stop")

    def drive(forward: bool) -> None:
        cancel_timer()
        cancel_ramp()
        _set_direction(pi, forward=forward)
        pi.hardware_PWM(ENB, PWM_FREQUENCY, _duty(RAMP_START_SPEED))
        if(not forward):
            fan_off(pi)
        _set_motor_direction("forward" if forward else "backward")
        print(f"Motor: {'forward' if forward else 'backward'}, ramping {RAMP_START_SPEED} -> {FULL_SPEED}")
        start_ramp(RAMP_START_SPEED, FULL_SPEED)

    while True:
        try:
            cmd = motor_queue.get(timeout=0.1)
        except queue.Empty:
            continue

        print(f"Motor cmd: {cmd}")

        if cmd == "full":
            cancel_timer()
            cancel_ramp()
            pi.hardware_PWM(ENB, PWM_FREQUENCY, _duty(FULL_SPEED))
            print(f"Motor: full ({FULL_SPEED}/255)")

        elif cmd == "slow":
            cancel_timer()
            cancel_ramp()
            fan_on(pi) #skema terbaik, need worst case too
            pi.hardware_PWM(ENB, PWM_FREQUENCY, _duty(SLOW_SPEED))
            print(f"Motor: slow ({SLOW_SPEED}/255)")
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