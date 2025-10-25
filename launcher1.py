#!/usr/bin/env python3
import sys
import os
import json
import subprocess
import signal
import time
import psutil
from PyQt6.QtWidgets import (
    QApplication, QWidget, QPushButton, QGridLayout, QLabel,
    QVBoxLayout, QHBoxLayout
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QPixmap, QIcon

CONFIG_FILE = "apps.json"

# Load app definitions
with open(CONFIG_FILE, "r") as f:
    raw_apps = json.load(f)

apps = []
for name, cfg in raw_apps.items():
    cfg["name"] = name
    apps.append(cfg)


class OverlayLauncher(QWidget):
    def __init__(self, apps, screen_width=1024, screen_height=800):
        super().__init__()
        self.setFixedSize(screen_width, screen_height)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setStyleSheet("background-color: rgba(0, 0, 0, 220);")
        self.apps = apps
        self.page = 0
        self.apps_per_page = 9
        self.current_process = None
        self.current_plugin = None

        # ---------- Grid area ----------
        self.grid = QGridLayout()
        self.grid.setSpacing(10)
        self.grid.setContentsMargins(80, 60, 80, 100)

        # ---------- Bottom navigation ----------
        bottom_bar = QHBoxLayout()
        bottom_bar.setContentsMargins(40, 0, 40, 20)
        bottom_bar.setSpacing(20)

        # Stop button (bottom-left)
        self.stop_btn = QPushButton("Stop Launcher")
        self.stop_btn.setFixedSize(180, 60)
        self.stop_btn.setStyleSheet("font-size: 18px; background-color: gray; color: white; border-radius: 10px;")
        self.stop_btn.clicked.connect(self.stop_launcher)
        bottom_bar.addWidget(self.stop_btn, alignment=Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom)

        # Spacer
        bottom_bar.addStretch(1)

        # Page label (center)
        self.page_label = QLabel()
        self.page_label.setStyleSheet("font-size: 18px; color: white;")
        bottom_bar.addWidget(self.page_label, alignment=Qt.AlignmentFlag.AlignVCenter)

        # Spacer
        bottom_bar.addStretch(1)

        # Prev / Next (bottom-right)
        self.prev_btn = QPushButton("← Prev")
        self.next_btn = QPushButton("Next →")
        btn_style = "font-size: 18px; background-color: #555; color: white; border-radius: 10px; padding: 10px;"
        self.prev_btn.setStyleSheet(btn_style)
        self.next_btn.setStyleSheet(btn_style)
        self.prev_btn.clicked.connect(self.prev_page)
        self.next_btn.clicked.connect(self.next_page)
        bottom_bar.addWidget(self.prev_btn)
        bottom_bar.addWidget(self.next_btn)

        # ---------- Main layout ----------
        main_layout = QVBoxLayout(self)
        main_layout.addLayout(self.grid)
        main_layout.addStretch(1)
        main_layout.addLayout(bottom_bar)

        self.show_page()

    # ---------- Page Management ----------
    def show_page(self):
        # Clear grid
        for i in reversed(range(self.grid.count())):
            w = self.grid.itemAt(i).widget()
            if w:
                w.setParent(None)

        start = self.page * self.apps_per_page
        end = start + self.apps_per_page
        page_items = self.apps[start:end]

        for idx, cfg in enumerate(page_items):
            row, col = divmod(idx, 3)
            btn = QPushButton(cfg["name"])
            btn.setFixedSize(200, 100)
            btn.setStyleSheet("font-size: 18px; text-align: center; border-radius: 10px; background-color: #333; color: white;")
            icon_path = cfg.get("touch_icon")
            if icon_path and os.path.exists(icon_path):
                btn.setIcon(QIcon(QPixmap(icon_path).scaled(64, 64, Qt.AspectRatioMode.KeepAspectRatio)))
                btn.setIconSize(QPixmap(icon_path).scaled(64, 64, Qt.AspectRatioMode.KeepAspectRatio).size())
            btn.clicked.connect(lambda _, c=cfg: self.launch_app(c))
            self.grid.addWidget(btn, row, col, alignment=Qt.AlignmentFlag.AlignCenter)

        total_pages = max(1, (len(self.apps) - 1) // self.apps_per_page + 1)
        self.page_label.setText(f"Page {self.page + 1} / {total_pages}")

    def next_page(self):
        total_pages = max(1, (len(self.apps) - 1) // self.apps_per_page + 1)
        self.page = (self.page + 1) % total_pages
        self.show_page()

    def prev_page(self):
        total_pages = max(1, (len(self.apps) - 1) // self.apps_per_page + 1)
        self.page = (self.page - 1) % total_pages
        self.show_page()

    # ---------- Launch / Close ----------
    def launch_app(self, cfg):
        print(f"Launching {cfg['name']}")
        cmd = cfg["cmd"]
        try:
            subprocess.Popen(cmd if isinstance(cmd, str) else " ".join(cmd), shell=True)
        except Exception as e:
            print("Error launching:", e)

    def stop_launcher(self):
        QApplication.quit()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    launcher = OverlayLauncher(apps, 1024, 800)
    launcher.show()
    sys.exit(app.exec())
