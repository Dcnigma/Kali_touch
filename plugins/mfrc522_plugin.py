#!/usr/bin/env python3
# mfrc522_plugin.py

import os
import sys
import time

# Make sure MFRC522.py is in the same folder
try:
    from MFRC522 import MFRC522
except ImportError:
    print("MFRC522 Python library not available on this system.")
    print("Place MFRC522.py in the same folder as this plugin to read cards.")
    MFRC522 = None

# Only proceed if MFRC522 is available
if MFRC522:
    # Initialize the reader
    reader = MFRC522()

    def uidToString(uid):
        """Convert UID list to hex string."""
        return ''.join(format(x, '02X') for x in uid)

    def scan_card():
        """Scan for a card once and return UID string if found."""
        status, _ = reader.MFRC522_Request(reader.PICC_REQIDL)
        if status == reader.MI_OK:
            status, uid = reader.MFRC522_SelectTagSN()
            if status == reader.MI_OK:
                return uidToString(uid)
        return None

    # This is an example function for the plugin UI to call repeatedly
    def plugin_loop(update_ui_callback):
        """
        Call this function repeatedly from your plugin main loop.
        update_ui_callback should be a function that takes the UID string
        or None if no card is present.
        """
        while True:
            uid = scan_card()
            if uid:
                update_ui_callback(uid)
            time.sleep(0.1)  # Adjust scan frequency as needed
