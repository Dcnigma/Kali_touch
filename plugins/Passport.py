#!/usr/bin/env python3
import os
import sys
import json
from itertools import cycle
from PyQt6.QtWidgets import QWidget, QLabel, QProgressBar, QApplication
from PyQt6.QtGui import QPixmap, QFont, QBrush, QPalette
from PyQt6.QtCore import Qt, QTimer

plugin_folder = os.path.dirname(os.path.abspath(__file__))

# JSON files
REBECCA_JSON = os.path.join(plugin_folder, "rebecca.json")
REBECCA_XP_JSON = os.path.join(plugin_folder, "rebecca_xp.json")
FACES_DIR = os.path.join(plugin_folder, "oLed", "rebecca", "faces_rebecca")

# Original design sizes (used for scaling)
ORIG_W, ORIG_H = 1015, 570

# Positions & sizes (original design)
FRAME_X, FRAME_Y, FRAME_W, FRAME_H = 77, 70, 350, 350
NAME_X, NAME_Y = 473, 60
MOOD_X, MOOD_Y = 473, 170
LEVEL_X, LEVEL_Y = 473, 300
PROGRESS_X, PROGRESS_Y, PROGRESS_W, PROGRESS_H = 460, 410, 517, 67
LEVELS = [0, 50, 150, 350, 700, 1200]

class PassportPlugin(QWidget):
    def __init__(self):
        super().__init__()
        self.load_json_data()

        # Fullscreen and no window decorations
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint)
        self.showFullScreen()

        screen_w = self.screen().size().width()
        screen_h = self.screen().size().height()
        self.scale_x = screen_w / ORIG_W
        self.scale_y = screen_h / ORIG_H

        # Background
        bg_path = os.path.join(plugin_folder, "passport.png")
        if os.path.exists(bg_path):
            pixmap = QPixmap(bg_path).scaled(
                screen_w, screen_h, Qt.AspectRatioMode.IgnoreAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            palette = self.palette()
            palette.setBrush(QPalette.ColorRole.Window, QBrush(pixmap))
            self.setAutoFillBackground(True)
            self.setPalette(palette)

        # Name label
        self.name_label = QLabel(self)
        self.name_label.setFont(QFont("Arial", int(60*self.scale_y)))
        self.name_label.setText(self.rebecca_data.get("name", {}).get("firstname", "Unknown"))
        self.name_label.move(int(NAME_X*self.scale_x), int(NAME_Y*self.scale_y))
        self.name_label.setFixedWidth(int(500*self.scale_x))
        self.name_label.setAlignment(Qt.AlignmentFlag.AlignLeft)

        # Mood label
        self.mood_label = QLabel(self)
        self.mood_label.setFont(QFont("Arial", int(60*self.scale_y)))
        self.mood_label.setText(f"Mood: {self.rebecca_xp.get('mood', 'Neutral')}")
        self.mood_label.move(int(MOOD_X*self.scale_x), int(MOOD_Y*self.scale_y))
        self.mood_label.setFixedWidth(int(500*self.scale_x))
        self.mood_label.setAlignment(Qt.AlignmentFlag.AlignLeft)

        # Level label
        self.level_label = QLabel(self)
        self.level_label.setFont(QFont("Arial", int(60*self.scale_y)))
        self.level_label.setText(f"Level: {self.rebecca_xp.get('level', 0)}")
        self.level_label.move(int(LEVEL_X*self.scale_x), int(LEVEL_Y*self.scale_y))
        self.level_label.setFixedWidth(int(500*self.scale_x))
        self.level_label.setAlignment(Qt.AlignmentFlag.AlignLeft)

        # Progress bar
        self.progress = QProgressBar(self)
        self.progress.setGeometry(
            int(PROGRESS_X*self.scale_x),
            int(PROGRESS_Y*self.scale_y),
            int(PROGRESS_W*self.scale_x),
            int(PROGRESS_H*self.scale_y)
        )
        self.progress.setMaximum(LEVELS[-1])
        self.progress.setValue(self.rebecca_xp.get("xp", 0))
        self.progress.setFormat("XP: %v/%m")
        self.progress.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.progress.setStyleSheet(f"""
            QProgressBar {{
                border: 3px solid #000000;
                border-radius: {int(15*self.scale_y)}px;
                background-color: #9CED21;
                text-align: center;
                font: {int(24*self.scale_y)}px 'Arial';
                color: white;
            }}
            QProgressBar::chunk {{
                border: 5px solid #000000;
                border-radius: {int(15*self.scale_y)}px;
                background-color: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 #47CC00, stop:1 #3D8F11
                );
                margin: 0.01px;
            }}
        """)

        # Face label
        self.face_label = QLabel(self)
        self.face_label.setGeometry(
            int(FRAME_X*self.scale_x),
            int(FRAME_Y*self.scale_y),
            int(FRAME_W*self.scale_x),
            int(FRAME_H*self.scale_y)
        )
        self.face_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.face_label.setStyleSheet(f"""
            border-radius: {int(15*self.scale_y)}px;
            border: 15px solid #000;
        """)

        self.face_images = self.load_face_images()
        self.face_cycle = cycle(self.face_images)
        self.update_face()

        self.face_timer = QTimer()
        self.face_timer.timeout.connect(self.update_face)
        self.face_timer.start(1000)

    def load_json_data(self):
        self.rebecca_data = {}
        self.rebecca_xp = {}
        if os.path.exists(REBECCA_JSON):
            with open(REBECCA_JSON, "r") as f:
                self.rebecca_data = json.load(f)
        if os.path.exists(REBECCA_XP_JSON):
            with open(REBECCA_XP_JSON, "r") as f:
                self.rebecca_xp = json.load(f)

    def load_face_images(self):
        images = []
        for filename in ["LOOK_L.png", "LOOK_R.png", "LOOK_R_HAPPY.png", "LOOK_L_HAPPY.png"]:
            path = os.path.join(FACES_DIR, filename)
            if os.path.exists(path):
                pixmap = QPixmap(path).scaled(
                    int(FRAME_W*self.scale_x),
                    int(FRAME_H*self.scale_y),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation
                )
                images.append(pixmap)
        return images

    def update_face(self):
        if self.face_images:
            self.face_label.setPixmap(next(self.face_cycle))

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.close()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = PassportPlugin()
    window.show()
    sys.exit(app.exec())
