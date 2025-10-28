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

ROWS_PER_PAGE = 4
COLUMNS = 2
VIDEO_FILE = os.path.join(plugin_folder, "videos.json")


class RfidPlayerPlugin(QWidget):
    def __init__(self, parent=None, apps=None, cfg=None):
        super().__init__(parent)
        self.cfg = cfg
        self.current_uid = None
        self.my_subprocess = None
        self.video_map = {}
        self.video_files = []
        self.page = 0
        self.uid_inputs = []
        self.video_inputs = []

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

        self.load_videos()
        self.scan_plugin_folder()
        self.init_ui()

        if LIB_AVAILABLE:
            self.reader = MFRC522.MFRC522()
        else:
            self.log_message(
                "MFRC522 Python library not available on this system.\n"
                "Place MFRC522.py in the same folder as this plugin to read cards."
            )

        # Timer for scanning cards
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

        spacer_logo = QWidget()
        spacer_logo.setFixedHeight(20)
        main_layout.addWidget(spacer_logo)

        # Grid for video mapping
        self.grid_widget = QWidget()
        self.grid_widget.setFixedSize(700, 320)
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
        pagination_layout.addWidget(self.next_button)
        main_layout.addLayout(pagination_layout)

        # Last scanned UID label
        self.last_scanned_label = QLabel("Last scanned: None")
        self.last_scanned_label.setStyleSheet("color: lightgrey; font-size: 18px;")
        self.last_scanned_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.last_scanned_label.mousePressEvent = self.copy_last_uid_to_clipboard
        main_layout.addWidget(self.last_scanned_label, alignment=Qt.AlignmentFlag.AlignCenter)

        # Save button
        self.save_button = QPushButton("Save")
        self.save_button.clicked.connect(self.save_videos)
        main_layout.addWidget(self.save_button, alignment=Qt.AlignmentFlag.AlignCenter)

        # Spacer
        main_layout.addItem(QSpacerItem(20, 40, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding))

        self.update_grid()

    # ---------------------- Load/save ----------------------
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
        # Update mapping from current inputs
        for uid_input, video_input in zip(self.uid_inputs, self.video_inputs):
            uid = uid_input.text().strip()
            video = video_input.text().strip()
            if video:
                if uid:
                    self.video_map[uid] = video
                elif video not in self.video_map.values():
                    # Keep unlinked videos as empty UID
                    self.video_map[""] = video
        try:
            with open(VIDEO_FILE, "w") as f:
                json.dump(self.video_map, f)
            self.log_message("Video mapping saved.")
        except Exception as e:
            self.log_message(f"Error saving video map: {e}")
        self.update_grid()

    # ---------------------- Scan plugin folder for new videos ----------------------
    def scan_plugin_folder(self):
        all_videos = [f for f in os.listdir(plugin_folder) if f.lower().endswith(".mp4")]
        self.video_files = all_videos
        # Add unlisted videos to mapping with empty UID
        for v in all_videos:
            if v not in self.video_map.values():
                self.video_map[""] = v

    # ---------------------- Pagination ----------------------
    def prev_page(self):
        total_pages = max(1, (len(self.video_map) + ROWS_PER_PAGE - 1) // ROWS_PER_PAGE)
        self.page = (self.page - 1 + total_pages) % total_pages
        self.update_grid()

    def next_page(self):
        total_pages = max(1, (len(self.video_map) + ROWS_PER_PAGE - 1) // ROWS_PER_PAGE)
        self.page = (self.page + 1) % total_pages
        self.update_grid()

    # ---------------------- Update grid ----------------------
    def update_grid(self):
        # Clear current grid
        for i in reversed(range(self.grid_layout.count())):
            widget = self.grid_layout.itemAt(i).widget()
            if widget:
                widget.setParent(None)
        self.uid_inputs = []
        self.video_inputs = []

        items = list(self.video_map.items())
        start_index = self.page * ROWS_PER_PAGE
        end_index = start_index + ROWS_PER_PAGE
        page_items = items[start_index:end_index]

        for i, (uid, video) in enumerate(page_items):
            uid_label = QLabel(f"UID:")
            uid_label.setStyleSheet("color: lightgrey; font-size: 16px;")
            uid_input = QLineEdit(uid)
            uid_input.setStyleSheet("font-size: 14px;")
            video_input = QLineEdit(video)
            video_input.setStyleSheet("font-size: 14px;")
            self.grid_layout.addWidget(uid_label, i, 0)
            self.grid_layout.addWidget(uid_input, i, 1)
            self.grid_layout.addWidget(video_input, i, 2)
            self.uid_inputs.append(uid_input)
            self.video_inputs.append(video_input)

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
        if self.my_subprocess:
            try:
                self.my_subprocess.terminate()
            except Exception:
                pass
            self.my_subprocess.wait(timeout=1)
        self.my_subprocess = None

    def play_video_for_uid(self, uid_str):
        if uid_str in self.video_map and self.video_map[uid_str]:
            video_file = self.video_map[uid_str]
            if video_file.lower() == "stop":
                self.stop_current_video()
                return
            self.stop_current_video()
            video_path = os.path.join(plugin_folder, video_file)
            if os.path.exists(video_path):
                cmd = ["/bin/ffplay", "-fs", "-autoexit", "-loop", "0", video_path]
                self.my_subprocess = subprocess.Popen(cmd, stdin=subprocess.PIPE,
                                                     stdout=subprocess.DEVNULL,
                                                     stderr=subprocess.DEVNULL)

    # ---------------------- Logging & clipboard ----------------------
    def log_message(self, text):
        print(text)

    def copy_last_uid_to_clipboard(self, event):
        if self.current_uid:
            QApplication.clipboard().setText(self.current_uid)
