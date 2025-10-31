#!/usr/bin/env python3
import os
import sys
import json
from itertools import cycle
from PyQt6.QtWidgets import QWidget, QLabel, QApplication, QProgressBar
from PyQt6.QtGui import QPixmap, QFont
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

        # ---------- Fullscreen setup ----------
        screen = QApplication.primaryScreen().geometry()
        screen_w, screen_h = screen.width(), screen.height()
        self.setGeometry(0, 0, screen_w, screen_h)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.showFullScreen()
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        # scaling helper (relative to 1015x570 base)
        self.scale = min(screen_w / 1015, screen_h / 570)
        def S(val): return int(val * self.scale)

        # ---------- Load JSON ----------
        self.load_json_data()

        # ---------- Background ----------
        bg_path = os.path.join(plugin_folder, "passport.png")
        self.bg_label = QLabel(self)
        if os.path.exists(bg_path):
            bg_pixmap = QPixmap(bg_path).scaled(screen_w, screen_h, Qt.AspectRatioMode.IgnoreAspectRatio)
            self.bg_label.setPixmap(bg_pixmap)
        self.bg_label.setGeometry(0, 0, screen_w, screen_h)
        self.bg_label.lower()  # background sits below everything

        # ---------- Labels ----------
        name = self.rebecca_data.get("name", {}).get("firstname", "Unknown")
        mood = self.rebecca_xp.get("mood", "Neutral")
        level = self.rebecca_xp.get("level", 0)
        xp_val = self.rebecca_xp.get("xp", 0)

        self.name_label = QLabel(f"{name}", self)
        self.name_label.setFont(QFont("Arial", S(60)))
        self.name_label.move(S(473), S(60))
        self.name_label.setStyleSheet("color: white; background: transparent;")

        self.mood_label = QLabel(f"Mood: {mood}", self)
        self.mood_label.setFont(QFont("Arial", S(60)))
        self.mood_label.move(S(473), S(170))
        self.mood_label.setStyleSheet("color: white; background: transparent;")

        self.level_label = QLabel(f"Level: {level}", self)
        self.level_label.setFont(QFont("Arial", S(60)))
        self.level_label.move(S(473), S(300))
        self.level_label.setStyleSheet("color: white; background: transparent;")

        # ---------- Progress Bar ----------
        self.progress = QProgressBar(self)
        self.progress.setGeometry(S(460), S(410), S(517), S(67))
        self.progress.setMaximum(LEVELS[-1])
        self.progress.setValue(xp_val)
        self.progress.setFormat("XP: %v/%m")
        self.progress.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.progress.setStyleSheet(f"""
            QProgressBar {{
                border: {S(3)}px solid #000;
                border-radius: {S(15)}px;
                background-color: #9CED21;
                font: {S(24)}px 'Arial';
                color: black;
            }}
            QProgressBar::chunk {{
                border-radius: {S(15)}px;
                background-color: qlineargradient(
                    x1: 0, y1: 0, x2: 1, y2: 0,
                    stop: 0 #47CC00, stop: 1 #3D8F11
                );
            }}
        """)

        # ---------- Face Frame ----------
        self.face_label = QLabel(self)
        self.face_label.setGeometry(S(77), S(70), S(350), S(350))
        self.face_label.setStyleSheet(f"border-radius: {S(15)}px; border: {S(5)}px solid #000; background: transparent;")
        self.face_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Load faces
        self.face_images = self.load_face_images(S)
        if not self.face_images:
            print("[DEBUG] No face images loaded from:", FACES_DIR)
        self.face_cycle = cycle(self.face_images)
        self.update_face()

        # Timer
        self.face_timer = QTimer()
        self.face_timer.timeout.connect(self.update_face)
        self.face_timer.start(1000)

        # Bring foreground elements above background
        for widget in [self.face_label, self.name_label, self.mood_label, self.level_label, self.progress]:
            widget.raise_()

        print(f"[DEBUG] Loaded name={name}, mood={mood}, level={level}, xp={xp_val}")

    # ---------- JSON ----------
    def load_json_data(self):
        self.rebecca_data = {}
        self.rebecca_xp = {}
        if os.path.exists(REBECCA_JSON):
            with open(REBECCA_JSON, "r") as f:
                self.rebecca_data = json.load(f)
        if os.path.exists(REBECCA_XP_JSON):
            with open(REBECCA_XP_JSON, "r") as f:
                self.rebecca_xp = json.load(f)

    # ---------- Faces ----------
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

    # ---------- ESC quits ----------
    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            QApplication.quit()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = PassportPlugin()
    window.show()
    sys.exit(app.exec())
