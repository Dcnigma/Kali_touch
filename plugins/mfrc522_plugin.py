#!/usr/bin/env python3
# mfrc522_plugin.py

import os
import sys
import time

# --- Ensure MFRC522.py can be imported ---
current_file = os.path.abspath(__file__)
plugin_folder = os.path.dirname(current_file)
if plugin_folder not in sys.path:
    sys.path.insert(0, plugin_folder)

try:
    import MFRC522
except ImportError:
    print("MFRC522 Python library not available on this system.")
    print("Place MFRC522.py in the same folder as this plugin to read cards.")
    MFRC522 = None

# --- PyQt6 imports ---
from PyQt6.QtWidgets import QWidget, QLabel, QVBoxLayout
from PyQt6.QtCore import QTimer, Qt

class MFRC522Plugin(QWidget):
    def __init__(self, parent=None, apps=None, cfg=None):
        super().__init__(parent)
        self.setWindowTitle("RFID Reader")
        self.setFixedSize(800, 900)

        self.cfg = cfg
        self.apps = apps

        # UI elements
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

        # RFID setup
        if MFRC522:
            self.rdr = MFRC522.MFRC522()
            self.label.setText("Ready to scan RFID cards")
            self.timer = QTimer()
            self.timer.timeout.connect(self.check_card)
            self.timer.start(200)  # check every 200ms
        else:
            self.label.setText("MFRC522.py not found! Cannot read cards.")

    def check_card(self):
        if not MFRC522:
            return
        try:
            status, uid = self.rdr.MFRC522_SelectTagSN()
            if status == self.rdr.MI_OK:
                self.label.setText(f"Card detected! UID: {uid}")
            else:
                self.label.setText("No card detected")
        except Exception as e:
            self.label.setText(f"Error: {e}")
