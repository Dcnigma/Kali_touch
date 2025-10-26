#!/usr/bin/env python3
import sys
import os
import json
import subprocess
import importlib
import signal
import time
import psutil
import shutil
import traceback
from PyQt6.QtWidgets import (
    QApplication, QWidget, QPushButton, QGridLayout, QLabel,
    QHBoxLayout, QVBoxLayout, QSpacerItem, QSizePolicy, QMessageBox
)
from PyQt6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve
from PyQt6.QtGui import QPixmap, QIcon

CONFIG_FILE = "apps.json"
SCREEN_W, SCREEN_H = 1024, 800
DEBUG = True


def log(*args, **kwargs):
    if DEBUG:
        print(*args, **kwargs)


# Load apps safely
try:
    with open(CONFIG_FILE, "r") as f:
        raw_apps = json.load(f)
except Exception as e:
    print(f"[ERROR] Could not load {CONFIG_FILE}: {e}")
    raw_apps = {}

# Keep both dict and ordered list
apps_dict = dict(raw_apps)
apps = []
for name, cfg in raw_apps.items():
    cfg = dict(cfg)
    cfg["name"] = name
    apps.append(cfg)


# ---------------- Safe plugin loader ---------------- #
def load_plugin(app_name, app_data, parent=None):
    """Safely load plugin widgets from JSON entries."""
    try:
        plugin_path = app_data.get("plugin")
        if not plugin_path:
            log(f"[PLUGIN] ⚠ No plugin path for '{app_name}'")
            return None

        module_name, class_name = plugin_path.split(":")
        module = importlib.import_module(module_name.strip())
        cls = getattr(module, class_name.strip())
        plugin_widget = cls(parent=None, apps=apps_dict, cfg=app_data)
        plugin_widget.setWindowFlags(plugin_widget.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
        plugin_widget.show()
        plugin_widget.raise_()
        plugin_widget.activateWindow()
        if hasattr(plugin_widget, "on_start"):
            try:
                plugin_widget.on_start()
            except Exception as e:
                log(f"[PLUGIN] on_start() error in {app_name}: {e}")

        log(f"[PLUGIN] ✅ Loaded '{app_name}' ({plugin_path})")
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


class FloatingCloseButton(QPushButton):
    """Fixed top-right always-on-top close button."""
    def __init__(self, callback, screen_w=SCREEN_W, margin=20):
        super().__init__("✕")
        size = 72
        self.setFixedSize(size, size)
        self.setStyleSheet(f"""
            QPushButton {{
                font-size: 28px;
                background-color: rgba(0,0,0,160);
                color: white;
                border-radius: {size//2}px;
                border: 2px solid rgba(255,255,255,160);
            }}
            QPushButton:hover {{ background-color: rgba(200,0,0,200); }}
        """)
        self.clicked.connect(callback)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self._screen_w = screen_w
        self._margin = margin

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
#        self.overlay.hide()
        self.overlay_anim = QPropertyAnimation(self.overlay, b"windowOpacity", self)

        # Main UI
        self.ui_container = QWidget(self)
        self.ui_container.setGeometry(0, 0, screen_width, screen_height)
        ui_layout = QVBoxLayout(self.ui_container)
        ui_layout.setSpacing(10)
        ui_layout.setContentsMargins(36, 20, 36, 18)

        self.grid = QGridLayout()
        self.grid.setSpacing(12)
        ui_layout.addLayout(self.grid)

        ui_layout.addItem(QSpacerItem(0, 0, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding))

        # Bottom bar
        bottom_bar = QHBoxLayout()
        bottom_bar.setContentsMargins(8, 0, 8, 8)

        self.stop_btn = QPushButton("Stop Launcher")
        self.stop_btn.setFixedSize(180, 64)
        self.stop_btn.setStyleSheet("font-size:18px; background-color:#5a5a5a; color:white; border-radius:8px;")
        self.stop_btn.clicked.connect(self.stop_launcher)
        bottom_bar.addWidget(self.stop_btn, alignment=Qt.AlignmentFlag.AlignLeft)

        bottom_bar.addStretch(1)
        self.page_label = QLabel()
        self.page_label.setStyleSheet("font-size:18px; color:white;")
        bottom_bar.addWidget(self.page_label, alignment=Qt.AlignmentFlag.AlignCenter)
        bottom_bar.addStretch(1)

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

        # Close Button
        self.close_btn = FloatingCloseButton(self.close_current, screen_w=screen_width, margin=16)
        self.close_btn.set_parent_parent(self)
        self.close_btn.hide()

        self.raise_timer = QTimer(self)
        self.raise_timer.timeout.connect(self._raise_close_btn)

        self.show_page()

    # ---------------- PAGE SYSTEM ---------------- #
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

    # ---------------- LAUNCH APPS ---------------- #
    def launch_app(self, cfg):
        self.close_current()
        cmd = cfg["cmd"]
        self.ui_container.hide()

        self.overlay.setWindowOpacity(0.0)
        self.overlay.show()
        self.overlay.raise_()
        self.overlay_anim.stop()
        self.overlay_anim.setDuration(360)
        self.overlay_anim.setStartValue(0.0)
        self.overlay_anim.setEndValue(0.88)
        self.overlay_anim.setEasingCurve(QEasingCurve.Type.InOutQuad)
        self.overlay_anim.start()

        try:
            cmd_str = cmd if isinstance(cmd, str) else " ".join(cmd)
            primary = cmd_str.split()[0]
            if shutil.which(primary) is None:
                lower_primary = primary.lower()
                if shutil.which(lower_primary):
                    rest = " ".join(cmd_str.split()[1:])
                    cmd_str = f"{lower_primary} {rest}".strip()
                    log(f"Auto-corrected command → {cmd_str}")
            proc = subprocess.Popen(cmd, shell=True, preexec_fn=os.setsid)
            # Give the app a moment, then focus it (if supported)
#            QTimer.singleShot(700, lambda: self.raise_())
            self.current_process = proc
            self.hide()  # hide launcher overlay
            QTimer.singleShot(1000, self.show)  # reopen after 1s, optional            
            log(f"Launched PID {proc.pid}: {cmd_str}")
        except Exception as e:
#            self.overlay.hide()
            self.ui_container.show()
            QMessageBox.warning(self, "Launch failed", str(e))
            return

        QTimer.singleShot(500, self._poll_for_running)

    def _poll_for_running(self):
        if self.current_process and self.current_process.poll() is None:
            QTimer.singleShot(600, self._show_close_after_app_ready)
        else:
            QTimer.singleShot(500, self._poll_for_running)

    def _show_close_after_app_ready(self):
        if not (self.current_process and self.current_process.poll() is None):
#            self.overlay.hide()
            self.ui_container.show()
            return

        self.overlay_anim.stop()
        self.overlay_anim.setDuration(300)
        self.overlay_anim.setStartValue(self.overlay.windowOpacity())
        self.overlay_anim.setEndValue(0.0)
        self.overlay_anim.setEasingCurve(QEasingCurve.Type.InOutQuad)

        def _on_fade_done():
#            self.overlay.hide()
            self.close_btn.show()
            self.raise_timer.start(100)

        try:
            self.overlay_anim.finished.disconnect()
        except Exception:
            pass
        self.overlay_anim.finished.connect(_on_fade_done)
        self.overlay_anim.start()

    # ---------------- PLUGIN LAUNCH ---------------- #
    def _start_plugin_safe(self, cfg):
        app_name = cfg.get("name", "Unknown Plugin")
        plugin_widget = load_plugin(app_name, cfg, parent=self)
        if plugin_widget:
            self.launch_plugin(app_name, plugin_widget)
        else:
            self.ui_container.show()

    def launch_plugin(self, app_name, widget):
        try:
            widget.setWindowTitle(app_name)
            w = int(widget.cfg.get("width", 900))
            h = int(widget.cfg.get("height", 700))
            x = int(widget.cfg.get("x", (self.screen_width - w) // 2))
            y = int(widget.cfg.get("y", (self.screen_height - h) // 2))
            widget.setGeometry(x, y, w, h)
            widget.show()
            self.current_plugin = widget
#            self.overlay.hide()
            self.close_btn.show()
            self.raise_timer.start(100)
            log(f"[PLUGIN] ▶ Running '{app_name}'")
        except Exception as e:
            log(f"[PLUGIN] ⚠ Error running '{app_name}': {e}")
            QMessageBox.critical(self, "Plugin Error", str(e))

    # ---------------- CLEANUP ---------------- #
    def close_current(self):
        if self.current_plugin:
            try:
                if hasattr(self.current_plugin, "on_close"):
                    self.current_plugin.on_close()
                self.current_plugin.close()
            except Exception as e:
                log("Error closing plugin:", e)
            self.current_plugin = None

        if self.current_process:
            try:
                pid = self.current_process.pid
                pgid = os.getpgid(pid)
                os.killpg(pgid, signal.SIGTERM)
                time.sleep(0.4)
            except Exception:
                pass
            try:
                subprocess.run("pkill -f firefox", shell=True)
            except Exception:
                pass
            self.current_process = None

        self.overlay.hide()
        self.ui_container.show()
        self.close_btn.hide()
        self.raise_timer.stop()

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
    launcher = OverlayLauncher(apps, screen_width=SCREEN_W, screen_height=SCREEN_H)
    launcher.show()
    sys.exit(app.exec())
