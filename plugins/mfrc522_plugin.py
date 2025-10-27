from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel
from PyQt6.QtCore import QTimer
import os, sys

# Ensure MFRC522.py is importable
plugin_dir = os.path.dirname(os.path.abspath(__file__))
if plugin_dir not in sys.path:
    sys.path.insert(0, plugin_dir)

try:
    import MFRC522
except ImportError:
    MFRC522 = None


class MFRC522Plugin(QWidget):
    def __init__(self, parent=None, apps=None, cfg=None):
        super().__init__(parent)
        self.apps = apps
        self.cfg = cfg

        # UI setup
        self.setWindowTitle("RFID Reader")
        self.resize(800, 900)
        layout = QVBoxLayout()
        self.status_label = QLabel("Initializing...")
        layout.addWidget(self.status_label)
        self.setLayout(layout)

        if MFRC522 is None:
            self.status_label.setText(
                "MFRC522 Python library not available.\nPlace MFRC522.py in this folder."
            )
            return

        # Create MFRC522 reader
        self.reader = MFRC522.MFRC522()

        # Timer to poll the reader
        self.timer = QTimer()
        self.timer.timeout.connect(self.poll_card)
        self.timer.start(500)  # every 500 ms

    def poll_card(self):
        status, _ = self.reader.MFRC522_Request(self.reader.PICC_REQIDL)
        if status == self.reader.MI_OK:
            status, uid = self.reader.MFRC522_SelectTagSN()
            if status == self.reader.MI_OK:
                uid_str = "".join(f"{x:02X}" for x in uid)
                self.status_label.setText(f"Card detected: {uid_str}")
            else:
                self.status_label.setText("Authentication error")
        else:
            self.status_label.setText("No card detected")
