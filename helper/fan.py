import logging

import pigpio
from helper.pins import FAN

logger = logging.getLogger(__name__)


def setup_fan(pi: pigpio.pi) -> None:
    pi.set_mode(FAN, pigpio.OUTPUT)
    pi.write(FAN, pigpio.LOW)


def fan_on(pi: pigpio.pi) -> None:
    logger.info("Fan on")
    pi.write(FAN, pigpio.HIGH)


def fan_off(pi: pigpio.pi) -> None:
    logger.info("Fan off")
    pi.write(FAN, pigpio.LOW)