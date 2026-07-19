import pigpio
from helper.pins import FAN


def setup_fan(pi: pigpio.pi) -> None:
    pi.set_mode(FAN, pigpio.OUTPUT)
    pi.write(FAN, pigpio.LOW)


def fan_on(pi: pigpio.pi) -> None:
    print("Fan ONN")
    pi.write(FAN, pigpio.HIGH)


def fan_off(pi: pigpio.pi) -> None:
    print("Fan Off")
    pi.write(FAN, pigpio.LOW)