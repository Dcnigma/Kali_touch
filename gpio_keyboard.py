#!/usr/bin/env python3
import RPi.GPIO as GPIO
from pynput.keyboard import Controller, Key
import time

# Setup
GPIO.setwarnings(False)
GPIO.setmode(GPIO.BCM)

# Button pin configuration
buttons = {
    19: Key.right,
    13: Key.up,
    6: Key.down,
    5: Key.left,
    26: Key.esc  # Home button mapped to ESC
}

for pin in buttons:
    GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)

keyboard = Controller()
last_state = {pin: GPIO.input(pin) for pin in buttons}

try:
    while True:
        for pin, key in buttons.items():
            current_state = GPIO.input(pin)
            if last_state[pin] == GPIO.HIGH and current_state == GPIO.LOW:
                # Button just pressed
                keyboard.press(key)
                keyboard.release(key)
            last_state[pin] = current_state
        time.sleep(0.01)  # 10ms debounce
except KeyboardInterrupt:
    print("Exiting...")
finally:
    GPIO.cleanup()
