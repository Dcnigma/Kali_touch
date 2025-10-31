#!/usr/bin/env python3
import os
import sys
import json
from itertools import cycle
from PyQt6.QtWidgets import QWidget, QLabel, QApplication, QProgressBar
from PyQt6.QtGui import QPixmap, QFont, QBrush, QPalette
from PyQt6.QtCore import Qt, QTimer

plugin_folder = os.path.dirname(os.path.abspath(__file__))

REBECCA_JSON = os.path.join(plugin_folder, "rebecca.json")
REBECCA_XP_JSON = os.path.join(plugin_folder, "rebecca_xp.json")
FACES_DIR = os.path.join(plugin_folder, "oLed", "rebecca", "faces_rebecca")

LEVELS = [0, 50, 150, 350, 700, 1200]


class PassportPlugin(QWidget):
    def __init__(self, parent=None, apps=None, cfg=None):
        super().__init__(parent)
        self.apps = apps
        self.cfg = cfg

        # ---------------- Fullscreen setup ----------------
        screen = QApplication.primaryScreen().geometry()
        screen_w, screen_h = screen.width(), screen.height()
        self.setGeometry(0, 0, screen_w, screen_h)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.showFullScreen()
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        # Scaling factors (based on 1015x570 base)
        self.scale_x = screen_w / 1015
        self.scale_y = screen_h / 570
        self.scale = min(self.scale_x, self.scale_y)

        self.load_json_data()

        # ---------------- Background ----------------
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

        # ---------------- Helper for scaling ----------------
        def S(val): return int(val * self.scale)

        # ---------------- Labels ----------------
        self.name_label = QLabel(self)
        self.name_label.setFont(QFont("Arial", S(60)))
        self.name_label.setText(self.rebecca_data.get("name", {}).get("firstname", "Unknown"))
        self.name_label.move(S(473), S(60))
        self.name_label.setFixedWidth(screen_w)
        self.name_label.setAlignment(Qt.AlignmentFlag.AlignLeft)

        self.mood_label = QLabel(self)
        self.mood_label.setFont(QFont("Arial", S(60)))
        self.mood_label.setText(f"Mood: {self.rebecca_xp.get('mood', 'Neutral')}")
        self.mood_label.move(S(473), S(170))
        self.mood_label.setFixedWidth(screen_w)
        self.mood_label.setAlignment(Qt.AlignmentFlag.AlignLeft)

        self.level_label = QLabel(self)
        self.level_label.setFont(QFont("Arial", S(60)))
        self.level_label.setText(f"Level: {self.rebecca_xp.get('level', 0)}")
        self.level_label.move(S(473), S(300))
        self.level_label.setFixedWidth(screen_w)
        self.level_label.setAlignment(Qt.AlignmentFlag.AlignLeft)

        # ---------------- Progress Bar ----------------
        self.progress = QProgressBar(self)
        self.progress.setGeometry(S(460), S(410), S(517), S(67))
        self.progress.setMaximum(LEVELS[-1])
        self.progress.setValue(self.rebecca_xp.get("xp", 0))
        self.progress.setFormat("XP: %v/%m")
        self.progress.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.progress.setStyleSheet(f"""
            QProgressBar {{
                border: {S(3)}px solid #000000;
                border-radius: {S(15)}px;
                background-color: #9CED21;
                font: {S(24)}px 'Arial';
                color: white;
            }}
            QProgressBar::chunk {{
                border: {S(3)}px solid #000000;            
                border-radius: {S(15)}px;
                background-color: qlineargradient(
                    x1: 0, y1: 0, x2: 1, y2: 0,
                    stop: 0 #47CC00, stop: 1 #3D8F11
                );
            }}
        """)

        # ---------------- Face Frame ----------------
        self.face_label = QLabel(self)
        self.face_label.setGeometry(S(77), S(70), S(350), S(350))
        self.face_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.face_label.setStyleSheet(f"""
            border-radius: {S(15)}px;
            border: {S(5)}px solid #000;
        """)

        # Load and animate faces
        self.face_images = self.load_face_images(S)
        self.face_cycle = cycle(self.face_images)
        self.update_face()

        self.face_timer = QTimer()
        self.face_timer.timeout.connect(self.update_face)
        self.face_timer.start(1000)

    # ---------------- JSON Loading ----------------
    def load_json_data(self):
        self.rebecca_data = {}
        self.rebecca_xp = {}
        if os.path.exists(REBECCA_JSON):
            with open(REBECCA_JSON, "r") as f:
                self.rebecca_data = json.load(f)
        if os.path.exists(REBECCA_XP_JSON):
            with open(REBECCA_XP_JSON, "r") as f:
                self.rebecca_xp = json.load(f)

    # ---------------- Face Images ----------------
    def load_face_images(self, S):
        images = []
        for filename in ["LOOK_L.png", "LOOK_R.png", "LOOK_R_HAPPY.png", "LOOK_L_HAPPY.png"]:
            path = os.path.join(FACES_DIR, filename)
            if os.path.exists(path):
                pixmap = QPixmap(path).scaled(
                    S(350), S(350),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation
                )
                images.append(pixmap)
        return images

    def update_face(self):
        if self.face_images:
            self.face_label.setPixmap(next(self.face_cycle))

    # ---------------- Escape key to exit ----------------
    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            QApplication.quit()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = PassportPlugin()
    window.show()
    sys.exit(app.exec())
