#!/usr/bin/env python3
import os
import sys
import json
from itertools import cycle
from PyQt6.QtWidgets import (
    QWidget, QLabel, QPushButton, QApplication, QProgressBar, QVBoxLayout, QSpacerItem, QSizePolicy
)
from PyQt6.QtGui import QPixmap, QFont, QBrush, QPalette
from PyQt6.QtCore import Qt, QTimer

plugin_folder = os.path.dirname(os.path.abspath(__file__))

# JSON files
REBECCA_JSON = os.path.join(plugin_folder, "rebecca.json")
REBECCA_XP_JSON = os.path.join(plugin_folder, "rebecca_xp.json")
FACES_DIR = os.path.join(plugin_folder, "oLed", "rebecca", "faces_rebecca")

# Photo frame positions & size
FRAME_X, FRAME_Y = 77, 70
FRAME_W, FRAME_H = 350, 350

# Right panel positions
RIGHT_X = 473
NAME_Y = 0  # layout will handle vertical spacing
MOOD_Y = 0
LEVEL_Y = 0

# Progress bar size
PROGRESS_W, PROGRESS_H = 517, 67

LEVELS = [0, 50, 150, 350, 700, 1200]


class PassportPlugin(QWidget):
    def __init__(self, parent=None, apps=None, cfg=None):
        super().__init__(parent)
        self.apps = apps
        self.cfg = cfg

        self.setFixedSize(1015, 570)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.showFullScreen()

        # ---------------------- Background ----------------------
        bg_path = os.path.join(plugin_folder, "passport.png")
        if os.path.exists(bg_path):
            pixmap = QPixmap(bg_path).scaled(
                self.size(), Qt.AspectRatioMode.IgnoreAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            palette = self.palette()
            palette.setBrush(QPalette.ColorRole.Window, QBrush(pixmap))
            self.setAutoFillBackground(True)
            self.setPalette(palette)

        # ---------------------- Load JSON ----------------------
        self.load_json_data()

        # ---------------------- Face Frame ----------------------
        self.face_label = QLabel(self)
        self.face_label.setGeometry(FRAME_X, FRAME_Y, FRAME_W, FRAME_H)
        self.face_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.face_label.setStyleSheet("""
            border-radius: 15px;
            border: 15px solid #000;
            overflow: hidden;
        """)
        self.face_images = self.load_face_images()
        self.face_cycle = cycle(self.face_images)
        self.update_face()
        self.face_timer = QTimer()
        self.face_timer.timeout.connect(self.update_face)
        self.face_timer.start(1000)

        # ---------------------- Right Panel Layout ----------------------
        self.right_widget = QWidget(self)
        self.right_widget.setGeometry(RIGHT_X, 60, self.width() - RIGHT_X - 50, self.height() - 120)
        self.right_layout = QVBoxLayout(self.right_widget)
        self.right_layout.setSpacing(20)
        self.right_layout.setContentsMargins(0, 0, 0, 0)

        # Name label
        self.name_label = QLabel(self.rebecca_data.get("name", {}).get("firstname", "Unknown"))
        self.name_label.setFont(QFont("Arial", 60))
        self.name_label.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self.right_layout.addWidget(self.name_label)

        # Mood label
        self.mood_label = QLabel(f"Mood: {self.rebecca_xp.get('mood', 'Neutral')}")
        self.mood_label.setFont(QFont("Arial", 60))
        self.mood_label.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self.right_layout.addWidget(self.mood_label)

        # Level label
        self.level_label = QLabel(f"Level: {self.rebecca_xp.get('level', 0)}")
        self.level_label.setFont(QFont("Arial", 60))
        self.level_label.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self.right_layout.addWidget(self.level_label)

        # Spacer
        self.right_layout.addSpacerItem(QSpacerItem(0, 20, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding))

        # Progress bar
        self.progress = QProgressBar()
        self.progress.setMaximum(LEVELS[-1])
        self.progress.setValue(self.rebecca_xp.get("xp", 0))
        self.progress.setFormat("XP: %v/%m")
        self.progress.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.progress.setFixedHeight(PROGRESS_H)
        self.progress.setStyleSheet("""
            QProgressBar {
                border: 3px solid #000000;
                border-radius: 15px;
                background-color: #9CED21;
                text-align: center;
                font: 24px 'Arial';
                color: white;
            }
            QProgressBar::chunk {
                border: 5px solid #000000;            
                border-radius: 15px;
                background-color: qlineargradient(
                x1: 0, y1: 0, x2: 1, y2: 0,
                stop: 0 #47CC00, stop: 1 #3D8F11
                );
                margin: 0.01px;
            }
        """)
        self.right_layout.addWidget(self.progress)

        # ---------------------- Close Button ----------------------
        self.close_btn = QPushButton("Close", self)
        self.close_btn.setGeometry(self.width() - 120, 20, 100, 40)
        self.close_btn.clicked.connect(self.close)

    # ---------------------- JSON Loading ----------------------
    def load_json_data(self):
        self.rebecca_data = {}
        self.rebecca_xp = {}
        if os.path.exists(REBECCA_JSON):
            with open(REBECCA_JSON, "r") as f:
                self.rebecca_data = json.load(f)
        if os.path.exists(REBECCA_XP_JSON):
            with open(REBECCA_XP_JSON, "r") as f:
                self.rebecca_xp = json.load(f)

    # ---------------------- Face Animation ----------------------
    def load_face_images(self):
        images = []
        for filename in ["LOOK_L.png", "LOOK_R.png", "LOOK_R_HAPPY.png", "LOOK_L_HAPPY.png"]:
            path = os.path.join(FACES_DIR, filename)
            if os.path.exists(path):
                pixmap = QPixmap(path).scaled(
                    FRAME_W, FRAME_H, Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation
                )
                images.append(pixmap)
        return images

    def update_face(self):
        if self.face_images:
            self.face_label.setPixmap(next(self.face_cycle))


# ---------------------- Entry Point ----------------------
if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = PassportPlugin()
    window.show()
    sys.exit(app.exec())
