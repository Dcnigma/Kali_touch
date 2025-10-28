#!/usr/bin/env python3
import os
import sys
import json
import subprocess
import time
from PyQt6.QtWidgets import (
    QWidget, QLabel, QLineEdit, QPushButton, QVBoxLayout, QHBoxLayout,
    QGridLayout, QApplication, QSpacerItem, QSizePolicy, QToolTip
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

SCREEN_WIDTH = 1015
SCREEN_HEIGHT = 570
ROWS = 4
COLUMNS = 2
VIDEOS_FILE = os.path.join(plugin_folder, "videos.json")


class RfidPlayerPlugin(QWidget):
    def __init__(self, parent=None, apps=None, cfg=None):
        super().__init__(parent)
        self.cfg = cfg

        # ---------------------- Window setup ----------------------
        self.setFixedSize(SCREEN_WIDTH, SCREEN_HEIGHT)
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

        # ---------------------- Data structures ----------------------
        self.videoDict = {}  # uid -> video filename
        self.load_videos()
        self.current_video_uid = None
        self.video_process = None

        self.init_ui()

        if LIB_AVAILABLE:
            self.reader = MFRC522.MFRC522()
        else:
            self.log_message(
                "MFRC522 Python library not available.\nPlace MFRC522.py in the plugin folder."
            )

        # ---------------------- Timer to poll RFID ----------------------
        self.timer = QTimer()
        self.timer.timeout.connect(self.check_card)
        self.timer.start(300)

    # ---------------------- UI ----------------------
    def init_ui(self):
        main_layout = QVBoxLayout()
        self.setLayout(main_layout)

        # Spacer top
        main_layout.addItem(QSpacerItem(20, 10, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed))

        # Logo
        self.logo_label = QLabel(self)
        logo_path = os.path.join(plugin_folder, "logo.png")
        if os.path.exists(logo_path):
            pixmap = QPixmap(logo_path).scaled(200, 50, Qt.AspectRatioMode.KeepAspectRatio,
                                               Qt.TransformationMode.SmoothTransformation)
            self.logo_label.setPixmap(pixmap)
            self.logo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(self.logo_label, alignment=Qt.AlignmentFlag.AlignCenter)

        # Spacer
        main_layout.addItem(QSpacerItem(20, 10, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed))

        # Grid for UID / video editing
        self.grid_widget = QWidget()
        self.grid_widget.setFixedSize(500, 320)
        self.grid_widget.setStyleSheet("background-color: rgba(0,0,0,120); border-radius: 10px;")
        self.grid_layout = QGridLayout()
        self.grid_widget.setLayout(self.grid_layout)
        main_layout.addWidget(self.grid_widget, alignment=Qt.AlignmentFlag.AlignCenter)

        self.uid_edits = {}
        self.video_edits = {}
        self.update_grid()

        # Pagination controls (not strictly needed here, but could add later)
        main_layout.addItem(QSpacerItem(20, 20, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed))

        # Save button
        self.save_button = QPushButton("Save Mappings")
        self.save_button.clicked.connect(self.save_videos)
        main_layout.addWidget(self.save_button, alignment=Qt.AlignmentFlag.AlignCenter)

    def update_grid(self):
        # Clear previous widgets
        for i in reversed(range(self.grid_layout.count())):
            widget = self.grid_layout.itemAt(i).widget()
            if widget:
                widget.setParent(None)

        self.uid_edits.clear()
        self.video_edits.clear()
        row = 0
        for uid, videofile in self.videoDict.items():
            uid_label = QLabel("UID:")
            uid_label.setStyleSheet("color: white;")
            self.grid_layout.addWidget(uid_label, row, 0)

            uid_edit = QLineEdit(uid)
            uid_edit.setStyleSheet("color: white; background-color: rgba(50,50,50,150);")
            self.grid_layout.addWidget(uid_edit, row, 1)
            self.uid_edits[uid] = uid_edit

            video_label = QLabel("Video:")
            video_label.setStyleSheet("color: white;")
            self.grid_layout.addWidget(video_label, row, 2)

            video_edit = QLineEdit(videofile)
            video_edit.setStyleSheet("color: white; background-color: rgba(50,50,50,150);")
            self.grid_layout.addWidget(video_edit, row, 3)
            self.video_edits[uid] = video_edit
            row += 1

    # ---------------------- Logging ----------------------
    def log_message(self, text):
        print(text)

    # ---------------------- Video functions ----------------------
    def stop_current_video(self):
        if self.video_process:
            try:
                self.video_process.terminate()
            except:
                pass
            self.video_process = None
            self.current_video_uid = None

    def play_video_loop(self, uid):
        videofile = self.videoDict.get(uid)
        if not videofile or videofile.lower() == "stop":
            self.stop_current_video()
            return

        if self.current_video_uid == uid:
            return

        self.stop_current_video()
        self.current_video_uid = uid
        cmd = ["/bin/ffplay", "-fs", "-autoexit", "-loop", "0", os.path.join(plugin_folder, videofile)]
        self.video_process = subprocess.Popen(cmd, stdin=subprocess.PIPE,
                                              stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    # ---------------------- Check card ----------------------
    def check_card(self):
        if not LIB_AVAILABLE:
            return
        status, TagType = self.reader.MFRC522_Request(self.reader.PICC_REQIDL)
        if status == self.reader.MI_OK:
            status, uid_bytes = self.reader.MFRC522_SelectTagSN()
            if status == self.reader.MI_OK:
                uid = ''.join(format(i, '02X') for i in uid_bytes)
                if uid in self.videoDict:
                    if self.videoDict[uid].lower() == "stop":
                        self.stop_current_video()
                    else:
                        self.play_video_loop(uid)

    # ---------------------- Save/load mappings ----------------------
    def save_videos(self):
        new_dict = {}
        for old_uid, uid_edit in self.uid_edits.items():
            new_uid = uid_edit.text()
            video_file = self.video_edits[old_uid].text()
            new_dict[new_uid] = video_file
        self.videoDict = new_dict
        try:
            with open(VIDEOS_FILE, "w") as f:
                json.dump(self.videoDict, f)
            self.log_message("Video mappings saved.")
        except Exception as e:
            self.log_message(f"Error saving videos: {e}")

    def load_videos(self):
        if os.path.exists(VIDEOS_FILE):
            try:
                with open(VIDEOS_FILE, "r") as f:
                    self.videoDict = json.load(f)
            except Exception as e:
                self.log_message(f"Error loading videos: {e}")
                self.videoDict = {}
        else:
            # Default sample
            self.videoDict = {
                "C561E9C0": "Fingerprint.mp4",
                "1E007B16": "Password.mp4",
                "1E00307C": "Skull.mp4",
                "6154A6BE": "stop"
            }
