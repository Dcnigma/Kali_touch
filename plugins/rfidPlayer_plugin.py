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
from PyQt6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve

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

CARDS_PER_PAGE = 8  # Rows per page
ANIMATION_STEPS = 10
ANIMATION_INTERVAL = 50  # ms
VIDEO_FILE = os.path.join(plugin_folder, "video.json")


class myRFIDReader(MFRC522.MFRC522):
    """RFID reader that only reports new cards."""
    def __init__(self, bus=0, dev=0):
        super().__init__(bus=bus, dev=dev)
        self.key = None
        self.keyIn = False
        self.keyValidCount = 0

    def Read(self):
        status, TagType = self.MFRC522_Request(self.PICC_REQIDL)
        if status == self.MI_OK:
            status, uid = self.MFRC522_SelectTagSN()
            if status == self.MI_OK:
                self.keyIn = True
                self.keyValidCount = 2
                if self.key != uid:
                    self.key = uid
                    if uid is None:
                        return False
                    return True
        else:
            if self.keyIn:
                if self.keyValidCount > 0:
                    self.keyValidCount -= 1
                else:
                    self.keyIn = False
                    self.key = None
        return False


class RFIDVideoPlugin(QWidget):
    def __init__(self, parent=None, apps=None, cfg=None):
        super().__init__(parent)
        self.cfg = cfg
        self.setWindowTitle("RFID Video Player")
        self.setFixedSize(1015, 570)
        self.move(-50, 0)

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

        self.reader = myRFIDReader() if LIB_AVAILABLE else None
        self.video_map = {}  # uid -> videoname
        self.video_process = None

        self.load_videos()
        self.init_ui()

        # Timers
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
            pixmap = QPixmap(logo_path).scaled(200, 50, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            self.logo_label.setPixmap(pixmap)
            self.logo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(self.logo_label, alignment=Qt.AlignmentFlag.AlignCenter)

        # Spacer
        main_layout.addWidget(QWidget(), 1)

        # Grid container
        self.grid_widget = QWidget()
        self.grid_widget.setFixedSize(500, 320)
        self.grid_layout = QGridLayout()
        self.grid_widget.setLayout(self.grid_layout)
        self.grid_widget.setStyleSheet("background-color: rgba(0,0,0,120); border-radius: 10px;")
        main_layout.addWidget(self.grid_widget, alignment=Qt.AlignmentFlag.AlignCenter)

        # Headers
        self.grid_layout.addWidget(QLabel("UID"), 0, 0)
        self.grid_layout.addWidget(QLabel("Video File"), 0, 1)
        self.uid_inputs = []
        self.video_inputs = []

        for i, (uid, videofile) in enumerate(self.video_map.items()):
            self.add_row(i + 1, uid, videofile)

        # Buttons to save
        btn_layout = QHBoxLayout()
        self.save_button = QPushButton("Save")
        self.save_button.clicked.connect(self.save_videos)
        btn_layout.addWidget(self.save_button)
        main_layout.addLayout(btn_layout)

        # Fade-in
        self.grid_widget.setWindowOpacity(0.0)
        fade_in = QPropertyAnimation(self.grid_widget, b"windowOpacity")
        fade_in.setDuration(1500)
        fade_in.setStartValue(0.0)
        fade_in.setEndValue(1.0)
        fade_in.setEasingCurve(QEasingCurve.Type.InOutCubic)
        fade_in.start()

    def add_row(self, row, uid, videofile):
        uid_input = QLineEdit(uid)
        video_input = QLineEdit(videofile)
        self.grid_layout.addWidget(uid_input, row, 0)
        self.grid_layout.addWidget(video_input, row, 1)
        self.uid_inputs.append(uid_input)
        self.video_inputs.append(video_input)

    # ---------------------- RFID card check ----------------------
    def check_card(self):
        if not self.reader:
            return
        if self.reader.Read():
            uid_str = ''.join(format(i, '02X') for i in self.reader.key)
            print(f"Card scanned: {uid_str}")
            if uid_str in self.video_map:
                self.play_video(self.video_map[uid_str])

    # ---------------------- Video playback ----------------------
    def play_video(self, videofile):
        self.stop_video()
        if videofile == "stop":
            return
        filepath = os.path.join(plugin_folder, videofile)
        if os.path.exists(filepath):
            self.video_process = subprocess.Popen(["/bin/ffplay", "-fs", "-autoexit", filepath],
                                                  stdin=subprocess.PIPE,
                                                  stdout=subprocess.PIPE,
                                                  stderr=subprocess.PIPE)

    def stop_video(self):
        if self.video_process:
            try:
                self.video_process.terminate()
            except Exception:
                pass
            time.sleep(0.5)
            self.video_process = None

    # ---------------------- Save/load JSON ----------------------
    def save_videos(self):
        new_map = {self.uid_inputs[i].text(): self.video_inputs[i].text() for i in range(len(self.uid_inputs))}
        self.video_map = new_map
        try:
            with open(VIDEO_FILE, "w") as f:
                json.dump(self.video_map, f)
        except Exception as e:
            print(f"Error saving video map: {e}")

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
