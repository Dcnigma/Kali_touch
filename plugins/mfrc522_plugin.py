# plugins/mfrc522_plugin.py
"""
Touchscreen-friendly MFRC522 RFID reader plugin for a PyQt6 launcher.
- Exposes class `MFRC522Plugin(QWidget)` so the launcher's plugin loader can instantiate it
  with the same optional signature used in your other plugins: (parent=None, apps=None, cfg=None).
- Window size is set to 900x800 as requested.
- Console-like QTextEdit displays card UID reads in a human-friendly format.

Notes:
- This code expects the original `MFRC522` Python module the user provided in their example to be
  importable on the target system (typically a Raspberry Pi with an MFRC522 module).
- The reader runs in a QThread to avoid blocking the UI. The thread polls the reader and emits
  signals when a UID is detected.
- Place this file in your `plugins/` folder alongside other plugins and import/instantiate it from the launcher.
"""

import os
import datetime
from typing import Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTextEdit, QPushButton, QMessageBox
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QFont

# Try to import MFRC522, but keep plugin import-safe if library is not available.
try:
    import MFRC522  # type: ignore
    HAS_MFRC = True
except Exception:
    MFRC522 = None
    HAS_MFRC = False


def uidToString(uid):
    """Convert list/tuple of bytes to uppercase hex string (e.g. [0xDE,0xAD,0xBE,0xEF] -> DEADBEEF)."""
    s = ""
    try:
        for i in uid:
            s = format(i, "02X") + s
    except Exception:
        # Fallback: stringify
        s = str(uid)
    return s


class MFRC522ReaderThread(QThread):
    """Background thread that polls the MFRC522 reader and emits UIDs when found."""

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
                    # card detected
                    self.status.emit("Card detected")
                    (status2, uid) = self.reader.MFRC522_SelectTagSN()
                    if status2 == self.reader.MI_OK:
                        uid_str = uidToString(uid)
                        self.uid_read.emit(uid_str)
                    else:
                        self.status.emit("Authentication / UID read error")
                # throttle polling
                self.msleep(int(self._poll_interval * 1000))
            except Exception as e:
                # emit and continue; don't crash the thread
                self.status.emit(f"Reader loop error: {e}")
                self.msleep(500)

        self.status.emit("Reader stopped.")

    def stop(self):
        self._running = False
        self.wait(1000)


class MFRC522Plugin(QWidget):
    """Plugin widget for MFRC522 RFID reader.

    Constructor signature supports being called from the launcher:
        MFRC522Plugin(parent=None, apps=apps_dict, cfg=cfg)
    """

    name = "RFID Reader"
    description = "Read MFRC522 card UIDs (touchscreen-friendly)."

    def __init__(self, parent=None, apps: Optional[dict] = None, cfg: Optional[dict] = None):
        super().__init__(parent)
        self.apps = apps or {}
        self.cfg = cfg or {}

        # Enforce requested screen size
        self.setWindowTitle(self.name)
        self.setFixedSize(900, 800)  # requested 900x800

        # Thread that reads the card
        self.reader_thread: Optional[MFRC522ReaderThread] = None

        # UI
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

        # Console-style output
        self.output = QTextEdit()
        self.output.setReadOnly(True)
        self.output.setStyleSheet("font-family: monospace; font-size:14px;")
        layout.addWidget(self.output, stretch=1)

        # Buttons
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

        # Back / Close
        back_row = QHBoxLayout()
        self.back_btn = QPushButton("Back")
        self.back_btn.setFixedHeight(56)
        self.back_btn.clicked.connect(self._on_back)
        back_row.addWidget(self.back_btn)
        layout.addLayout(back_row)

        self.setLayout(layout)

        # If the hardware library is missing, inform the user
        if not HAS_MFRC:
            self.append_line("MFRC522 Python library not available on this system. Plugin will still load but cannot read cards.")

    # ---------- helpers ----------
    def append_line(self, text: str):
        ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.output.append(f"[{ts}] {text}")

    # ---------- reader control ----------
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
        """Optional hook called by launcher when the plugin is shown."""
        try:
            self.start_btn.setFocus()
        except Exception:
            pass

    def on_close(self):
        """Called by launcher when plugin closes — ensure reader is stopped."""
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


# If this file is executed directly, show a simple standalone window for testing.
if __name__ == "__main__":
    import sys
    from PyQt6.QtWidgets import QApplication

    app = QApplication(sys.argv)
    w = MFRC522Plugin()
    w.show()
    sys.exit(app.exec())
