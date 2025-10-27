# plugins/mfrc522_plugin.py
"""
Touchscreen-friendly MFRC522 RFID reader plugin for a PyQt6 launcher.
- Exposes class `MFRC522Plugin(QWidget)` so the launcher's plugin loader can instantiate it
  with the same optional signature used in your other plugins: (parent=None, apps=None, cfg=None).
- Window size is set to 900x800.
- Console-like QTextEdit displays card UID reads in a human-friendly format.

Notes:
- Expects the MFRC522 Python module and SPI hardware to be available (Raspberry Pi).
- The reader runs in a QThread to avoid blocking the UI.
- Plugin now auto-detects SPI availability and gives clearer messages if hardware is missing.
"""

import os
import datetime
from typing import Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTextEdit, QPushButton
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QFont

# Try to import MFRC522 safely
try:
    import MFRC522  # type: ignore
    HAS_MFRC = True
except Exception:
    MFRC522 = None
    HAS_MFRC = False

# Additional SPI check (for Raspberry Pi)
try:
    import spidev  # type: ignore
    SPI_AVAILABLE = True
except Exception:
    SPI_AVAILABLE = False


def uidToString(uid):
    s = ""
    try:
        for i in uid:
            s = format(i, "02X") + s
    except Exception:
        s = str(uid)
    return s


class MFRC522ReaderThread(QThread):
    uid_read = pyqtSignal(str)
    status = pyqtSignal(str)

    def __init__(self, poll_interval: float = 0.5, parent=None):
        super().__init__(parent)
        self._running = False
        self._poll_interval = poll_interval
        self.reader = None

    def run(self):
        if not HAS_MFRC:
            self.status.emit("MFRC522 library not available; cannot start reader.")
            return
        if not SPI_AVAILABLE:
            self.status.emit("SPI interface not available; check hardware and enable SPI in raspi-config.")
            return

        try:
            self.reader = MFRC522.MFRC522()
        except Exception as e:
            self.status.emit(f"Failed to initialize MFRC522: {e}")
            return

        self._running = True
        self.status.emit("Reader started. Waiting for cards...")

        while self._running:
            try:
                (status, TagType) = self.reader.MFRC522_Request(self.reader.PICC_REQIDL)
                if status == self.reader.MI_OK:
                    self.status.emit("Card detected")
                    (status2, uid) = self.reader.MFRC522_SelectTagSN()
                    if status2 == self.reader.MI_OK:
                        uid_str = uidToString(uid)
                        self.uid_read.emit(uid_str)
                    else:
                        self.status.emit("Authentication / UID read error")
                self.msleep(int(self._poll_interval * 1000))
            except Exception as e:
                self.status.emit(f"Reader loop error: {e}")
                self.msleep(500)

        self.status.emit("Reader stopped.")

    def stop(self):
        self._running = False
        self.wait(1000)


class MFRC522Plugin(QWidget):
    name = "RFID Reader"
    description = "Read MFRC522 card UIDs (touchscreen-friendly)."

    def __init__(self, parent=None, apps: Optional[dict] = None, cfg: Optional[dict] = None):
        super().__init__(parent)
        self.apps = apps or {}
        self.cfg = cfg or {}

        self.setWindowTitle(self.name)
        self.setFixedSize(900, 800)

        self.reader_thread: Optional[MFRC522ReaderThread] = None

        layout = QVBoxLayout()
        layout.setSpacing(8)
        layout.setContentsMargins(12, 12, 12, 12)

        header = QLabel("MFRC522 UID Reader")
        header.setFont(QFont("", 20, QFont.Weight.Bold))
        header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(header)

        info = QLabel("Console output below shows detected UIDs. Press Start to begin polling the reader.")
        info.setWordWrap(True)
        layout.addWidget(info)

        self.output = QTextEdit()
        self.output.setReadOnly(True)
        self.output.setStyleSheet("font-family: monospace; font-size:14px;")
        layout.addWidget(self.output, stretch=1)

        btn_row = QHBoxLayout()
        self.start_btn = QPushButton("Start")
        self.start_btn.setFixedHeight(56)
        self.start_btn.clicked.connect(self.start_reader)
        btn_row.addWidget(self.start_btn)

        self.stop_btn = QPushButton("Stop")
        self.stop_btn.setFixedHeight(56)
        self.stop_btn.clicked.connect(self.stop_reader)
        self.stop_btn.setEnabled(False)
        btn_row.addWidget(self.stop_btn)

        self.clear_btn = QPushButton("Clear Console")
        self.clear_btn.setFixedHeight(56)
        self.clear_btn.clicked.connect(self.output.clear)
        btn_row.addWidget(self.clear_btn)

        layout.addLayout(btn_row)

        back_row = QHBoxLayout()
        self.back_btn = QPushButton("Back")
        self.back_btn.setFixedHeight(56)
        self.back_btn.clicked.connect(self._on_back)
        back_row.addWidget(self.back_btn)
        layout.addLayout(back_row)

        self.setLayout(layout)

        if not HAS_MFRC:
            self.append_line("MFRC522 Python library not found. Install it to read cards.")
        elif not SPI_AVAILABLE:
            self.append_line("SPI interface not detected. Enable SPI to read cards.")

    def append_line(self, text: str):
        ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.output.append(f"[{ts}] {text}")

    def start_reader(self):
        if self.reader_thread and self.reader_thread.isRunning():
            return
        self.reader_thread = MFRC522ReaderThread(poll_interval=self.cfg.get("poll_interval", 0.5))
        self.reader_thread.uid_read.connect(self.on_uid_read)
        self.reader_thread.status.connect(self.append_line)
        self.reader_thread.start()
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.append_line("Starting reader thread...")

    def stop_reader(self):
        if self.reader_thread:
            try:
                self.reader_thread.stop()
            except Exception:
                pass
            self.reader_thread = None
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.append_line("Reader stopped by user.")

    def on_uid_read(self, uid_str: str):
        self.append_line(f"Card read UID: {uid_str}")

    def on_start(self):
        try:
            self.start_btn.setFocus()
        except Exception:
            pass

    def on_close(self):
        try:
            if self.reader_thread and self.reader_thread.isRunning():
                self.reader_thread.stop()
        except Exception:
            pass

    def _on_back(self):
        try:
            self.on_close()
        except Exception:
            pass
        try:
            self.close()
        except Exception:
            pass


if __name__ == "__main__":
    import sys
    from PyQt6.QtWidgets import QApplication

    app = QApplication(sys.argv)
    w = MFRC522Plugin()
    w.show()
    sys.exit(app.exec())
