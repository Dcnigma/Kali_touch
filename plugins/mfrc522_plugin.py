# plugins/mfrc522_plugin.py
import os
import signal
import sys
import threading
import datetime
from typing import Optional, List

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTextEdit, QPushButton, QMessageBox
)
from PyQt6.QtCore import Qt

try:
    import MFRC522  # use local MFRC522.py
    MFRC522_AVAILABLE = True
except ImportError:
    MFRC522_AVAILABLE = False


class MFRC522Plugin(QWidget):
    name = "MFRC522 Reader"
    description = "Read RFID card UIDs via MFRC522"

    def __init__(self, parent=None, apps: Optional[dict] = None, cfg: Optional[dict] = None):
        super().__init__(parent)
        self.apps = apps or {}
        self.cfg = cfg or {}

        self.setWindowTitle(self.name)
        self.setFixedSize(900, 800)

        layout = QVBoxLayout()
        layout.setSpacing(10)
        layout.setContentsMargins(16, 16, 16, 16)

        header = QLabel("MFRC522 RFID Reader")
        header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header.setStyleSheet("font-size: 24px; font-weight: bold;")
        layout.addWidget(header)

        self.output = QTextEdit()
        self.output.setReadOnly(True)
        self.output.setStyleSheet("font-size: 16px;")
        layout.addWidget(self.output)

        btn_row = QHBoxLayout()
        self.start_btn = QPushButton("Start Reading")
        self.start_btn.setStyleSheet("font-size: 18px; background-color:#2e8b57; color:white;")
        self.start_btn.clicked.connect(self.start_reading)
        btn_row.addWidget(self.start_btn)

        self.stop_btn = QPushButton("Stop Reading")
        self.stop_btn.setStyleSheet("font-size: 18px; background-color:#b22222; color:white;")
        self.stop_btn.clicked.connect(self.stop_reading)
        self.stop_btn.setEnabled(False)
        btn_row.addWidget(self.stop_btn)

        layout.addLayout(btn_row)

        self.setLayout(layout)

        # Reading thread
        self.continue_reading = False
        self.read_thread: Optional[threading.Thread] = None

        if not MFRC522_AVAILABLE:
            self.append("MFRC522 Python library not found. Place MFRC522.py in the same folder to read cards.\n")

    def append(self, text: str):
        self.output.insertPlainText(text)
        self.output.verticalScrollBar().setValue(self.output.verticalScrollBar().maximum())

    # ---------- Card reading logic ----------
    def uid_to_string(self, uid: List[int]) -> str:
        return "".join(format(i, "02X") for i in uid)

    def read_loop(self):
        if not MFRC522_AVAILABLE:
            return

        reader = MFRC522.MFRC522()
        self.append("Ready to read cards. Press Stop to end.\n")

        while self.continue_reading:
            (status, _) = reader.MFRC522_Request(reader.PICC_REQIDL)
            if status == reader.MI_OK:
                self.append("Card detected\n")
                (status, uid) = reader.MFRC522_SelectTagSN()
                if status == reader.MI_OK:
                    self.append(f"Card read UID: {self.uid_to_string(uid)}\n\n")
                else:
                    self.append("Authentication error\n")
            # avoid busy loop
            import time
            time.sleep(0.5)

        self.append("Stopped reading.\n")

    def start_reading(self):
        if not MFRC522_AVAILABLE:
            QMessageBox.warning(self, "Missing library", "MFRC522.py not found. Cannot read cards.")
            return
        self.continue_reading = True
        self.read_thread = threading.Thread(target=self.read_loop, daemon=True)
        self.read_thread.start()
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)

    def stop_reading(self):
        self.continue_reading = False
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
