import uinput
import RPi.GPIO as GPIO
import time

buttons = {
    19: uinput.KEY_RIGHT,
    13: uinput.KEY_UP,
    6: uinput.KEY_DOWN,
    5: uinput.KEY_LEFT,
    26: uinput.KEY_ESC
}

device = uinput.Device(buttons)

GPIO.setmode(GPIO.BCM)
GPIO.setup(list(buttons.keys()), GPIO.IN, pull_up_down=GPIO.PUD_UP)

last_state = {pin: GPIO.input(pin) for pin in buttons}

while True:
    for pin, key in buttons.items():
        current_state = GPIO.input(pin)
        if last_state[pin] == GPIO.HIGH and current_state == GPIO.LOW:
            device.emit_click(key)
        last_state[pin] = current_state
    time.sleep(0.01)
