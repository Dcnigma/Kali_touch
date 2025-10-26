#!/usr/bin/env python3
import sys
import os
import json
import subprocess
import importlib
import signal
import psutil
import shutil
import traceback
from PyQt6.QtWidgets import (
    QApplication, QWidget, QPushButton, QGridLayout, QLabel,
    QHBoxLayout, QVBoxLayout, QSpacerItem, QSizePolicy, QMessageBox
)
from PyQt6.QtCore import Qt, QTimer, QPropertyAnimation
from PyQt6.QtGui import QPixmap, QIcon

CONFIG_FILE = "apps.json"
SCREEN_W, SCREEN_H = 1024, 800
DEBUG = True


def log(*args):
    if DEBUG:
        print(*args)


# ---------- Load apps ----------
try:
    with open(CONFIG_FILE, "r") as f:
        raw_apps = json.load(f)
except Exception as e:
    print(f"[ERROR] Could not load {CONFIG_FILE}: {e}")
    raw_apps = {}

apps_dict = dict(raw_apps)
apps = []
for name, cfg in raw_apps.items():
    cfg = dict(cfg)
    cfg["name"] = name
    apps.append(cfg)


# ---------- Plugin Loader ----------
def load_plugin(app_name, app_data, parent=None):
    try:
        plugin_path = app_data.get("plugin")
        if not plugin_path:
            log(f"[PLUGIN] ⚠ No plugin path for '{app_name}'")
            return None

        module_name, class_name = plugin_path.split(":")
        module = importlib.import_module(module_name.strip())
        cls = getattr(module, class_name.strip())

        try:
            plugin_widget = cls(parent=None, apps=apps_dict, cfg=app_data)
        except TypeError:
            plugin_widget = cls(parent=None)
            setattr(plugin_widget, "cfg", app_data)

        plugin_widget.setWindowFlags(Qt.WindowType.Tool)
        if hasattr(plugin_widget, "on_start"):
            try:
                plugin_widget.on_start()
            except Exception as e:
                log(f"[PLUGIN] on_start error: {e}")

        return plugin_widget
    except Exception as e:
        print(f"[PLUGIN] ❌ Failed to load '{app_name}': {e}")
        traceback.print_exc()
        msg = QMessageBox()
        msg.setIcon(QMessageBox.Icon.Warning)
        msg.setWindowTitle("Plugin Load Error")
        msg.setText(f"Failed to load plugin '{app_name}'\n\nError:\n{e}")
        msg.exec()
        return None


# ---------- Floating Close Button ----------
class FloatingCloseButton(QPushButton):
    def __init__(self, callback):
        super().__init__("✕")
        self.setFixedSize(72, 72)
        self.setStyleSheet("""
            QPushButton {
                font-size: 28px;
                background-color: rgba(0,0,0,160);
                color: white;
                border-radius: 36px;
                border: 2px solid rgba(255,255,255,160);
            }
            QPushButton:hover { background-color: rgba(200,0,0,200); }
        """)
        self.clicked.connect(callback)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )


