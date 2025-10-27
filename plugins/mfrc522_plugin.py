#!/usr/bin/env python3
import os
import sys
import time
from PyQt6 import QtWidgets, QtCore

# ---------- Auto-detect MFRC522.py ----------
def find_mfrc522():
    """Try to locate MFRC522.py automatically."""
    possible_folders = [
        os.path.dirname(os.path.abspath(__file__)),  # plugin folder
        os.getcwd(),                                # current working dir
    ]
    for folder in possible_folders:
        candidate = os.path.join(folder, "MFRC522.py")
        if os.path.isfile(candidate):
            if folder not in sys.path:
                sys.path.insert(0, folder)
            return True, folder
    return False, None

MFRC522_AVAILABLE, mfrc_folder = find_mfrc522()
if MFRC522_AVAILABLE:
    import MFRC522
    print(f"=== DEBUG INFO ===\nMFRC522.py found in: {mfrc_folder}\n==================")
else:
    print("MFRC522 Python library not available on this system.")
    print("Place MFRC522.py in the same folder as this plugin or launcher to read cards.")

# ---------- Helper ----------
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

        # UI label
        self.label = QtWidgets.QLabel("No card detected", self)
        self.label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.label.setGeometry(50, 400, 700, 100)
        font = self.label.font()
        font.setPointSize(24)
        self.label.setFont(font)

        # Start RFID thread if available
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

        # Cleanup when closing
        self.destroyed.connect(self.cleanup)

    def on_card_detected(self, uid):
        self.label.setText(f"Card detected: {uid}")

    def cleanup(self):
        if MFRC522_AVAILABLE:
            self.worker.stop()
            self.thread.quit()
            self.thread.wait()

# ---------- RFID Worker ----------
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
