#!/usr/bin/env python3
import uinput
import RPi.GPIO as GPIO
import time
import json
import os
import threading
from pathlib import Path
import sys

CONFIG_FILE = Path("/home/kali/overlay_launcher/gpio_keyboard_config.json")
RELOAD_INTERVAL = 0.5  # seconds

# Default configuration
default_config = {
    "buttons": {
        "19": {"key": "KEY_RIGHT", "mode": "single"},
        "13": {"key": "KEY_UP", "mode": "single"},
        "6": {"key": "KEY_DOWN", "mode": "hold"},
        "5": {"key": "KEY_LEFT", "mode": "hold"},
        "26": {"key": "KEY_ESC", "mode": "single"}
    },
    "hold_repeat_delay": 0.2
}

# Map string key names to uinput constants
KEY_MAP = {
    "KEY_RIGHT": uinput.KEY_RIGHT,
    "KEY_LEFT": uinput.KEY_LEFT,
    "KEY_UP": uinput.KEY_UP,
    "KEY_DOWN": uinput.KEY_DOWN,
    "KEY_ESC": uinput.KEY_ESC
}

# Load or create config
def load_config():
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r") as f:
                cfg = json.load(f)
            # Validate keys
            for pin, val in cfg["buttons"].items():
                if val["key"] not in KEY_MAP:
                    print(f"Unknown key in config: {val['key']}")
                    cfg["buttons"][pin]["key"] = "KEY_ESC"
                if val["mode"] not in ("single", "hold"):
                    cfg["buttons"][pin]["mode"] = "single"
            return cfg
        except Exception as e:
            print(f"Error loading config: {e}, using default.")
            return default_config
    else:
        with open(CONFIG_FILE, "w") as f:
            json.dump(default_config, f, indent=4)
        return default_config

config = load_config()

# Setup GPIO and uinput
buttons = {int(pin): KEY_MAP[val["key"]] for pin, val in config["buttons"].items()}
modes = {int(pin): val["mode"] for pin, val in config["buttons"].items()}

device = uinput.Device(buttons.values())

GPIO.setwarnings(False)
GPIO.setmode(GPIO.BCM)
for pin in buttons:
    GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)

last_state = {pin: GPIO.input(pin) for pin in buttons}
hold_timers = {pin: 0 for pin in buttons}

# Watch for config changes
def watch_config():
    global config, buttons, modes
    last_mtime = CONFIG_FILE.stat().st_mtime
    while True:
        time.sleep(RELOAD_INTERVAL)
        try:
            mtime = CONFIG_FILE.stat().st_mtime
            if mtime != last_mtime:
                print("Config file changed, reloading...")
                last_mtime = mtime
                new_cfg = load_config()
                # Update buttons and modes
                for pin, val in new_cfg["buttons"].items():
                    buttons[int(pin)] = KEY_MAP[val["key"]]
                    modes[int(pin)] = val["mode"]
                config = new_cfg
        except Exception as e:
            print(f"Error watching config: {e}")

# Start config watcher thread
threading.Thread(target=watch_config, daemon=True).start()

try:
    while True:
        now = time.time()
        for pin, key in buttons.items():
            current_state = GPIO.input(pin)

            # SINGLE PRESS MODE
            if modes[pin] == "single":
                if last_state[pin] == GPIO.HIGH and current_state == GPIO.LOW:
                    device.emit_click(key)

            # HOLD MODE (repeat while held)
            elif modes[pin] == "hold":
                if current_state == GPIO.LOW:
                    if now - hold_timers[pin] > config.get("hold_repeat_delay", 0.2):
                        device.emit_click(key)
                        hold_timers[pin] = now
                else:
                    hold_timers[pin] = now

            last_state[pin] = current_state

        time.sleep(0.01)

except KeyboardInterrupt:
    print("Exiting...")
finally:
    GPIO.cleanup()
    sys.exit(0)
