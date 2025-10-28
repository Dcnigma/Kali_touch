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

VIDEOS_FILE = os.path.join(plugin_folder, "videos.json")

CARDS_PER_PAGE = 8
COLUMNS = 2
ROWS = 4
ANIMATION_INTERVAL = 50  # ms

class RfidPlayerPlugin(QWidget):
    def __init__(self, parent=None, apps=None, cfg=None):
        super().__init__(parent)
        self.cfg = cfg

        # ---------------------- Window setup ----------------------
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

        # ---------------------- Data structures ----------------------
        self.videos = {}  # uid -> filename
        self.load_videos()
        self.current_video_process = None
        self.current_uid = None

        # ---------------------- UI ----------------------
        self.init_ui()

        # ---------------------- MFRC522 ----------------------
        if LIB_AVAILABLE:
            self.reader = MFRC522.MFRC522()
        else:
            self.log_message("MFRC522 library not available. Plugin won't read cards.")

        # ---------------------- Timers ----------------------
        self.timer = QTimer()
        self.timer.timeout.connect(self.check_card)
        self.timer.start(200)  # check cards every 200ms

    # ---------------------- UI ----------------------
    def init_ui(self):
        main_layout = QVBoxLayout()
        self.setLayout(main_layout)

        # Spacer above logo
        spacer_top = QWidget()
        spacer_top.setFixedHeight(10)
        main_layout.addWidget(spacer_top)

        # Logo top-center
        self.logo_label = QLabel(self)
        logo_path = os.path.join(plugin_folder, "logo.png")
        if os.path.exists(logo_path):
            pixmap = QPixmap(logo_path).scaled(
                200, 50, Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            self.logo_label.setPixmap(pixmap)
            self.logo_label.setAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignTop)
        main_layout.addWidget(self.logo_label, alignment=Qt.AlignmentFlag.AlignCenter)

        # Spacer between logo and grid
        spacer_logo = QWidget()
        spacer_logo.setFixedHeight(20)
        main_layout.addWidget(spacer_logo)

        # Grid container
        self.grid_widget = QWidget()
        self.grid_widget.setFixedSize(500, 320)
        self.grid_layout = QGridLayout()
        self.grid_widget.setLayout(self.grid_layout)
        self.grid_widget.setStyleSheet("background-color: rgba(0,0,0,120); border-radius: 10px;")
        main_layout.addWidget(self.grid_widget, alignment=Qt.AlignmentFlag.AlignCenter)

        # Create labels and text inputs for videos
        self.video_inputs = {}  # uid -> QLineEdit
        for i, (uid, filename) in enumerate(self.videos.items()):
            row = i // COLUMNS
            col = i % COLUMNS

            uid_label = QLabel(uid)
            uid_label.setStyleSheet("color: lightgrey; font-size: 16px;")
            self.grid_layout.addWidget(uid_label, row*2, col)

            filename_input = QLineEdit(filename)
            filename_input.setStyleSheet("font-size: 16px; padding: 5px;")
            filename_input.editingFinished.connect(self.save_videos)
            self.grid_layout.addWidget(filename_input, row*2+1, col)

            self.video_inputs[uid] = filename_input

        # Pagination / controls
        pagination_layout = QHBoxLayout()
        self.prev_button = QPushButton("Previous")
        self.prev_button.setFixedSize(100, 35)
        self.prev_button.clicked.connect(lambda: None)  # optional
        self.next_button = QPushButton("Next")
        self.next_button.setFixedSize(100, 35)
        self.next_button.clicked.connect(lambda: None)  # optional
        pagination_layout.addWidget(self.prev_button)
        pagination_layout.addWidget(self.next_button)
        main_layout.addLayout(pagination_layout)

        # Spacer at bottom
        main_layout.addItem(QSpacerItem(20, 40, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding))

    # ---------------------- Video management ----------------------
    def play_video(self, videofile):
        self.stop_video()
        if videofile == "stop":
            return
        cmd = ("/bin/ffplay", "-fs", "-autoexit", "-loop", "0", videofile)
        self.current_video_process = subprocess.Popen(cmd, stdin=subprocess.PIPE,
                                                      stdout=subprocess.PIPE,
                                                      stderr=subprocess.PIPE)

    def stop_video(self):
        if self.current_video_process:
            try:
                self.current_video_process.terminate()
            except Exception:
                pass
            self.current_video_process = None
            time.sleep(0.2)

    # ---------------------- MFRC522 helpers ----------------------
    def uid_to_string(self, uid):
        return ''.join(format(i, '02X') for i in uid)

    def check_card(self):
        if not LIB_AVAILABLE:
            return
        status, tag_type = self.reader.MFRC522_Request(self.reader.PICC_REQIDL)
        if status == self.reader.MI_OK:
            status, uid = self.reader.MFRC522_SelectTagSN()
            if status == self.reader.MI_OK:
                uid_str = self.uid_to_string(uid)
                if uid_str in self.videos:
                    self.current_uid = uid_str
                    filename = os.path.join(plugin_folder, self.videos[uid_str])
                    self.play_video(filename)
                elif self.current_uid and self.videos.get(self.current_uid) == "stop":
                    self.stop_video()
                    self.current_uid = None

    # ---------------------- Save/load videos ----------------------
    def save_videos(self):
        for uid, input_box in self.video_inputs.items():
            self.videos[uid] = input_box.text()
        try:
            with open(VIDEOS_FILE, "w") as f:
                json.dump(self.videos, f)
        except Exception as e:
            self.log_message(f"Error saving videos: {e}")

    def load_videos(self):
        if os.path.exists(VIDEOS_FILE):
            try:
                with open(VIDEOS_FILE, "r") as f:
                    self.videos = json.load(f)
            except Exception as e:
                self.log_message(f"Error loading videos: {e}")
                self.videos = {}
        else:
            self.videos = {}

    # ---------------------- Logging ----------------------
    def log_message(self, text):
        print(text)
