#!/usr/bin/env python3
import os
import sys
import json
from itertools import cycle
from PyQt6.QtWidgets import (
    QWidget, QLabel, QPushButton, QApplication, QProgressBar
)
from PyQt6.QtGui import QPixmap, QFont
from PyQt6.QtCore import Qt, QTimer

plugin_folder = os.path.dirname(os.path.abspath(__file__))

# JSON files
REBECCA_JSON = os.path.join(plugin_folder, "rebecca.json")
REBECCA_XP_JSON = os.path.join(plugin_folder, "rebecca_xp.json")
FACES_DIR = os.path.join(plugin_folder, "oLed", "rebecca", "faces_rebecca")

LEVELS = [0, 50, 150, 350, 700, 1200]

# Face frame size
FRAME_W, FRAME_H = 350, 350

# Precise positions (adjust these as needed)
FACE_X, FACE_Y = 0, 0
NAME_X, NAME_Y = 0, 0
MOOD_X, MOOD_Y = 0, 0
LEVEL_X, LEVEL_Y = 0, 0
PROGRESS_X, PROGRESS_Y, PROGRESS_W, PROGRESS_H = 0, 0, 0, 0
CLOSE_X, CLOSE_Y, CLOSE_W, CLOSE_H = 895, 520, 100, 40


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
        self.bg_label = QLabel(self)
        self.bg_label.setGeometry(0, 0, self.width(), self.height())
        if os.path.exists(bg_path):
            pixmap = QPixmap(bg_path).scaled(
                self.size(), Qt.AspectRatioMode.IgnoreAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            self.bg_label.setPixmap(pixmap)
        self.bg_label.show()

        # ---------------------- Load JSON ----------------------
        self.load_json_data()

        # ---------------------- Face ----------------------
        self.face_label = QLabel(self)
        self.face_label.setGeometry(FACE_X, FACE_Y, FRAME_W, FRAME_H)
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

        # ---------------------- Labels ----------------------
        self.name_label = QLabel(self)
        self.name_label.setText(self.rebecca_data.get("name", {}).get("firstname", "Unknown"))
        self.name_label.setFont(QFont("Arial", 60))
        self.name_label.setStyleSheet("color: white;")
        self.name_label.setGeometry(NAME_X, NAME_Y, 500, 70)

        self.mood_label = QLabel(self)
        self.mood_label.setText(f"Mood: {self.rebecca_xp.get('mood', 'Neutral')}")
        self.mood_label.setFont(QFont("Arial", 60))
        self.mood_label.setStyleSheet("color: white;")
        self.mood_label.setGeometry(MOOD_X, MOOD_Y, 500, 70)

        self.level_label = QLabel(self)
        self.level_label.setText(f"Level: {self.rebecca_xp.get('level', 0)}")
        self.level_label.setFont(QFont("Arial", 60))
        self.level_label.setStyleSheet("color: white;")
        self.level_label.setGeometry(LEVEL_X, LEVEL_Y, 500, 70)

        # ---------------------- Progress Bar ----------------------
        self.progress = QProgressBar(self)
        self.progress.setGeometry(PROGRESS_X, PROGRESS_Y, PROGRESS_W, PROGRESS_H)
        self.progress.setMaximum(LEVELS[-1])
        self.progress.setValue(self.rebecca_xp.get("xp", 0))
        self.progress.setFormat("XP: %v/%m")
        self.progress.setAlignment(Qt.AlignmentFlag.AlignCenter)
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

        # ---------------------- Close Button ----------------------
        self.close_btn = QPushButton("Close", self)
        self.close_btn.setGeometry(CLOSE_X, CLOSE_Y, CLOSE_W, CLOSE_H)
        self.close_btn.clicked.connect(self.close)
        self.close_btn.show()

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
