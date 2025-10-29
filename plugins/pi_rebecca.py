#!/usr/bin/env python3
import random
import time
from pathlib import Path
from demo_opts import get_device
from PIL import Image


def main():
    # Get paths to images
    base_path = Path(__file__).resolve().parent / 'oLed/rebecca/faces_rebecca'
    img_left = Image.open(base_path / 'LOOK_L.png').convert("RGBA")
    img_right = Image.open(base_path / 'LOOK_R.png').convert("RGBA")

    # Prepare the white background
    background = Image.new("RGBA", device.size, "white")

    # Position to center the image horizontally
    posn = ((device.width - img_left.width) // 2, 0)

    # Start loop
    current = img_left
    while True:
        # Paste current image onto background
        frame = background.copy()
        frame.paste(current, posn, current)
        device.display(frame.convert(device.mode))

        # Wait a random duration (looks more natural)
        time.sleep(random.uniform(1.5, 5.0))

        # Switch to the other image
        current = img_right if current == img_left else img_left


if __name__ == "__main__":
    try:
        device = get_device()
        main()
    except KeyboardInterrupt:
        pass
