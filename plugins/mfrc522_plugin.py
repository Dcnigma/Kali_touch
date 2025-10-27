#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import os
import signal
import time
from PyQt6.QtWidgets import QApplication, QWidget, QLabel, QVBoxLayout
from PyQt6.QtCore import QTimer, Qt

# Ensure plugin folder is in sys.path so MFRC522.py can be imported
plugin_folder = os.path.dirname(os.path.abspath(__file__))
if plugin_folder not in sys.path:
    sys.path.insert(0, plugin_folder)

try:
    import MFRC522
except ImportError:
    print("MFRC522 Python library not available on this system.")
    print("Place MFRC522.py in the same folder as this plugin to read cards.")
    MFRC522 = None

# Function to convert UID to string
def uidToString(uid):
    return ''.join(format(i, '02X') for i in uid)

# Flag to control reading loop
continue_reading = True

# Capture SIGINT to cleanly stop
def end_read(signal_received, frame):
    global continue_reading
    print("Ctrl+C captured, ending read.")
    continue_reading = False

signal.signal(signal.SIGINT, end_read)

class MFRC522Plugin(QWidget):
    def __init__(self, parent=None, apps=None, cfg=None):
        super().__init__(parent)
        self.setWindowTitle("RFID Reader")
        self.resize(800, 900)

        # Layout and label
        layout = QVBoxLayout()
        self.label = QLabel("No card detected")
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setStyleSheet("font-size: 24px;")
        layout.addWidget(self.label)
        self.setLayout(layout)

        self.cfg = cfg
        self.apps = apps

        # Setup reader if available
        if MFRC522:
            self.reader = MFRC522.MFRC522()
        else:
            self.reader = None
            self.label.setText("MFRC522 library not found!")

        # Timer to poll for cards every 200ms
        self.timer = QTimer()
        self.timer.timeout.connect(self.poll_card)
        self.timer.start(200)

    def poll_card(self):
        if not self.reader:
            return

        (status, _) = self.reader.MFRC522_Request(self.reader.PICC_REQIDL)
        if status == self.reader.MI_OK:
            (status, uid) = self.reader.MFRC522_SelectTagSN()
            if status == self.reader.MI_OK:
                self.label.setText(f"Card detected!\nUID: {uidToString(uid)}")
            else:
                self.label.setText("Authentication error")
        else:
            self.label.setText("No card detected")


# Standalone mode
if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MFRC522Plugin()
    window.show()
    sys.exit(app.exec())
