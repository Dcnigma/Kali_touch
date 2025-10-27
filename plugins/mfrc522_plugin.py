#!/usr/bin/env python3
# mfrc522_plugin.py

import os
import sys
import time
import signal

# Ensure MFRC522.py can be imported
plugin_folder = os.path.dirname(os.path.abspath(__file__))
if plugin_folder not in sys.path:
    sys.path.insert(0, plugin_folder)

try:
    import MFRC522
except ImportError:
    print("MFRC522 Python library not available on this system.")
    print("Place MFRC522.py in the same folder as this plugin to read cards.")
    MFRC522 = None

from PyQt6.QtWidgets import QWidget, QLabel, QVBoxLayout
from PyQt6.QtCore import QTimer, Qt

class MFRC522Plugin(QWidget):
    def __init__(self, parent=None, apps=None, cfg=None):
        super().__init__(parent)
        self.setWindowTitle("RFID Reader")
        self.setFixedSize(800, 900)

        self.cfg = cfg
        self.apps = apps

        # UI
        self.label = QLabel("Initializing...", self)
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout = QVBoxLayout()
        layout.addWidget(self.label)
        self.setLayout(layout)

        # Debug info
        print("=== DEBUG INFO ===")
        print("Current working directory:", os.getcwd())
        print("Plugin folder:", plugin_folder)
        print("sys.path:", sys.path)
        print("Contents of plugin folder:", os.listdir(plugin_folder))
        print("==================")

        if MFRC522:
            self.MIFAREReader = MFRC522.MFRC522()
            self.label.setText("Ready to scan RFID cards")

            # Timer to repeatedly check for cards
            self.timer = QTimer()
            self.timer.timeout.connect(self.check_card)
            self.timer.start(200)  # check every 200ms
        else:
            self.label.setText("MFRC522.py not found! Cannot read cards.")

    def uidToString(self, uid):
        return ''.join(format(i, '02X') for i in uid)

    def check_card(self):
        if not MFRC522:
            return
        try:
            # Scan for cards (original code logic)
            (status, TagType) = self.MIFAREReader.MFRC522_Request(self.MIFAREReader.PICC_REQIDL)

            if status == self.MIFAREReader.MI_OK:
                # Card detected, now get UID
                (status, uid) = self.MIFAREReader.MFRC522_SelectTagSN()
                if status == self.MIFAREReader.MI_OK:
                    self.label.setText(f"Card detected! UID: {self.uidToString(uid)}")
                else:
                    self.label.setText("Card detected but UID read failed")
            else:
                self.label.setText("No card detected")
        except Exception as e:
            self.label.setText(f"Error: {e}")
