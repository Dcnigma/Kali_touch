#!/usr/bin/env python3
import os
import sys
import json
import time
import subprocess
from PyQt6.QtWidgets import (
    QWidget, QLabel, QLineEdit, QPushButton, QVBoxLayout, QHBoxLayout,
    QGridLayout, QApplication, QSpacerItem, QSizePolicy
)
from PyQt6.QtGui import QPixmap, QPalette, QBrush
from PyQt6.QtCore import Qt, QTimer

# ---------------------- Paths ----------------------
plugin_folder = os.path.dirname(os.path.abspath(__file__))
if plugin_folder not in sys.path:
    sys.path.insert(0, plugin_folder)

VIDEO_FILE = os.path.join(plugin_folder, "videos.json")

# ---------------------- Try import MFRC522 ----------------------
try:
    import MFRC522
    LIB_AVAILABLE = True
except ImportError:
    LIB_AVAILABLE = False

# ---------------------- Constants ----------------------
ROWS = 4
COLUMNS = 2
VIDEOS_PER_PAGE = ROWS * COLUMNS


class RfidPlayerPlugin(QWidget):
    def __init__(self, parent=None, apps=None, cfg=None):
        super().__init__(parent)
        self.cfg = cfg
        self.current_uid = None
        self.my_subprocess = None
        self.video_map = {}
        self.unassigned_counter = 0
        self.page = 0

        # ---------------------- Window ----------------------
        self.setFixedSize(1015, 570)
        self.move(-50, 0)
        self.setWindowTitle("RFID Video Player")

        # ---------------------- Background ----------------------
        bg_path = os.path.join(plugin_folder, "background.png")
        if os.path.exists(bg_path):
            pixmap = QPixmap(bg_path).scaled(
                self.size(), Qt.AspectRatioMode.IgnoreAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            palette = self.palette()
            palette.setBrush(QPalette.ColorRole.Window, QBrush(pixmap))
            self.setAutoFillBackground(True)
            self.setPalette(palette)

        # ---------------------- Data ----------------------
        self.load_videos()
        self.scan_plugin_folder_for_videos()

        # ---------------------- UI ----------------------
        self.init_ui()

        if LIB_AVAILABLE:
            self.reader = MFRC522.MFRC522()
        else:
            self.log_message("MFRC522 library not available. Card reading disabled.")

        # ---------------------- Timers ----------------------
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

        # Spacer
        spacer_logo = QWidget()
        spacer_logo.setFixedHeight(20)
        main_layout.addWidget(spacer_logo)

        # Grid
        self.grid_widget = QWidget()
        self.grid_widget.setFixedSize(700, 300)
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

        # Save button
        self.save_button = QPushButton("Save")
        self.save_button.clicked.connect(self.save_videos)
        main_layout.addWidget(self.save_button, alignment=Qt.AlignmentFlag.AlignCenter)

        # Last scanned label
        self.last_scanned_label = QLabel("Last scanned: None")
        self.last_scanned_label.setStyleSheet("color: lightgrey; font-size: 18px;")
        self.last_scanned_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.last_scanned_label.mousePressEvent = self.copy_last_uid_to_clipboard
        main_layout.addWidget(self.last_scanned_label, alignment=Qt.AlignmentFlag.AlignCenter)

        # Spacer bottom
        main_layout.addItem(QSpacerItem(20, 40, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding))

        # Build grid
        self.uid_inputs = []
        self.video_inputs = []
        self.update_grid()

    # ---------------------- Grid ----------------------
    def update_grid(self):
        # clear previous widgets
        for i in reversed(range(self.grid_layout.count())):
            self.grid_layout.itemAt(i).widget().setParent(None)

        video_items = list(self.video_map.items())
        total_pages = max(1, (len(video_items) + VIDEOS_PER_PAGE - 1) // VIDEOS_PER_PAGE)
        self.page = min(self.page, total_pages - 1)

        start = self.page * VIDEOS_PER_PAGE
        end = start + VIDEOS_PER_PAGE
        page_videos = video_items[start:end]

        self.uid_inputs.clear()
        self.video_inputs.clear()

        for i, (uid, video) in enumerate(page_videos):
            row = i
            uid_label = QLabel(f"UID {start+i+1}:")
            uid_label.setStyleSheet("color: lightgrey; font-size: 18px;")
            uid_input = QLineEdit(uid if not uid.startswith("UNASSIGNED_") else "")
            uid_input.setStyleSheet("font-size: 16px;")
            video_input = QLineEdit(video)
            video_input.setStyleSheet("font-size: 16px;")
            self.grid_layout.addWidget(uid_label, row, 0)
            self.grid_layout.addWidget(uid_input, row, 1)
            self.grid_layout.addWidget(video_input, row, 2)
            self.uid_inputs.append(uid_input)
            self.video_inputs.append(video_input)

    def prev_page(self):
        self.page = (self.page - 1) % max(1, (len(self.video_map) + VIDEOS_PER_PAGE - 1) // VIDEOS_PER_PAGE)
        self.update_grid()

    def next_page(self):
        self.page = (self.page + 1) % max(1, (len(self.video_map) + VIDEOS_PER_PAGE - 1) // VIDEOS_PER_PAGE)
        self.update_grid()

    # ---------------------- Video handling ----------------------
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
                # play video if mapped
                if uid_str in self.video_map:
                    self.play_video_for_uid(uid_str)

    def uid_to_string(self, uid):
        return ''.join(format(i, '02X') for i in uid)

    # ---------------------- Videos JSON ----------------------
    def load_videos(self):
        if os.path.exists(VIDEO_FILE):
            try:
                with open(VIDEO_FILE, "r") as f:
                    self.video_map = json.load(f)
            except Exception as e:
                print(f"Error loading video map: {e}")
                self.video_map = {}
        else:
            # default example
            self.video_map = {
                "C0E961C5": "Fingerprint.mp4",
                "167B001E": "Password.mp4",
                "F93264E6": "Skull.mp4",
                "BEA65461": "stop"
            }
            self.save_videos()

    def save_videos(self):
        for uid_input, video_input in zip(self.uid_inputs, self.video_inputs):
            uid = uid_input.text().strip()
            video = video_input.text().strip()
            if uid and video:
                self.video_map[uid] = video
        try:
            with open(VIDEO_FILE, "w") as f:
                json.dump(self.video_map, f)
        except Exception as e:
            self.log_message(f"Error saving video map: {e}")
        self.update_grid()

    # ---------------------- Scan plugin folder ----------------------
    def scan_plugin_folder_for_videos(self):
        files = [f for f in os.listdir(plugin_folder) if f.lower().endswith(".mp4")]
        added = False
        for f in files:
            if f not in self.video_map.values():
                uid_placeholder = f"UNASSIGNED_{self.unassigned_counter}"
                self.video_map[uid_placeholder] = f
                self.unassigned_counter += 1
                added = True
        if added:
            self.save_videos()

    # ---------------------- Logging & clipboard ----------------------
    def log_message(self, text):
        print(text)

    def copy_last_uid_to_clipboard(self, event):
        if self.current_uid:
            QApplication.clipboard().setText(self.current_uid)
