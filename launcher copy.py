#!/usr/bin/env python3
import sys, os, json, subprocess
from PyQt6.QtWidgets import (
    QApplication, QWidget, QPushButton, QGridLayout, QLabel,
    QHBoxLayout, QVBoxLayout
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QPixmap, QIcon

import psutil  # NEW: to terminate apps properly

CONFIG_FILE = "apps.json"

# Load apps from JSON
with open(CONFIG_FILE, "r") as f:
    raw_apps = json.load(f)

# Convert to list so duplicates are kept
apps = []
for name, cfg in raw_apps.items():
    cfg["name"] = name
    apps.append(cfg)


class FloatingButton(QPushButton):
    """Always-on-top draggable button"""
    def __init__(self, text, callback, position):
        super().__init__(text)
        self.setStyleSheet(
            "font-size: 20px; background-color: rgba(255,0,0,200); color: white; border-radius: 10px;"
        )
        self.setFixedSize(80, 40)
        self.clicked.connect(callback)
        self._drag_position = None
        self.move(*position)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.show()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.MouseButton.LeftButton and self._drag_position:
            self.move(event.globalPosition().toPoint() - self._drag_position)
            event.accept()

    def mouseReleaseEvent(self, event):
        self._drag_position = None
        event.accept()


class OverlayLauncher(QWidget):
    def __init__(self, apps, screen_width=1024, screen_height=800):
        super().__init__()
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.showFullScreen()

        self.screen_width = screen_width
        self.screen_height = screen_height
        self.apps = apps
        self.apps_per_page = 9
        self.page = 0
        self.current_process = None
        self.current_plugin = None

        # Overlay behind plugin/app
        self.overlay = QWidget(self)
        self.overlay.setStyleSheet("background-color: rgba(0,0,0,200);")
        self.overlay.setGeometry(0, 0, self.screen_width, self.screen_height)
        self.overlay.hide()

        # Close button for apps/plugins
        self.app_close_btn = FloatingButton("X", self.close_current, position=(self.screen_width-100, 20))
        self.app_close_btn.hide()

        # Timer to keep button on top
        self.raise_timer = QTimer()
        self.raise_timer.timeout.connect(self.raise_close_button)

        # Main layout
        main_layout = QVBoxLayout()
        main_layout.setSpacing(20)
        main_layout.setContentsMargins(50, 50, 50, 50)
        self.setLayout(main_layout)

        # Grid for app/plugin buttons
        self.grid = QGridLayout()
        self.grid.setSpacing(20)
        main_layout.addLayout(self.grid)

        # Bottom bar: Stop Launcher | Page | Navigation
        bottom_layout = QHBoxLayout()
        bottom_layout.setSpacing(50)

        # Stop
        self.stop_btn = QPushButton("Stop Launcher")
        self.stop_btn.setFixedSize(200, 80)
        self.stop_btn.setStyleSheet("font-size: 20px; background-color: gray; color: white;")
        self.stop_btn.clicked.connect(self.stop_launcher)
        bottom_layout.addWidget(self.stop_btn, alignment=Qt.AlignmentFlag.AlignLeft)

        # Page label
        self.page_label = QLabel()
        self.page_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.page_label.setStyleSheet("font-size: 24px; color: white;")
        bottom_layout.addWidget(self.page_label, alignment=Qt.AlignmentFlag.AlignCenter)

        # Navigation buttons
        nav_layout = QHBoxLayout()
        self.prev_btn = QPushButton("â† Prev")
        self.prev_btn.setFixedSize(120, 80)
        self.prev_btn.setStyleSheet("font-size: 20px;")
        self.prev_btn.clicked.connect(self.prev_page)
        nav_layout.addWidget(self.prev_btn)

        self.next_btn = QPushButton("Next â†’")
        self.next_btn.setFixedSize(120, 80)
        self.next_btn.setStyleSheet("font-size: 20px;")
        self.next_btn.clicked.connect(self.next_page)
        nav_layout.addWidget(self.next_btn)

        bottom_layout.addLayout(nav_layout)
        main_layout.addLayout(bottom_layout)

        self.show_page()

    # ----------------- Grid & pages -----------------
    def show_page(self):
        for i in reversed(range(self.grid.count())):
            widget = self.grid.itemAt(i).widget()
            if widget:
                widget.setParent(None)

        start = self.page * self.apps_per_page
        end = start + self.apps_per_page
        page_items = self.apps[start:end]

        for idx, cfg in enumerate(page_items):
            row, col = divmod(idx, 3)
            btn = QPushButton(cfg["name"])
            btn.setFixedSize(200, 100)
            btn.setStyleSheet("font-size: 18px; text-align:center;")

            # Add touch icon if available
            icon_path = cfg.get("touch_icon")
            if icon_path and os.path.exists(icon_path):
                pix = QPixmap(icon_path).scaled(64, 64, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                btn.setIcon(QIcon(pix))
                btn.setIconSize(pix.size())

            # Connect launch
            if "cmd" in cfg:
                btn.clicked.connect(lambda _, c=cfg: self.launch_app(c))
            elif "plugin" in cfg:
                btn.clicked.connect(lambda _, c=cfg: self.launch_plugin(c["plugin"], c))

            self.grid.addWidget(btn, row, col)

        total_pages = (len(self.apps) - 1) // self.apps_per_page + 1
        self.page_label.setText(f"Page {self.page + 1} / {total_pages}")

    def next_page(self):
        total_pages = (len(self.apps) - 1) // self.apps_per_page + 1
        self.page = (self.page + 1) % total_pages
        self.show_page()

    def prev_page(self):
        total_pages = (len(self.apps) - 1) // self.apps_per_page + 1
        self.page = (self.page - 1) % total_pages
        self.show_page()

    # ----------------- Launch apps/plugins -----------------
    def launch_app(self, cfg):
        self.close_current()

        cmd = cfg["cmd"]
        try:
            self.current_process = subprocess.Popen(cmd, shell=True)
        except FileNotFoundError:
            print(f"Executable not found: {cmd}")
            self.current_process = None
            return

        self.overlay.show()
        self.overlay.raise_()
        self.app_close_btn.show()
        self.app_close_btn.raise_()
        self.raise_timer.start(100)

    def launch_plugin(self, plugin_path, cfg):
        self.close_current()

        # Import plugin
        module_name, class_name = plugin_path.split(":")
        module = __import__(module_name.strip(), fromlist=[class_name.strip()])
        cls = getattr(module, class_name.strip())

        # Instantiate plugin
        plugin_widget = cls()
        plugin_widget.setWindowFlags(Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.FramelessWindowHint)

        # Geometry
        w = int(cfg.get("width", 900))
        h = int(cfg.get("height", 700))
        x = int(cfg.get("x", (self.screen_width-w)//2))
        y = int(cfg.get("y", (self.screen_height-h)//2))
        plugin_widget.setGeometry(x, y, w, h)

        self.overlay.hide()
        plugin_widget.show()
        plugin_widget.raise_()
        self.app_close_btn.raise_()
        self.overlay.show()

        self.current_plugin = plugin_widget

    # ----------------- Close apps/plugins -----------------
    def close_current(self):
        # Close plugin
        if self.current_plugin:
            try:
                self.current_plugin.close()
            except Exception:
                pass
            self.current_plugin = None

        # Close app
        if self.current_process:
            try:
                parent = psutil.Process(self.current_process.pid)
                for child in parent.children(recursive=True):
                    child.terminate()
                parent.terminate()
            except Exception:
                pass
            self.current_process = None

        self.overlay.hide()
        self.app_close_btn.hide()
        self.raise_timer.stop()

    def raise_close_button(self):
        if self.app_close_btn.isVisible():
            self.app_close_btn.raise_()
            self.app_close_btn.activateWindow()
        else:
            self.raise_timer.stop()

    def stop_launcher(self):
        QApplication.quit()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    launcher = OverlayLauncher(apps, screen_width=1024, screen_height=800)
    launcher.show()
    sys.exit(app.exec())
