#!/usr/bin/env python3
import os
import sys
import signal
import time
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel
from PyQt6.QtCore import QTimer, Qt

print("=== DEBUG INFO ===")
print("Current working directory:", os.getcwd())
print("Plugin file path:", os.path.abspath(__file__))
print("sys.path:", sys.path)
print("Contents of plugin folder:", os.listdir(os.path.dirname(os.path.abspath(__file__))))
print("==================")

# Ensure MFRC522.py in the same folder can be imported
plugin_dir = os.path.dirname(os.path.abspath(__file__))
if plugin_dir not in sys.path:
    sys.path.insert(0, plugin_dir)

try:
    import MFRC522
except ImportError:
    MFRC522 = None
    print("MFRC522 Python library not available on this system.")
    print("Place MFRC522.py in the same folder as this plugin to read cards.")

class MFRC522Plugin(QWidget):
    def __init__(self, parent=None, apps=None, cfg=None):
        super().__init__(parent)
        self.apps = apps
        self.cfg = cfg
        self.setWindowTitle("RFID Reader")
        self.setGeometry(100, 100, 800, 900)  # window size 800x900

        layout = QVBoxLayout()
        self.label = QLabel("No card detected", self)
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.label)
        self.setLayout(layout)

        self.continue_reading = True

        if MFRC522 is not None:
            self.reader = MFRC522.MFRC522()
            self.timer = QTimer()
            self.timer.timeout.connect(self.read_card)
            self.timer.start(200)  # check every 200ms
        else:
            self.reader = None

        # Handle Ctrl+C if run standalone
        signal.signal(signal.SIGINT, self.end_read)

    def uidToString(self, uid):
        return "".join(format(i, '02X') for i in uid)

    def read_card(self):
        if not self.reader:
            return
        (status, TagType) = self.reader.MFRC522_Request(self.reader.PICC_REQIDL)
        if status == self.reader.MI_OK:
            (status, uid) = self.reader.MFRC522_SelectTagSN()
            if status == self.reader.MI_OK:
                uid_str = self.uidToString(uid)
                self.label.setText(f"Card detected:\n{uid_str}")
            else:
                self.label.setText("Authentication error")
        else:
            self.label.setText("No card detected")

    def end_read(self, signalnum=None, frame=None):
        self.continue_reading = False
        if hasattr(self, 'reader') and self.reader:
            self.reader.AntennaOff()
        print("Exiting RFID reader")

    # Optional: called by launcher if needed
    def on_start(self):
        if self.reader:
            self.reader.AntennaOn()
