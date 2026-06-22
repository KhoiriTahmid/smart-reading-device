import pigpio
import time

from helper.led import setup_led, led_on, led_off


def main():
    pi = pigpio.pi()

    if not pi.connected:
        print("Failed to connect to pigpio daemon")
        return

    setup_led(pi)

    try:
        print("LED test started. Press Ctrl+C to stop.\n")
        while True:
            print("LED ON")
            led_on(pi)
            time.sleep(100)

            # print("LED OFF")
            # led_off(pi)
            # time.sleep(1)

    except KeyboardInterrupt:
        print("\nStopped")

    finally:
        led_off(pi)
        pi.stop()


if __name__ == "__main__":
    main()