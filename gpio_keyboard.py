#!/usr/bin/env python3
import uinput
import RPi.GPIO as GPIO
import time

# GPIO button mapping
buttons = {
    19: uinput.KEY_RIGHT,
    13: uinput.KEY_UP,
    6: uinput.KEY_DOWN,
    5: uinput.KEY_LEFT,
    26: uinput.KEY_ESC  # Home button mapped to ESC
}

# Setup uinput device
device = uinput.Device(buttons.values())

# Setup GPIO
GPIO.setwarnings(False)
GPIO.setmode(GPIO.BCM)
for pin in buttons:
    GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)

# Track last state to detect presses
last_state = {pin: GPIO.input(pin) for pin in buttons}

try:
    while True:
        for pin, key in buttons.items():
            current_state = GPIO.input(pin)
            if last_state[pin] == GPIO.HIGH and current_state == GPIO.LOW:
                # Button pressed, send key event
                device.emit_click(key)
            last_state[pin] = current_state
        time.sleep(0.01)  # debounce
except KeyboardInterrupt:
    print("Exiting...")
finally:
    GPIO.cleanup()
