import pigpio
import time

from helper.button import (
    setup_buttons,
    read_btn1,
    read_btn2,
    read_btn3,
    read_btn4,
    read_btn5,
    read_btn6,
)

from helper.limit_switch import (
    setup_limit_switches,
    read_limit_sw1,
    read_limit_sw2,
)

from helper.switch import (
    setup_switches,
    read_sw1,
    read_sw2_language,
)

# from helper.ultrasonic import (
#     setup_ultrasonic,
#     read_ultra1,
#     read_ultra2,
# )

from helper.encoder import (
    setup_encoders,
    read_encoders,
    get_volume,
    get_tts_speed,
)


def main():
    pi = pigpio.pi()

    if not pi.connected:
        print("Failed to connect to pigpio daemon")
        return

    setup_buttons(pi)
    setup_limit_switches(pi)
    setup_switches(pi)
    # setup_ultrasonic(pi)
    setup_encoders(pi)

    print("=== Hardware Test Started ===")
    print("Press Ctrl+C to exit\n")

    last_volume = get_volume()
    last_speed = get_tts_speed()

    try:
        while True:

            # ---------- Buttons ----------
            if read_btn1(pi):
                print("BTN1 PRESSED")

            if read_btn2(pi):
                print("BTN2 PRESSED")

            if read_btn3(pi):
                print("BTN3 PRESSED")

            if read_btn4(pi):
                print("BTN4 PRESSED")

            if read_btn5(pi):
                print("BTN5 PRESSED")

            if read_btn6(pi):
                print("BTN6 PRESSED")

            # ---------- Limit Switch ----------
            if read_limit_sw1(pi):
                print("LIMIT SW1 PRESSED")

            if read_limit_sw2(pi):
                print("LIMIT SW2 PRESSED")

            # ---------- Toggle Switch ----------
            sw1 = read_sw1(pi)
            lang = read_sw2_language(pi)

            # ---------- Encoder ----------
            read_encoders(pi)

            volume = get_volume()
            speed = get_tts_speed()

            if volume != last_volume:
                print(f"VOLUME = {volume}")
                last_volume = volume

            if speed != last_speed:
                print(f"TTS SPEED = {speed}")
                last_speed = speed

            # ---------- Ultrasonic ----------
            # d1 = read_ultra1(pi)
            # d2 = read_ultra2(pi)

            # print(
            #     f"\rSW1={'ON' if sw1 else 'OFF'} | "
            #     f"LANG={lang} | "
            #     f"ULTRA1={d1}cm | "
            #     f"ULTRA2={d2}cm",
            #     end="",
            #     flush=True
            # )

            time.sleep(0.1)

    except KeyboardInterrupt:
        print("\nStopped")

    finally:
        pi.stop()


if __name__ == "__main__":
    main()