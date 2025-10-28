#!/usr/bin/env python3
import os
import sys
import json
import time
import subprocess
from datetime import datetime
from PyQt6.QtWidgets import (
    QWidget, QLabel, QLineEdit, QPushButton, QVBoxLayout, QHBoxLayout,
    QGridLayout, QApplication, QSpacerItem, QSizePolicy
)
from PyQt6.QtGui import QPixmap, QPalette, QBrush
from PyQt6.QtCore import Qt, QTimer

# Ensure plugin folder is in sys.path
plugin_folder = os.path.dirname(os.path.abspath(__file__))
if plugin_folder not in sys.path:
    sys.path.insert(0, plugin_folder)

# Try to import MFRC522
try:
    import MFRC522
    LIB_AVAILABLE = True
except ImportError:
    LIB_AVAILABLE = False

VIDEOS_FILE = os.path.join(plugin_folder, "videos.json")
CARDS_PER_PAGE = 8  # 2 columns x 4 rows
COLUMNS = 2
ROWS = 4
CHECK_INTERVAL = 500  # ms


class RfidPlayerPlugin(QWidget):
    def __init__(self, parent=None, apps=None, cfg=None):
        super().__init__(parent)
        self.cfg = cfg

        # ---------------------- Window ----------------------
        self.setFixedSize(1015, 570)
        self.move(-50, 0)
        self.setWindowTitle("RFID Video Player")

        # ---------------------- Background ----------------------
        bg_path = os.path.join(plugin_folder, "background.png")
        if os.path.exists(bg_path):
            pixmap = QPixmap(bg_path).scaled(
                self.size(), Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation
            )
            palette = self.palette()
            palette.setBrush(QPalette.ColorRole.Window, QBrush(pixmap))
            self.setAutoFillBackground(True)
            self.setPalette(palette)

        # ---------------------- Data ----------------------
        self.video_map = {}
        self.checkboxes = []
        self.page = 0
        self.current_uid = None
        self.video_process = None

        self.load_videos()
        self.init_ui()

        if LIB_AVAILABLE:
            self.reader = MFRC522.MFRC522()
        else:
            print("MFRC522 Python library not available. Plugin will not read cards.")

        # ---------------------- Timers ----------------------
        self.timer = QTimer()
        self.timer.timeout.connect(self.check_card)
        self.timer.start(CHECK_INTERVAL)

    # ---------------------- Load videos ----------------------
    def load_videos(self):
        if os.path.exists(VIDEOS_FILE):
            try:
                with open(VIDEOS_FILE, "r") as f:
                    self.video_map = json.load(f)
            except Exception as e:
                print(f"Error loading videos.json: {e}")
                self.video_map = {}
        else:
            # default videos
            self.video_map = {
                "C0E961C5": "Fingerprint.mp4",
                "167B001E": "Password.mp4",
                "F93264E6": "Skull.mp4",
                "BEA65461": "stop"
            }
            # Save the default JSON
            try:
                with open(VIDEOS_FILE, "w") as f:
                    json.dump(self.video_map, f, indent=4)
            except Exception as e:
                print(f"Error creating default videos.json: {e}")

    def save_videos(self):
        try:
            with open(VIDEOS_FILE, "w") as f:
                json.dump(self.video_map, f, indent=4)
        except Exception as e:
            print(f"Error saving videos.json: {e}")

    # ---------------------- UI ----------------------
    def init_ui(self):
        main_layout = QVBoxLayout()
        self.setLayout(main_layout)

        # Logo
        logo_label = QLabel(self)
        logo_path = os.path.join(plugin_folder, "logo.png")
        if os.path.exists(logo_path):
            pixmap = QPixmap(logo_path).scaled(200, 50, Qt.AspectRatioMode.KeepAspectRatio)
            logo_label.setPixmap(pixmap)
            logo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(logo_label, alignment=Qt.AlignmentFlag.AlignCenter)

        # Grid for videos
        self.grid_widget = QWidget()
        self.grid_widget.setFixedSize(600, 320)
        self.grid_widget.setStyleSheet("background-color: rgba(0,0,0,120); border-radius: 10px;")
        self.grid_layout = QGridLayout()
        self.grid_widget.setLayout(self.grid_layout)
        main_layout.addWidget(self.grid_widget, alignment=Qt.AlignmentFlag.AlignCenter)

        # Video entries
        self.video_entries = []
        for i, (uid, filename) in enumerate(self.video_map.items()):
            label = QLabel(uid)
            label.setStyleSheet("color: lightgrey; font-size: 16px;")
            le_uid = QLineEdit(uid)
            le_file = QLineEdit(filename)
            btn_save = QPushButton("Save")
            btn_save.clicked.connect(lambda _, idx=i: self.update_video_entry(idx))
            self.grid_layout.addWidget(label, i, 0)
            self.grid_layout.addWidget(le_uid, i, 1)
            self.grid_layout.addWidget(le_file, i, 2)
            self.grid_layout.addWidget(btn_save, i, 3)
            self.video_entries.append((le_uid, le_file))

        # Last scanned label
        self.last_scanned_label = QLabel("Last scanned: None")
        self.last_scanned_label.setStyleSheet("color: lightgrey; font-size: 18px;")
        main_layout.addWidget(self.last_scanned_label, alignment=Qt.AlignmentFlag.AlignCenter)

        # Spacer
        main_layout.addItem(QSpacerItem(20, 40, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding))

    def update_video_entry(self, index):
        le_uid, le_file = self.video_entries[index]
        old_uid = list(self.video_map.keys())[index]
        new_uid = le_uid.text()
        new_file = le_file.text()
        if old_uid != new_uid:
            self.video_map.pop(old_uid)
        self.video_map[new_uid] = new_file
        self.save_videos()

    # ---------------------- Card reading ----------------------
    def check_card(self):
        if not LIB_AVAILABLE:
            return
        status, _ = self.reader.MFRC522_Request(self.reader.PICC_REQIDL)
        if status == self.reader.MI_OK:
            status, uid = self.reader.MFRC522_SelectTagSN()
            if status == self.reader.MI_OK:
                uid_str = ''.join(format(i, '02X') for i in uid)
                if uid_str != self.current_uid:
                    self.current_uid = uid_str
                    self.last_scanned_label.setText(f"Last scanned: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | UID: {uid_str}")
                    self.play_video_for_uid(uid_str)

    # ---------------------- Video playback ----------------------
    def play_video_for_uid(self, uid):
        if self.video_process:
            self.video_process.terminate()
            self.video_process = None
            time.sleep(0.2)

        if uid in self.video_map:
            filename = self.video_map[uid]
            if filename.lower() == "stop":
                return
            filepath = os.path.join(plugin_folder, filename)
            if os.path.exists(filepath):
                cmd = ["/bin/ffplay", "-fs", "-loop", "0", "-autoexit", filepath]
                self.video_process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
