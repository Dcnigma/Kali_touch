#!/usr/bin/env python3
import os
import sys
import json
from itertools import cycle
from PyQt6.QtWidgets import QWidget, QLabel, QProgressBar, QApplication
from PyQt6.QtGui import QPixmap, QFont, QPalette, QBrush
from PyQt6.QtCore import Qt, QTimer

plugin_folder = os.path.dirname(os.path.abspath(__file__))

# JSON files
REBECCA_JSON = os.path.join(plugin_folder, "rebecca.json")
REBECCA_XP_JSON = os.path.join(plugin_folder, "rebecca_xp.json")
FACES_DIR = os.path.join(plugin_folder, "oLed", "rebecca", "faces_rebecca")

# Photo frame positions & size
FRAME_X, FRAME_Y = 77, 70
FRAME_W, FRAME_H = 350, 350

# Text positions
NAME_X, NAME_Y = 473, 60
MOOD_X, MOOD_Y = 473, 170
LEVEL_X, LEVEL_Y = 473, 300

# Progress bar position & size
PROGRESS_X, PROGRESS_Y = 460, 410
PROGRESS_W, PROGRESS_H = 517, 67

LEVELS = [0, 50, 150, 350, 700, 1200]


class PassportPlugin(QWidget):
    def __init__(self):
        super().__init__()

        # ---------------------- Load JSON ----------------------
        self.load_json_data()

        # ---------------------- Fullscreen without title ----------------------
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint)
        self.showFullScreen()

        # ---------------------- Background ----------------------
        bg_path = os.path.join(plugin_folder, "passport.png")
        if os.path.exists(bg_path):
            pixmap = QPixmap(bg_path).scaled(
                self.size(),
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation
            )
            palette = QPalette()
            palette.setBrush(QPalette.ColorRole.Window, QBrush(pixmap))
            self.setPalette(palette)
            self.setAutoFillBackground(True)

        # ---------------------- Name ----------------------
        self.name_label = QLabel(self)
        self.name_label.setFont(QFont("Arial", 60))
        self.name_label.setText(self.rebecca_data.get("name", {}).get("firstname", "Unknown"))
        self.name_label.move(NAME_X, NAME_Y)
        self.name_label.setFixedWidth(self.width())
        self.name_label.setAlignment(Qt.AlignmentFlag.AlignLeft)

        # ---------------------- Mood ----------------------
        self.mood_label = QLabel(self)
        self.mood_label.setFont(QFont("Arial", 60))
        self.mood_label.setText(f"Mood: {self.rebecca_xp.get('mood', 'Neutral')}")
        self.mood_label.move(MOOD_X, MOOD_Y)
        self.mood_label.setFixedWidth(self.width())
        self.mood_label.setAlignment(Qt.AlignmentFlag.AlignLeft)

        # ---------------------- Level ----------------------
        self.level_label = QLabel(self)
        self.level_label.setFont(QFont("Arial", 60))
        self.level_label.setText(f"Level: {self.rebecca_xp.get('level', 0)}")
        self.level_label.move(LEVEL_X, LEVEL_Y)
        self.level_label.setFixedWidth(self.width())
        self.level_label.setAlignment(Qt.AlignmentFlag.AlignLeft)

        # ---------------------- XP Bar ----------------------
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
                border-radius: 15px;
                background-color: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 #47CC00, stop:1 #3D8F11
                );
            }
        """)

        # ---------------------- Face Frame ----------------------
        self.face_label = QLabel(self)
        self.face_label.setGeometry(FRAME_X, FRAME_Y, FRAME_W, FRAME_H)
        self.face_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.face_label.setStyleSheet("border-radius: 15px;")

        self.face_images = self.load_face_images()
        self.face_cycle = cycle(self.face_images)
        self.update_face()

        # ---------------------- Face Timer ----------------------
        self.face_timer = QTimer()
        self.face_timer.timeout.connect(self.update_face)
        self.face_timer.start(1000)

    # ---------------------- Load JSON ----------------------
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
                    FRAME_W, FRAME_H,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation
                )
                images.append(pixmap)
        return images

    def update_face(self):
        if self.face_images:
            self.face_label.setPixmap(next(self.face_cycle))

    # ---------------------- ESC key to exit ----------------------
    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.close()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = PassportPlugin()
    window.show()
    sys.exit(app.exec())
