#!/usr/bin/env python3
import os
import sys
import time
import importlib
from PyQt6.QtWidgets import QWidget, QLabel, QTextEdit, QVBoxLayout
from PyQt6.QtGui import QPixmap, QColor, QPalette
from PyQt6.QtCore import Qt, QTimer

# Dynamically ensure plugin folder is in sys.path
plugin_folder = os.path.dirname(os.path.abspath(__file__))
if plugin_folder not in sys.path:
    sys.path.insert(0, plugin_folder)

# Try to import MFRC522
try:
    import MFRC522
    LIB_AVAILABLE = True
except ImportError:
    LIB_AVAILABLE = False

class MFRC522Plugin(QWidget):
    def __init__(self, parent=None, apps=None, cfg=None):
        super().__init__(parent)
        self.cfg = cfg
        self.setWindowTitle("RFID Reader")
        self.setFixedSize(800, 900)
        self.init_ui()
        self.continue_reading = True
        self.last_uid = None

        if LIB_AVAILABLE:
            self.reader = MFRC522.MFRC522()
        else:
            self.log_message("MFRC522 Python library not available on this system.\nPlace MFRC522.py in the same folder as this plugin to read cards.")

        # Timer for polling cards
        self.timer = QTimer()
        self.timer.timeout.connect(self.check_card)
        self.timer.start(500)  # every 500 ms

    def init_ui(self):
        layout = QVBoxLayout()
        self.setLayout(layout)

        # Background
        self.setStyleSheet("background-color: #2b2b2b;")  # fallback if no image

        # Logo
        self.logo_label = QLabel(self)
        logo_path = os.path.join(plugin_folder, "logo.png")  # put your PNG in plugin folder
        if os.path.exists(logo_path):
            pixmap = QPixmap(logo_path).scaled(200, 50, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            self.logo_label.setPixmap(pixmap)
            self.logo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.logo_label)

        # Log area
        self.log_area = QTextEdit(self)
        self.log_area.setReadOnly(True)
        self.log_area.setStyleSheet("background-color: #1e1e1e; color: white; font-size: 16px;")
        layout.addWidget(self.log_area)

    def log_message(self, text, color="white"):
        self.log_area.setTextColor(QColor(color))
        self.log_area.append(text)

    def uid_to_string(self, uid):
        return ''.join(format(i, '02X') for i in uid)

    def check_card(self):
        if not LIB_AVAILABLE:
            return

        status, tag_type = self.reader.MFRC522_Request(self.reader.PICC_REQIDL)
        if status == self.reader.MI_OK:
            # Card detected
            status, uid = self.reader.MFRC522_SelectTagSN()
            if status == self.reader.MI_OK:
                uid_str = self.uid_to_string(uid)
                if uid_str != self.last_uid:
                    self.last_uid = uid_str
                    self.log_message(f"Card detected: {uid_str}", color="green")
            else:
                self.log_message("Authentication error", color="red")
        else:
            self.last_uid = None
