#!/usr/bin/env python3
import sys
import os
import grp
import json
import subprocess
import signal
import time
import psutil
from PyQt6.QtWidgets import (
    QApplication, QWidget, QPushButton, QGridLayout, QLabel,
    QHBoxLayout, QVBoxLayout, QSpacerItem, QSizePolicy
)
from PyQt6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve
from PyQt6.QtGui import QPixmap, QIcon

CONFIG_FILE = "apps.json"
SCREEN_W, SCREEN_H = 1024, 800

# Ensure current process has access to gpio and spi
def add_hardware_groups():
    try:
        # get GIDs for groups
        gpio_gid = grp.getgrnam('gpio').gr_gid
        spi_gid = grp.getgrnam('spi').gr_gid
        os.setgroups([gpio_gid, spi_gid])
    except Exception as e:
        print("Warning: Could not add gpio/spi groups:", e)

add_hardware_groups()

# Load apps from JSON
with open(CONFIG_FILE, "r") as f:
    apps = json.load(f)  # apps is now a list of dicts

class FloatingCloseButton(QPushButton):
    def __init__(self, callback, screen_w=SCREEN_W, margin=20):
        super().__init__("✕")
        size = 48  # slightly smaller
        self.setFixedSize(size, size)
        self.setStyleSheet(f"""
            QPushButton {{
                font-size: 24px;
                background-color: rgba(0,0,0,100);  /* more subtle */
                color: white;
                border-radius: {size//2}px;
                border: 1px solid rgba(255,255,255,120);
            }}
            QPushButton:hover {{
                background-color: rgba(255,0,0,180);  /* subtle red on hover */
            }}
        """)
        self.clicked.connect(callback)
        self._screen_w = screen_w
        self._margin = margin

        # Optional: fade animation
        self.anim = QPropertyAnimation(self, b"windowOpacity")
        self.setWindowOpacity(0.6)  # default slightly transparent

    def enterEvent(self, event):
        self.anim.stop()
        self.anim.setDuration(200)
        self.anim.setStartValue(self.windowOpacity())
        self.anim.setEndValue(1.0)  # fully visible on hover
        self.anim.start()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.anim.stop()
        self.anim.setDuration(300)
        self.anim.setStartValue(self.windowOpacity())
        self.anim.setEndValue(0.6)  # back to subtle
        self.anim.start()
        super().leaveEvent(event)

    def set_parent_parent(self, parent_widget):
        self.setParent(parent_widget)
        x = self._screen_w - self.width() - self._margin
        y = self._margin
        self.move(x, y)

