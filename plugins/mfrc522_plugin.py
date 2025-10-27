#!/usr/bin/env python3
import os
import sys
import time
from PyQt6 import QtWidgets, QtCore

# ---------- Ensure MFRC522.py is importable ----------
plugin_folder = os.path.dirname(os.path.abspath(__file__))
if plugin_folder not in sys.path:
    sys.path.insert(0, plugin_folder)

try:
    import MFRC522
    MFRC522_AVAILABLE = True
except ImportError:
    MFRC522_AVAILABLE = False
    print("MFRC522 Python library not available on this system.")
    print("Place MFRC522.py in the same folder as this plugin to read cards.")

# ---------- Helper Functions ----------
def uidToString(uid):
    """Convert UID list to string."""
    return "".join(format(i, "02X") for i in uid)

# ---------- PyQt6 Plugin ----------
class MFRC522Plugin(QtWidgets.QWidget):
    def __init__(self, parent=None, apps=None, cfg=None):
        super().__init__(parent)
        self.setWindowTitle("RFID Reader")
        self.resize(800, 900)

        self.cfg = cfg

        # UI: label
        self.label = QtWidgets.QLabel("No card detected", self)
        self.label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.label.setGeometry(50, 400, 700, 100)
        font = self.label.font()
        font.setPointSize(24)
        self.label.setFont(font)

        # Only start RFID thread if library is available
        if MFRC522_AVAILABLE:
            self.reader = MFRC522.MFRC522()
            self.thread = QtCore.QThread()
            self.worker = RFIDWorker(self.reader)
            self.worker.moveToThread(self.thread)
            self.thread.started.connect(self.worker.run)
            self.worker.card_detected.connect(self.on_card_detected)
            self.thread.start()
        else:
            self.label.setText("MFRC522.py not found!\nCannot read cards.")

        # Handle closing
        self.destroyed.connect(self.cleanup)

    def on_card_detected(self, uid):
        self.label.setText(f"Card detected: {uid}")

    def cleanup(self):
        if MFRC522_AVAILABLE:
            self.worker.stop()
            self.thread.quit()
            self.thread.wait()

# ---------- RFID Worker Thread ----------
class RFIDWorker(QtCore.QObject):
    card_detected = QtCore.pyqtSignal(str)

    def __init__(self, reader):
        super().__init__()
        self.reader = reader
        self.continue_reading = True

    def run(self):
        while self.continue_reading:
            (status, _) = self.reader.MFRC522_Request(self.reader.PICC_REQIDL)
            if status == self.reader.MI_OK:
                (status, uid) = self.reader.MFRC522_SelectTagSN()
                if status == self.reader.MI_OK:
                    self.card_detected.emit(uidToString(uid))
            time.sleep(0.5)

    def stop(self):
        self.continue_reading = False

# ---------- Standalone Launch ----------
if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    window = MFRC522Plugin()
    window.show()
    sys.exit(app.exec())
