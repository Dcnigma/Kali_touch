import sys
import subprocess
import json
import importlib
import psutil
from PyQt6.QtWidgets import (
    QApplication, QWidget, QPushButton, QGridLayout, QLabel,
    QHBoxLayout, QVBoxLayout, QMessageBox
)
from PyQt6.QtCore import Qt, QTimer

CONFIG_FILE = "apps.json"


def load_apps():
    try:
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return {"Text Editor": {"cmd": "mousepad"}}


class FloatingButton(QWidget):
    def __init__(self, text, callback, position):
        super().__init__()
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(160, 80)
        self._drag_position = None

        self.button = QPushButton(text, self)
        self.button.setStyleSheet("font-size: 20px; background-color: red; color: white;")
        self.button.clicked.connect(callback)
        self.button.resize(160, 80)
        self.move(*position)
        self.hide()

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
        self.apps_dict = apps
        self.apps = list(apps.items())
        self.current_process = None
        self.current_plugin = None
        self.page = 0
        self.apps_per_page = 9

        # Overlay background
        self.overlay = QWidget(self)
        self.overlay.setStyleSheet("background-color: black;")
        self.overlay.setGeometry(0, 0, screen_width, screen_height)
        self.overlay.hide()

        # Main layout
        main_layout = QVBoxLayout()
        main_layout.setSpacing(20)
        main_layout.setContentsMargins(50, 50, 50, 50)
        self.setLayout(main_layout)

        # App grid
        self.grid = QGridLayout()
        self.grid.setSpacing(20)
        main_layout.addLayout(self.grid)
        main_layout.addStretch(1)

        # Bottom navigation bar
        bottom_layout = QHBoxLayout()
        bottom_layout.setSpacing(50)

        # Stop Launcher button (bottom-left)
        self.stop_btn = QPushButton("Stop Launcher")
        self.stop_btn.setFixedSize(200, 80)
        self.stop_btn.setStyleSheet("font-size: 20px; background-color: gray; color: white;")
        self.stop_btn.clicked.connect(self.stop_launcher)
        bottom_layout.addWidget(self.stop_btn, alignment=Qt.AlignmentFlag.AlignLeft)

        # Page label (center)
        self.page_label = QLabel()
        self.page_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.page_label.setStyleSheet("font-size: 24px; color: white;")
        bottom_layout.addWidget(self.page_label, alignment=Qt.AlignmentFlag.AlignCenter)

        # Navigation (bottom-right)
        nav_layout = QHBoxLayout()
        self.prev_btn = QPushButton("← Prev")
        self.prev_btn.setFixedSize(120, 80)
        self.prev_btn.setStyleSheet("font-size: 20px;")
        self.prev_btn.clicked.connect(self.prev_page)
        nav_layout.addWidget(self.prev_btn)

        self.next_btn = QPushButton("Next →")
        self.next_btn.setFixedSize(120, 80)
        self.next_btn.setStyleSheet("font-size: 20px;")
        self.next_btn.clicked.connect(self.next_page)
        nav_layout.addWidget(self.next_btn)
        bottom_layout.addLayout(nav_layout)

        main_layout.addLayout(bottom_layout)

        # Floating Close button
        self.close_btn = FloatingButton("Close App", self.close_app, position=(20, 20))

        self.show_page()

    def show_page(self):
        for i in reversed(range(self.grid.count())):
            widget = self.grid.itemAt(i).widget()
            if widget:
                widget.setParent(None)

        start = self.page * self.apps_per_page
        end = start + self.apps_per_page
        page_apps = self.apps[start:end]

        for idx, (name, app_config) in enumerate(page_apps):
            row, col = divmod(idx, 3)
            btn = QPushButton(name)
            btn.setFixedSize(200, 100)
            btn.setStyleSheet("font-size: 20px;")
            btn.clicked.connect(lambda _, cfg=app_config: self.launch_item(cfg))
            self.grid.addWidget(btn, row, col)

        total_pages = (len(self.apps) - 1) // self.apps_per_page + 1
        self.page_label.setText(f"Page {self.page + 1} / {total_pages}")

    def launch_item(self, app_config):
        if "plugin" in app_config:
            self.launch_plugin(app_config["plugin"])
        elif "cmd" in app_config:
            self.launch_app(app_config)
        else:
            QMessageBox.warning(self, "Error", "Invalid app entry!")

    def launch_plugin(self, plugin_path):
        try:
            module_name, class_name = [s.strip() for s in plugin_path.split(":")]
            module = importlib.import_module(module_name)
            plugin_class = getattr(module, class_name)
            self.current_plugin = plugin_class(parent=self, apps=self.apps_dict)
            self.current_plugin.show()
            self.overlay.show()
            self.close_btn.show()
        except Exception as e:
            QMessageBox.critical(self, "Plugin Error", f"Failed to load plugin:\n{e}")
            print("Plugin load error:", e)

    def launch_app(self, app_config):
        if self.current_process:
            self.close_app()

        cmd = app_config["cmd"].lower()
        self.current_process = subprocess.Popen(cmd, shell=True)
        self.overlay.show()
        self.close_btn.show()

        # Position window
        x = app_config.get("x", 100)
        y = app_config.get("y", 100)
        w = app_config.get("width", 800)
        h = app_config.get("height", 600)
        QTimer.singleShot(2000, lambda: self.position_window(self.current_process.pid, x, y, w, h))

    def position_window(self, pid, x, y, width, height):
        subprocess.run(f"xdotool search --pid {pid} windowmove {x} {y}", shell=True)
        subprocess.run(f"xdotool search --pid {pid} windowsize {width} {height}", shell=True)

    def close_app(self):
        self.overlay.hide()
        self.close_btn.hide()

        if self.current_process:
            try:
                parent = psutil.Process(self.current_process.pid)
                for child in parent.children(recursive=True):
                    child.kill()
                parent.kill()
            except Exception:
                pass

            # Fallback for stubborn apps (like Firefox)
            try:
                if "firefox" in self.current_process.args[0]:
                    subprocess.run("pkill -f firefox", shell=True)
            except Exception:
                pass

            self.current_process = None

        if self.current_plugin:
            try:
                self.current_plugin.close()
            except Exception:
                pass
            self.current_plugin = None

    def stop_launcher(self):
        QApplication.quit()

    def next_page(self):
        total = (len(self.apps) - 1) // self.apps_per_page + 1
        self.page = (self.page + 1) % total
        self.show_page()

    def prev_page(self):
        total = (len(self.apps) - 1) // self.apps_per_page + 1
        self.page = (self.page - 1) % total
        self.show_page()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    launcher = OverlayLauncher(load_apps(), screen_width=1024, screen_height=800)
    launcher.show()
    sys.exit(app.exec())
