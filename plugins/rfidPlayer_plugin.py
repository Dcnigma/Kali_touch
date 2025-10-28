#!/usr/bin/env python3
import os
import sys
import json
import time
import subprocess
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

ROWS = 4
COLUMNS = 2
VIDEOS_PER_PAGE = ROWS * COLUMNS
VIDEO_FILE = os.path.join(plugin_folder, "videos.json")


class RfidPlayerPlugin(QWidget):
    def __init__(self, parent=None, apps=None, cfg=None):
        super().__init__(parent)
        self.cfg = cfg

        self.setFixedSize(1015, 570)
        self.move(-50, 0)
        self.setWindowTitle("RFID Video Player")

        # Background
        bg_path = os.path.join(plugin_folder, "background.png")
        if os.path.exists(bg_path):
            pixmap = QPixmap(bg_path).scaled(
                self.size(), Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation
            )
            palette = self.palette()
            palette.setBrush(QPalette.ColorRole.Window, QBrush(pixmap))
            self.setAutoFillBackground(True)
            self.setPalette(palette)

        self.video_map = {}
        self.video_list = []  # list of dicts: {"uid": "", "video": ""}
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
                "MFRC522 Python library not available.\n"
                "Place MFRC522.py in the same folder as this plugin."
            )

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
            pixmap = QPixmap(logo_path).scaled(200, 50, Qt.AspectRatioMode.KeepAspectRatio,
                                               Qt.TransformationMode.SmoothTransformation)
            self.logo_label.setPixmap(pixmap)
            self.logo_label.setAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignTop)
        main_layout.addWidget(self.logo_label, alignment=Qt.AlignmentFlag.AlignCenter)

        main_layout.addWidget(QWidget(), alignment=Qt.AlignmentFlag.AlignTop)  # spacer

        # Grid for video mapping
        self.grid_widget = QWidget()
        self.grid_widget.setFixedSize(700, 300)
        self.grid_layout = QGridLayout()
        self.grid_widget.setLayout(self.grid_layout)
        self.grid_widget.setStyleSheet("background-color: rgba(0,0,0,120); border-radius: 10px;")
        main_layout.addWidget(self.grid_widget, alignment=Qt.AlignmentFlag.AlignCenter)

        self.uid_inputs = []
        self.video_inputs = []

        # Navigation
        nav_layout = QHBoxLayout()
        self.prev_button = QPushButton("Previous")
        self.prev_button.clicked.connect(self.prev_page)
        self.next_button = QPushButton("Next")
        self.next_button.clicked.connect(self.next_page)
        nav_layout.addWidget(self.prev_button)
        nav_layout.addWidget(self.next_button)
        main_layout.addLayout(nav_layout)

        # Save button
        self.save_button = QPushButton("Save")
        self.save_button.clicked.connect(self.save_videos)
        main_layout.addWidget(self.save_button, alignment=Qt.AlignmentFlag.AlignCenter)

        # Last scanned UID label
        self.last_scanned_label = QLabel("Last scanned: None")
        self.last_scanned_label.setStyleSheet("color: lightgrey; font-size: 18px;")
        self.last_scanned_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.last_scanned_label.mousePressEvent = self.copy_last_uid_to_clipboard
        main_layout.addWidget(self.last_scanned_label, alignment=Qt.AlignmentFlag.AlignCenter)

        main_layout.addItem(QSpacerItem(20, 40, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding))

        self.update_grid()

    # ---------------------- Load/save ----------------------
    def load_videos(self):
        if os.path.exists(VIDEO_FILE):
            try:
                with open(VIDEO_FILE, "r") as f:
                    self.video_map = json.load(f)
            except Exception as e:
                self.log_message(f"Error loading videos.json: {e}")
                self.video_map = {}
        else:
            self.video_map = {
                "C0E961C5": "Fingerprint.mp4",
                "167B001E": "Password.mp4",
                "F93264E6": "Skull.mp4",
                "BEA65461": "stop"
            }
            self.save_videos()

        # Initialize video_list from video_map
        self.video_list = [{"uid": uid, "video": video} for uid, video in self.video_map.items()]

    def save_videos(self):
        # Update video_list entries for current page
        start = self.page * VIDEOS_PER_PAGE
        end = start + VIDEOS_PER_PAGE
        for i, entry in enumerate(self.video_list[start:end]):
            uid = self.uid_inputs[i].text().strip()
            video = self.video_inputs[i].text().strip()
            entry["uid"] = uid
            entry["video"] = video

        # Rebuild video_map
        self.video_map = {entry["uid"]: entry["video"] for entry in self.video_list if entry["uid"] and entry["video"]}

        try:
            with open(VIDEO_FILE, "w") as f:
                json.dump(self.video_map, f)
            self.log_message("Videos saved successfully!")
        except Exception as e:
            self.log_message(f"Error saving videos.json: {e}")

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
                # Add to video_list if new UID scanned
                if uid_str not in [e["uid"] for e in self.video_list]:
                    self.video_list.append({"uid": uid_str, "video": ""})
                    self.update_grid()

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
        if uid_str in self.video_map:
            video_file = self.video_map[uid_str]
            if video_file.lower() == "stop":
                self.stop_current_video()
                return
            self.stop_current_video()
            video_path = os.path.join(plugin_folder, video_file)
            if os.path.exists(video_path):
                cmd = ("/bin/ffplay", "-fs", "-autoexit", "-loop", "0", video_path)
                self.my_subprocess = subprocess.Popen(cmd, stdin=subprocess.PIPE,
                                                     stdout=subprocess.PIPE,
                                                     stderr=subprocess.PIPE)

    # ---------------------- Grid ----------------------
    def update_grid(self):
        # Clear old widgets
        for i in reversed(range(self.grid_layout.count())):
            widget = self.grid_layout.itemAt(i).widget()
            if widget:
                widget.setParent(None)

        # Setup inputs for current page
        self.uid_inputs = []
        self.video_inputs = []

        start = self.page * VIDEOS_PER_PAGE
        end = start + VIDEOS_PER_PAGE
        for i, entry in enumerate(self.video_list[start:end]):
            uid_label = QLabel(f"UID {start+i+1}:")
            uid_label.setStyleSheet("color: lightgrey; font-size: 18px;")
            uid_input = QLineEdit(entry["uid"])
            uid_input.setStyleSheet("font-size: 16px;")
            video_input = QLineEdit(entry["video"])
            video_input.setStyleSheet("font-size: 16px;")
            self.grid_layout.addWidget(uid_label, i, 0)
            self.grid_layout.addWidget(uid_input, i, 1)
            self.grid_layout.addWidget(video_input, i, 2)
            self.uid_inputs.append(uid_input)
            self.video_inputs.append(video_input)

    # ---------------------- Pagination ----------------------
    def next_page(self):
        total_pages = max(1, (len(self.video_list) + VIDEOS_PER_PAGE - 1) // VIDEOS_PER_PAGE)
        self.page = (self.page + 1) % total_pages
        self.update_grid()

    def prev_page(self):
        total_pages = max(1, (len(self.video_list) + VIDEOS_PER_PAGE - 1) // VIDEOS_PER_PAGE)
        self.page = (self.page - 1 + total_pages) % total_pages
        self.update_grid()

    # ---------------------- Helper ----------------------
    def scan_plugin_folder_for_videos(self):
        files = os.listdir(plugin_folder)
        for f in files:
            if f.lower().endswith(".mp4") and f not in [e["video"] for e in self.video_list]:
                self.video_list.append({"uid": "", "video": f})

    # ---------------------- Logging & clipboard ----------------------
    def log_message(self, text):
        print(text)

    def copy_last_uid_to_clipboard(self, event):
        if self.current_uid:
            QApplication.clipboard().setText(self.current_uid)
