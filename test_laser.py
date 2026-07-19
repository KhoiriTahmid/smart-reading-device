#!/usr/bin/env python3

import time
import pigpio

from helper.ultrasonic import setup_ultrasonic, read_ultra2

# ------------------------------------------------------------------
# Config
# ------------------------------------------------------------------

ULTRA2_SLOW_CM = 5.0
ULTRA2_INTERVAL = 0.1

# Stuck detector
STUCK_TIME = 2.0          # seconds without significant movement
STUCK_TOLERANCE = 1.0     # cm before considering we've moved

MOTOR_STATE = "forward"

# ------------------------------------------------------------------

def fake_motor_put(cmd: str):
    print(f"  [motor_queue]   -> {cmd}")

def fake_speaker_put(cmd: str):
    print(f"  [speaker_queue] -> {cmd}")

def main():
    pi = pigpio.pi()

    if not pi.connected:
        raise RuntimeError(
            "Cannot connect to pigpiod. Run:\n"
            "sudo systemctl start pigpiod"
        )

    setup_ultrasonic(pi)

    print("Ultra2 Stuck Detection Test (Pre-Filtered)")
    print(f"Motor state : {MOTOR_STATE}")
    print(f"Stuck time  : {STUCK_TIME}s")
    print(f"Tolerance   : {STUCK_TOLERANCE} cm\n")

    last_slow_print = 0

    # Stuck detector variables
    reference_distance = None
    no_progress_since = None
    stuck_reported = False

    try:
        while True:
            # This is now returning the smooth, Kalman-filtered value automatically!
            distance = read_ultra2(pi)

            if distance is None:
                time.sleep(ULTRA2_INTERVAL)
                continue
                
            print(f"Distance: {distance:5.1f} cm")

            # ==========================================================
            # STUCK DETECTION
            # ==========================================================
            if MOTOR_STATE in ("forward", "backward"):
                now = time.time()

                if reference_distance is None:
                    reference_distance = distance
                    no_progress_since = now

                else:
                    movement = abs(distance - reference_distance)

                    if movement >= STUCK_TOLERANCE:
                        # Significant movement detected.
                        reference_distance = distance
                        no_progress_since = now
                        stuck_reported = False

                    else:
                        elapsed = now - no_progress_since

                        if elapsed >= STUCK_TIME and not stuck_reported:
                            print(f">>> STUCK DETECTED <<< (no movement for {elapsed:.1f}s)")
                            fake_motor_put("stop")
                            fake_speaker_put("stuck")
                            stuck_reported = True
            else:
                reference_distance = None
                no_progress_since = None
                stuck_reported = False

            # ==========================================================
            # SLOW DETECTION
            # ==========================================================
            if MOTOR_STATE == "forward":
                if distance < ULTRA2_SLOW_CM:
                    now = time.time()
                    if now - last_slow_print > 1:
                        print(f">>> SLOW <<< ({distance:.1f} cm)")
                        fake_motor_put("slow")
                        last_slow_print = now

            time.sleep(ULTRA2_INTERVAL)

    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        pi.stop()


if __name__ == "__main__":
    main()