class OverlayLauncher(QWidget):
    def __init__(self, apps, screen_width=SCREEN_W, screen_height=SCREEN_H):
        super().__init__()
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setFixedSize(screen_width, screen_height)

        self.screen_width = screen_width
        self.screen_height = screen_height

        self.apps = apps
        self.page = 0
        self.apps_per_page = 9
        self.current_process = None
        self.current_plugin = None

        # Overlay
        self.overlay = QWidget(self)
        self.overlay.setGeometry(0, 0, screen_width, screen_height)
        self.overlay.setStyleSheet("background-color: rgba(0,0,0,230);")
        self.overlay.hide()
        self.overlay_anim = QPropertyAnimation(self.overlay, b"windowOpacity", self)

        # UI container
        self.ui_container = QWidget(self)
        self.ui_container.setGeometry(0, 0, screen_width, screen_height)
        ui_layout = QVBoxLayout(self.ui_container)
        ui_layout.setSpacing(10)
        ui_layout.setContentsMargins(36, 20, 36, 18)

        # Grid container
        grid_container = QWidget()
        grid_layout = QGridLayout(grid_container)
        grid_layout.setSpacing(12)
        grid_layout.setContentsMargins(0, 0, 0, 0)
        self.grid = grid_layout
        grid_container.setFixedHeight(3 * 116 + 2 * 12)
        ui_layout.addWidget(grid_container, alignment=Qt.AlignmentFlag.AlignTop)

        # Spacer to push bottom bar to bottom
        ui_layout.addStretch(1)

        # Bottom bar
        bottom_bar = QHBoxLayout()
        bottom_bar.setContentsMargins(8, 0, 8, 8)

        self.stop_btn = QPushButton("Stop Launcher")
        self.stop_btn.setFixedSize(180, 64)
        self.stop_btn.setStyleSheet("font-size:18px; background-color: #5a5a5a; color: white; border-radius: 8px;")
        self.stop_btn.clicked.connect(self.stop_launcher)
        bottom_bar.addWidget(self.stop_btn, alignment=Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom)

        bottom_bar.addStretch(1)

        self.page_label = QLabel()
        self.page_label.setStyleSheet("font-size:18px; color: white;")
        bottom_bar.addWidget(self.page_label, alignment=Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)

        bottom_bar.addStretch(1)

        nav_btn_style = ("font-size:18px; background-color: #444; color:white; "
                         "border-radius:8px; padding:8px 16px;")
        self.prev_btn = QPushButton("← Prev")
        self.prev_btn.setFixedSize(120, 64)
        self.prev_btn.setStyleSheet(nav_btn_style)
        self.prev_btn.clicked.connect(self.prev_page)

        self.next_btn = QPushButton("Next →")
        self.next_btn.setFixedSize(120, 64)
        self.next_btn.setStyleSheet(nav_btn_style)
        self.next_btn.clicked.connect(self.next_page)

        bottom_bar.addWidget(self.prev_btn, alignment=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignBottom)
        bottom_bar.addWidget(self.next_btn, alignment=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignBottom)

        ui_layout.addLayout(bottom_bar)

        # Close button
        self.close_btn = FloatingCloseButton(self.close_current, screen_w=screen_width, margin=16)
        self.close_btn.set_parent_parent(self)
        self.close_btn.hide()

        self.raise_timer = QTimer(self)
        self.raise_timer.timeout.connect(self._raise_close_btn)

        self.show_page()

    # ---------- pages / grid ----------
    def show_page(self):
        for i in reversed(range(self.grid.count())):
            w = self.grid.itemAt(i).widget()
            if w:
                w.setParent(None)

        start = self.page * self.apps_per_page
        end = start + self.apps_per_page
        page_items = self.apps[start:end]

        for idx, cfg in enumerate(page_items):
            row, col = divmod(idx, 3)
            name = cfg.get("name", "App")
            btn = QPushButton(name)
            btn.setFixedSize(220, 116)
            btn.setStyleSheet("font-size:20px; background-color:#2f2f2f; color:white; border-radius:10px;")
            icon_path = cfg.get("touch_icon")
            if icon_path and os.path.exists(icon_path):
                pix = QPixmap(icon_path).scaled(64, 64, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                btn.setIcon(QIcon(pix))
                btn.setIconSize(pix.size())
            if "cmd" in cfg:
                btn.clicked.connect(lambda _, c=cfg: self.launch_app(c))
            elif "plugin" in cfg:
                btn.clicked.connect(lambda _, c=cfg: self.launch_plugin(c["plugin"], c))
            self.grid.addWidget(btn, row, col, alignment=Qt.AlignmentFlag.AlignCenter)

        total_pages = max(1, (len(self.apps) - 1) // self.apps_per_page + 1)
        self.page_label.setText(f"Page {self.page + 1} / {total_pages}")

    def next_page(self):
        total = max(1, (len(self.apps) - 1) // self.apps_per_page + 1)
        self.page = (self.page + 1) % total
        self.show_page()

    def prev_page(self):
        total = max(1, (len(self.apps) - 1) // self.apps_per_page + 1)
        self.page = (self.page - 1) % total
        self.show_page()

    # ---------- launch handling ----------
    def launch_app(self, cfg):
        pass  # Copy your existing launch_app implementation here

    def launch_plugin(self, plugin_path, cfg):
        pass  # Copy your existing launch_plugin implementation here

    # ---------- close / cleanup ----------
    def close_current(self):
        pass  # Copy your existing close_current implementation here

    def _raise_close_btn(self):
        if self.close_btn.isVisible():
            self.close_btn.raise_()
            self.close_btn.activateWindow()
        else:
            self.raise_timer.stop()

    def stop_launcher(self):
        self.close_current()
        QApplication.quit()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    launcher = OverlayLauncher(apps, screen_width=SCREEN_W, screen_height=SCREEN_H)
    launcher.show()
    sys.exit(app.exec())