# ---------- Main Launcher ----------
class OverlayLauncher(QWidget):
    def __init__(self, apps):
        super().__init__()
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setFixedSize(SCREEN_W, SCREEN_H)

        self.apps = apps
        self.page = 0
        self.apps_per_page = 9
        self.current_process = None
        self.current_plugin = None

        # Overlay background
        self.overlay = QWidget(self)
        self.overlay.setGeometry(0, 0, SCREEN_W, SCREEN_H)
        self.overlay.setStyleSheet("background-color: rgba(0,0,0,200);")
        self.overlay.hide()

        self.overlay_anim = QPropertyAnimation(self.overlay, b"windowOpacity", self)

        # UI container
        self.ui_container = QWidget(self)
        self.ui_container.setGeometry(0, 0, SCREEN_W, SCREEN_H)
        ui_layout = QVBoxLayout(self.ui_container)
        ui_layout.setSpacing(10)
        ui_layout.setContentsMargins(36, 20, 36, 18)

        # App grid
        self.grid = QGridLayout()
        self.grid.setSpacing(12)
        ui_layout.addLayout(self.grid)

        ui_layout.addItem(QSpacerItem(0, 0, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding))

        # ---------- Bottom bar ----------
        bottom_bar = QHBoxLayout()
        bottom_bar.setContentsMargins(8, 0, 8, 8)

        # Stop Launcher button (bottom-left)
        self.stop_btn = QPushButton("Stop Launcher")
        self.stop_btn.setFixedSize(180, 64)
        self.stop_btn.setStyleSheet("font-size:18px; background-color:#5a5a5a; color:white; border-radius:8px;")
        self.stop_btn.clicked.connect(self.stop_launcher)
        bottom_bar.addWidget(self.stop_btn, alignment=Qt.AlignmentFlag.AlignLeft)

        bottom_bar.addStretch(1)

        # Page label center (optional)
        self.page_label = QLabel()
        self.page_label.setStyleSheet("font-size:18px; color:white;")
        bottom_bar.addWidget(self.page_label, alignment=Qt.AlignmentFlag.AlignCenter)

        bottom_bar.addStretch(1)

        # Prev / Next on bottom-right
        nav_style = "font-size:18px; background-color:#444; color:white; border-radius:8px; padding:8px 16px;"
        self.prev_btn = QPushButton("← Prev")
        self.prev_btn.setFixedSize(120, 64)
        self.prev_btn.setStyleSheet(nav_style)
        self.prev_btn.clicked.connect(self.prev_page)

        self.next_btn = QPushButton("Next →")
        self.next_btn.setFixedSize(120, 64)
        self.next_btn.setStyleSheet(nav_style)
        self.next_btn.clicked.connect(self.next_page)

        bottom_bar.addWidget(self.prev_btn)
        bottom_bar.addWidget(self.next_btn)

        ui_layout.addLayout(bottom_bar)

        # Floating close button
        self.close_btn = FloatingCloseButton(self.close_current)
        self.close_btn.setParent(self)
        self.close_btn.move(SCREEN_W - 90, SCREEN_H - 90)
        self.close_btn.hide()

        self.raise_timer = QTimer(self)
        self.raise_timer.timeout.connect(self._raise_close_btn)

        self.show_page()

    # ---------- Page Navigation ----------
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
                btn.clicked.connect(lambda _, c=cfg: self._start_plugin_safe(c))
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

    # ---------- Launch App ----------
    def launch_app(self, cfg):
        self.close_current()
        self.ui_container.hide()

        cmd = cfg["cmd"]
        self.last_launch_cfg = cfg

        self.overlay.setWindowOpacity(0.0)
        self.overlay.show()
        self.overlay.raise_()
        self.overlay_anim.stop()
        self.overlay_anim.setDuration(300)
        self.overlay_anim.setStartValue(0.0)
        self.overlay_anim.setEndValue(0.9)
        self.overlay_anim.start()

        try:
            cmd_str = cmd if isinstance(cmd, str) else " ".join(cmd)
            proc = subprocess.Popen(cmd_str, shell=True, preexec_fn=os.setsid)
            self.current_process = proc
            log(f"Launched PID {proc.pid}: {cmd_str}")
        except Exception as e:
            QMessageBox.warning(self, "Launch failed", str(e))
            self.overlay.hide()
            self.ui_container.show()
            return

        QTimer.singleShot(700, lambda: self._focus_launched_process(proc.pid, cfg))
        QTimer.singleShot(1000, self._show_close_after_launch)

    def _show_close_after_launch(self):
        self.overlay.hide()
        self.close_btn.show()
        self.raise_timer.start(100)

    # ---------- Plugin Launch ----------
    def _start_plugin_safe(self, cfg):
        widget = load_plugin(cfg.get("name", "Unknown"), cfg, parent=self)
        if widget:
            self.launch_plugin(widget)
        else:
            self.ui_container.show()

    def launch_plugin(self, widget):
        w, h = 900, 700
        x, y = (SCREEN_W - w) // 2, (SCREEN_H - h) // 2
        widget.setGeometry(x, y, w, h)
        widget.show()
        widget.raise_()
        widget.activateWindow()
        self.overlay.hide()
        self.close_btn.show()
        self.raise_timer.start(100)
        self.current_plugin = widget

    def _focus_launched_process(self, pid, cfg):
        if shutil.which("xdotool"):
            try:
                subprocess.run(f"xdotool search --pid {pid} windowactivate", shell=True)
            except Exception:
                pass
        if shutil.which("wmctrl"):
            try:
                subprocess.run("wmctrl -a " + cfg.get("name", ""), shell=True)
            except Exception:
                pass

    # ---------- Close / Stop ----------
    def close_current(self):
        if self.current_plugin:
            try:
                self.current_plugin.close()
            except Exception:
                pass
            self.current_plugin = None

        if self.current_process:
            try:
                os.killpg(os.getpgid(self.current_process.pid), signal.SIGTERM)
            except Exception:
                pass
            self.current_process = None

        self.overlay.hide()
        self.ui_container.show()
        self.close_btn.hide()

    def _raise_close_btn(self):
        if self.close_btn.isVisible():
            self.close_btn.raise_()
        else:
            self.raise_timer.stop()

    def stop_launcher(self):
        self.close_current()
        QApplication.quit()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    launcher = OverlayLauncher(apps)
    launcher.show()
    sys.exit(app.exec())
