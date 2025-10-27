#!/usr/bin/env python3
import os
import sys
import time

# --------------------- Ensure plugin folder is in sys.path ---------------------
plugin_folder = os.path.dirname(os.path.abspath(__file__))
if plugin_folder not in sys.path:
    sys.path.insert(0, plugin_folder)

# --------------------- Import MFRC522 ---------------------
try:
    import MFRC522
except ImportError:
    print("MFRC522 Python library not available on this system.")
    print("Place MFRC522.py in the same folder as this plugin to read cards.")
    MFRC522 = None

# --------------------- PyQt6 imports ---------------------
from PyQt6.QtWidgets import QWidget, QLabel, QVBoxLayout, QApplication
from PyQt6.QtCore import QTimer, Qt

# --------------------- Plugin Class ---------------------
class MFRC522Plugin(QWidget):
    def __init__(self, parent=None, apps=None, cfg=None):
        super().__init__(parent)
        self.cfg = cfg
        self.setWindowTitle("MFRC522 Reader")
        self.setFixedSize(800, 900)

        # UI
        self.label = QLabel("Initializing...", self)
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout = QVBoxLayout()
        layout.addWidget(self.label)
        self.setLayout(layout)

        # Card reader
        if MFRC522:
            self.reader = MFRC522.MFRC522()
        else:
            self.reader = None
            self.label.setText("MFRC522.py not found. Cannot read cards.")

        # Timer to poll cards
        self.timer = QTimer()
        self.timer.timeout.connect(self.poll_card)
        self.timer.start(500)  # every 0.5s

        # Debug
        print("=== DEBUG INFO ===")
        print("Current working directory:", os.getcwd())
        print("Plugin folder:", plugin_folder)
        print("sys.path:", sys.path)
        print("Contents of plugin folder:", os.listdir(plugin_folder))
        print("==================")

    # --------------------- Helper ---------------------
    def uidToString(self, uid):
        return ''.join(format(i, '02X') for i in uid)

    # --------------------- Poll card ---------------------
    def poll_card(self):
        if not self.reader:
            return

        (status, TagType) = self.reader.MFRC522_Request(self.reader.PICC_REQIDL)
        if status != self.reader.MI_OK:
            self.label.setText("No card detected")
            return

        (status, uid) = self.reader.MFRC522_SelectTagSN()
        if status == self.reader.MI_OK:
            uid_str = self.uidToString(uid)
            self.label.setText(f"Card detected:\n{uid_str}")
        else:
            self.label.setText("Authentication error")
