#!/usr/bin/env python3
import os
import sys
import json
import time
import subprocess
from math import ceil
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

ROWS_PER_PAGE = 4  # max 4 rows per page
VIDEO_FILE = os.path.join(plugin_folder, "videos.json")


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
        self.video_map = {}
        self.all_videos = []  # list of (uid, video)
        self.current_uid = None
        self.my_subprocess = None
        self.page = 0

        self.load_videos()
        self.scan_plugin_folder_for_videos()
        self.init_ui()

        if LIB_AVAILABLE:
            self.reader = MFRC522.MFRC522()
        else:
            self.log_message(
                "MFRC522 Python library not available on this system.\n"
                "Place MFRC522.py in the same folder as this plugin to read cards."
            )

        # ---------------------- Timer ----------------------
        self.timer = QTimer()
        self.timer.timeout.connect(self.check_card)
        self.timer.start(500)

    # ---------------------- UI ----------------------
    def init_ui(self):
        main_layout = QVBoxLayout()
        self.setLayout(main_layout)

        # Logo
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

        main_layout.addWidget(QWidget(), stretch=0)  # spacer

        # Grid container
        self.grid_widget = QWidget()
        self.grid_widget.setFixedSize(800, 200)
        self.grid_layout = QGridLayout()
        self.grid_widget.setLayout(self.grid_layout)
        self.grid_widget.setStyleSheet("background-color: rgba(0,0,0,120); border-radius: 10px;")
        main_layout.addWidget(self.grid_widget, alignment=Qt.AlignmentFlag.AlignCenter)

        # Pagination buttons
        pagination_layout = QHBoxLayout()
        self.prev_button = QPushButton("Previous")
        self.prev_button.setFixedSize(100, 35)
        self.prev_button.clicked.connect(self.prev_page)
        self.next_button = QPushButton("Next")
        self.next_button.setFixedSize(100, 35)
        self.next_button.clicked.connect(self.next_page)
        pagination_layout.addWidget(self.prev_button)
        pagination_layout.addStretch()
        pagination_layout.addWidget(self.next_button)
        main_layout.addLayout(pagination_layout)

        # Last scanned UID label
        self.last_scanned_label = QLabel("Last scanned: None")
        self.last_scanned_label.setStyleSheet("color: lightgrey; font-size: 16px;")
        self.last_scanned_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.last_scanned_label.mousePressEvent = self.fill_uid_from_last_scan
        main_layout.addWidget(self.last_scanned_label, alignment=Qt.AlignmentFlag.AlignCenter)

        main_layout.addItem(QSpacerItem(20, 40, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding))

        # Prepare grid inputs
        self.uid_inputs = []
        self.video_inputs = []

        self.update_grid()

    # ---------------------- Load/save videos ----------------------
    def load_videos(self):
        if os.path.exists(VIDEO_FILE):
            try:
                with open(VIDEO_FILE, "r") as f:
                    self.video_map = json.load(f)
            except Exception as e:
                self.log_message(f"Error loading video map: {e}")
                self.video_map = {}
        else:
            self.video_map = {}
            self.save_videos()

    def save_videos(self):
        self.video_map = {}
        for uid_input, video_input in zip(self.uid_inputs, self.video_inputs):
            uid = uid_input.text().strip()
            video = video_input.text().strip()
            if video:
                self.video_map[uid] = video
        try:
            with open(VIDEO_FILE, "w") as f:
                json.dump(self.video_map, f)
        except Exception as e:
            self.log_message(f"Error saving video map: {e}")

    # ---------------------- Scan folder for mp4 ----------------------
    def scan_plugin_folder_for_videos(self):
        files = [f for f in os.listdir(plugin_folder) if f.lower().endswith(".mp4")]
        # Add new videos not already in JSON
        for f in files:
            if f not in self.video_map.values():
                self.video_map[""] = f  # empty UID
        # Build the full list for pagination
        self.all_videos = list(self.video_map.items())

    # ---------------------- Grid update ----------------------
    def update_grid(self):
        # Clear previous widgets
        for i in reversed(range(self.grid_layout.count())):
            w = self.grid_layout.itemAt(i).widget()
            if w:
                w.setParent(None)
        self.uid_inputs.clear()
        self.video_inputs.clear()

        start_index = self.page * ROWS_PER_PAGE
        end_index = start_index + ROWS_PER_PAGE
        page_videos = self.all_videos[start_index:end_index]

        for row, (uid, video) in enumerate(page_videos):
            uid_label = QLabel(f"UID:")
            uid_label.setStyleSheet("color: lightgrey; font-size: 16px;")
            uid_input = QLineEdit(uid)
            uid_input.setStyleSheet("font-size: 16px;")
            video_input = QLineEdit(video)
            video_input.setStyleSheet("font-size: 16px;")
            self.grid_layout.addWidget(uid_label, row, 0)
            self.grid_layout.addWidget(uid_input, row, 1)
            self.grid_layout.addWidget(video_input, row, 2)
            self.uid_inputs.append(uid_input)
            self.video_inputs.append(video_input)

    # ---------------------- Pagination ----------------------
    def next_page(self):
        total_pages = ceil(len(self.all_videos) / ROWS_PER_PAGE)
        self.page = (self.page + 1) % total_pages
        self.update_grid()

    def prev_page(self):
        total_pages = ceil(len(self.all_videos) / ROWS_PER_PAGE)
        self.page = (self.page - 1 + total_pages) % total_pages
        self.update_grid()

    # ---------------------- Card reading ----------------------
    def check_card(self):
        if not LIB_AVAILABLE:
            return
        status, tag_type = self.reader.MFRC522_Request(self.reader.PICC_REQIDL)
        if status == self.reader.MI_OK:
            status, uid = self.reader.MFRC522_SelectTagSN()
            if status == self.reader.MI_OK:
                uid_str = self.uid_to_string(uid)
                self.current_uid = uid_str
                timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
                self.last_scanned_label.setText(f"Last scanned: {timestamp} | UID: {uid_str}")
                self.play_video_for_uid(uid_str)

    def uid_to_string(self, uid):
        return ''.join(format(i, '02X') for i in uid)

    # ---------------------- Video playback ----------------------
    def stop_current_video(self):
        try:
            if self.my_subprocess:
                self.my_subprocess.terminate()
        except Exception:
            pass
        time.sleep(0.2)
        self.my_subprocess = None

    def play_video_for_uid(self, uid_str):
        # If stop card scanned, stop video
        if uid_str in self.video_map and self.video_map[uid_str].lower() == "stop":
            self.stop_current_video()
            return
        # Otherwise stop current and play new video
        self.stop_current_video()
        video_file = self.video_map.get(uid_str)
        if video_file:
            video_path = os.path.join(plugin_folder, video_file)
            if os.path.exists(video_path):
                cmd = ("/bin/ffplay", "-fs", "-autoexit", "-loop", "0", video_path)
                self.my_subprocess = subprocess.Popen(cmd, stdin=subprocess.PIPE,
                                                     stdout=subprocess.PIPE,
                                                     stderr=subprocess.PIPE)

    # ---------------------- Last scanned UID -> fill empty field ----------------------
    def fill_uid_from_last_scan(self, event):
        if not self.current_uid:
            return
        for uid_input in self.uid_inputs:
            if not uid_input.text().strip():  # empty
                uid_input.setText(self.current_uid)
                break

    # ---------------------- Logging ----------------------
    def log_message(self, text):
        print(text)
