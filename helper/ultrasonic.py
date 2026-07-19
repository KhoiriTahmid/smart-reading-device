import pigpio
import time
import board
import busio
import adafruit_vl53l0x
import statistics
from collections import deque
from helper.pins import ULTRA1_TRIG, ULTRA1_ECHO

# ------------------------------------------------------------------
# Dual-Stage Filter (Median + Kalman) - reusable for any distance sensor
# ------------------------------------------------------------------
class KalmanFilter1D:
    def __init__(self, process_noise, measurement_noise):
        self.q = process_noise
        self.r = measurement_noise
        self.x = 0.0      # Estimated value
        self.p = 1.0      # Estimation error covariance
        self.initialized = False

    def update(self, measurement):
        if not self.initialized:
            self.x = measurement
            self.initialized = True
            return self.x

        self.p = self.p + self.q
        k = self.p / (self.p + self.r)
        self.x = self.x + k * (measurement - self.x)
        self.p = (1 - k) * self.p
        return self.x


class DualStageFilter:
    """Median filter (rejects spikes/outliers) + Kalman filter (smooths)."""
    def __init__(self, window: int, process_noise: float, measurement_noise: float):
        self.history = deque(maxlen=window)
        self.kalman = KalmanFilter1D(process_noise, measurement_noise)

    def update(self, raw_value: float) -> float:
        self.history.append(raw_value)
        median_value = statistics.median(self.history)
        return self.kalman.update(median_value)

    def reset(self):
        self.history.clear()
        self.kalman.initialized = False
        self.kalman.p = 1.0


# Configuration for the filters
FILTER_WINDOW = 5

# Ultrasonic (HC-SR04) tends to be noisier / has occasional big spikes
# from double-echo or angled surfaces -> slightly higher R (trust raw less)
ULTRA1_KALMAN_Q = 0.05
ULTRA1_KALMAN_R = 3.0

# VL53L0X ToF is already fairly precise -> trust raw more, tighter R
ULTRA2_KALMAN_Q = 0.05
ULTRA2_KALMAN_R = 1.5

_ultra1_filter = DualStageFilter(FILTER_WINDOW, ULTRA1_KALMAN_Q, ULTRA1_KALMAN_R)
_ultra2_filter = DualStageFilter(FILTER_WINDOW, ULTRA2_KALMAN_Q, ULTRA2_KALMAN_R)

_vl53: adafruit_vl53l0x.VL53L0X | None = None

# ------------------------------------------------------------------

def setup_ultrasonic(pi: pigpio.pi) -> None:
    pi.set_mode(ULTRA1_TRIG, pigpio.OUTPUT)
    pi.write(ULTRA1_TRIG, 0)
    pi.set_mode(ULTRA1_ECHO, pigpio.INPUT)
    time.sleep(0.1)

    # global _vl53
    # i2c = busio.I2C(board.SCL, board.SDA)
    # time.sleep(0.2)  # beri waktu sensor stabil setelah power-up

    # last_err = None
    # for attempt in range(5):
    #     try:
    #         _vl53 = adafruit_vl53l0x.VL53L0X(i2c)
    #         print(f"VL53L0X initialized on attempt {attempt + 1}")
    #         return
    #     except (OSError, RuntimeError) as e:
    #         last_err = e
    #         print(f"Attempt {attempt + 1} failed: {e}")
    #         time.sleep(0.3)

    # raise RuntimeError(f"Failed to initialize VL53L0X after 5 attempts: {last_err}")


def _read_raw(pi: pigpio.pi, trig: int, echo: int) -> float | None:
    """Raw distance read (unfiltered) — returns cm or None if failed."""
    pi.write(trig, 1)
    time.sleep(0.00001)
    pi.write(trig, 0)

    timeout = time.time() + 0.04
    while pi.read(echo) == 0:
        if time.time() > timeout:
            return None

    start = time.time()
    timeout = time.time() + 0.04
    while pi.read(echo) == 1:
        if time.time() > timeout:
            return None

    return (time.time() - start) * 17150


# --- HC-SR04 (Filtered) --------------------------------------------

def read_ultra1(pi: pigpio.pi) -> float | None:
    """
    Reads the HC-SR04 sensor, applies a Median + Kalman filter,
    and returns the smooth distance in cm.
    """
    raw_cm = _read_raw(pi, ULTRA1_TRIG, ULTRA1_ECHO)
    if raw_cm is None:
        # Optional: on timeout, don't feed the filter a bad value;
        # just return the last known good estimate instead of None.
        return _ultra1_filter.kalman.x if _ultra1_filter.kalman.initialized else None

    return _ultra1_filter.update(raw_cm)


# --- VL53L0X (Filtered) ---------------------------------------------

# def read_ultra2(pi: pigpio.pi | None = None) -> float | None:
#     """
#     Reads the VL53L0X sensor, applies a Median + Kalman filter,
#     and returns the smooth distance in cm.
#     """
#     if _vl53 is None:
#         return None
#     try:
#         raw_cm = _vl53.range / 10.0  # range is in mm, convert to cm
#         return _ultra2_filter.update(raw_cm)
#     except OSError:
#         return None