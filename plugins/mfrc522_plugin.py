#!/usr/bin/env python3
import sys
import os
import time
import threading
import signal
from PyQt6.QtWidgets import QApplication, QWidget, QVBoxLayout, QLabel
from PyQt6.QtCore import QTimer, Qt

# Try to import MFRC522
try:
    import MFRC522
    MFRC522_AVAILABLE = True
except ImportError:
    MFRC522_AVAILABLE = False
    print("MFRC522 Python library not available on this system.")
    print("Place MFRC522.py in the same folder as this plugin to read cards.")

# Helper to convert UID to string
def uidToString(uid):
    return ''.join(format(i, '02X') for i in uid)

# Plugin / UI Class
class MFRC522Plugin(QWidget):
    def __init__(self, parent=None, apps=None, cfg=None):
        super().__init__(parent)
        self.setWindowTitle("RFID Reader")
        self.setGeometry(100, 100, 800, 900)

        # UI
        layout = QVBoxLayout()
        self.label = QLabel("No card detected")
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setStyleSheet("font-size: 28px;")
        layout.addWidget(self.label)
        self.setLayout(layout)

        self.continue_reading = True
        self.mifare = None
        if MFRC522_AVAILABLE:
            self.mifare = MFRC522.MFRC522()

        # Timer for polling cards
        self.timer = QTimer()
        self.timer.timeout.connect(self.check_card)
        self.timer.start(300)  # check every 300 ms

    def check_card(self):
        if not self.mifare:
            return
        (status, _) = self.mifare.MFRC522_Request(self.mifare.PICC_REQIDL)
        if status == self.mifare.MI_OK:
            (status, uid) = self.mifare.MFRC522_SelectTagSN()
            if status == self.mifare.MI_OK:
                self.label.setText(f"Card detected!\nUID: {uidToString(uid)}")
            else:
                self.label.setText("Authentication error")
        else:
            self.label.setText("No card detected")

# Standalone launcher
if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MFRC522Plugin()
    window.show()
    sys.exit(app.exec())
