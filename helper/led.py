import pigpio
from helper.pins import LED


def setup_led(pi: pigpio.pi) -> None:
    pi.set_mode(LED, pigpio.OUTPUT)
    pi.write(LED, pigpio.LOW)


def led_on(pi: pigpio.pi) -> None:
    pi.write(LED, pigpio.HIGH)


def led_off(pi: pigpio.pi) -> None:
    pi.write(LED, pigpio.LOW)