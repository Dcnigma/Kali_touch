#!/usr/bin/env python3
import sys
import os
import json
import subprocess
import importlib
import signal
import traceback
import shutil           # <--- fixed: previously missing
from time import sleep

from PyQt6.QtWidgets import (
    QApplication, QWidget, QPushButton, QGridLayout, QLabel,
    QHBoxLayout, QVBoxLayout, QSpacerItem, QSizePolicy, QMessageBox,
    QDialog, QComboBox, QFormLayout, QDialogButtonBox
)
from PyQt6.QtCore import Qt, QTimer, QPropertyAnimation, QSize
from PyQt6.QtGui import QPixmap, QIcon, QGuiApplication

CONFIG_FILE = "apps.json"
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

        # Try common constructor patterns
        try:
            plugin_widget = cls(parent=parent, apps=apps_dict, cfg=app_data)
        except TypeError:
            try:
                plugin_widget = cls(parent=parent)
                setattr(plugin_widget, "cfg", app_data)
            except TypeError:
                plugin_widget = cls()
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
    def __init__(self, callback, parent=None):
        super().__init__("✕", parent=parent)
        size = 75
        self.setFixedSize(size, size)
        self.setStyleSheet(f"""
            QPushButton {{
                font-size: 28px;
                background-color: rgba(0,0,0,180);
                color: white;
                border-radius: {size//2}px;
                border: 2px solid rgba(255,255,255,160);
            }}
            QPushButton:hover {{ background-color: rgba(200,0,0,220); }}
        """)
        self.clicked.connect(callback)
        # keep it above other windows, but as a tool widget of the main app
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )


# ---------- Settings Dialog ----------
class SettingsDialog(QDialog):
    def __init__(self, parent=None, settings_path="launcher_settings.json"):
        super().__init__(parent)
        self.setWindowTitle("Launcher Settings")
        self.settings_path = settings_path
        self.resize(480, 220)

        layout = QFormLayout(self)

        self.theme_cb = QComboBox()
        self.theme_cb.addItems(["Default", "Dark", "Light"])
        layout.addRow("Theme:", self.theme_cb)

        self.sort_cb = QComboBox()
        self.sort_cb.addItems(["By name", "By category", "Manual"])
        layout.addRow("Sort:", self.sort_cb)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addRow(btns)

        self.load_settings()

    def load_settings(self):
        if os.path.exists(self.settings_path):
            try:
                with open(self.settings_path, "r") as f:
                    s = json.load(f)
                self.theme_cb.setCurrentText(s.get("theme", "Default"))
                self.sort_cb.setCurrentText(s.get("sort", "By name"))
            except Exception:
                pass

    def save_settings(self):
        s = {"theme": self.theme_cb.currentText(), "sort": self.sort_cb.currentText()}
        try:
            with open(self.settings_path, "w") as f:
                json.dump(s, f, indent=2)
        except Exception:
            pass

    def accept(self) -> None:
        self.save_settings()
        super().accept()


# ---------- Main Launcher ----------
class OverlayLauncher(QWidget):
    def __init__(self, apps):
        super().__init__()

        # Determine real screen size dynamically
        screen = QGuiApplication.primaryScreen()
        if screen:
            ssz = screen.size()
            self.SCREEN_W, self.SCREEN_H = ssz.width(), ssz.height()
        else:
            # fallback defaults
            self.SCREEN_W, self.SCREEN_H = 1024, 800

        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setFixedSize(self.SCREEN_W, self.SCREEN_H)

        self.apps = apps
        self.page = 0
        self.apps_per_page = 9
        self.current_process = None
        self.current_plugin = None
        self.last_launch_cfg = None

        # Overlay background (semi transparent while launching)
        self.overlay = QWidget(self)
        self.overlay.setGeometry(0, 0, self.SCREEN_W, self.SCREEN_H)
        self.overlay.setStyleSheet("background-color: rgba(0,0,0,200);")
        self.overlay.hide()

        self.overlay_anim = QPropertyAnimation(self.overlay, b"windowOpacity", self)

        # UI container
        self.ui_container = QWidget(self)
        self.ui_container.setGeometry(0, 0, self.SCREEN_W, self.SCREEN_H)
        ui_layout = QVBoxLayout(self.ui_container)
        ui_layout.setSpacing(10)
        ui_layout.setContentsMargins(36, 20, 36, 18)

        # App grid (3x3 -> 9)
        self.grid = QGridLayout()
        self.grid.setSpacing(12)
        ui_layout.addLayout(self.grid)

        ui_layout.addItem(QSpacerItem(0, 0, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding))

        # ---------- Bottom bar ----------
        bottom_bar = QHBoxLayout()
        bottom_bar.setContentsMargins(8, 0, 8, 8)

        # Stop Launcher button (bottom-left) = Close UI
        self.stop_btn = QPushButton("Stop Launcher")
        self.stop_btn.setFixedSize(180, 64)
        self.stop_btn.setStyleSheet("font-size:18px; background-color:#5a5a5a; color:white; border-radius:8px;")
        self.stop_btn.clicked.connect(self.stop_launcher)
        bottom_bar.addWidget(self.stop_btn, alignment=Qt.AlignmentFlag.AlignLeft)

        bottom_bar.addStretch(1)

        # Page label center
        self.page_label = QLabel()
        self.page_label.setStyleSheet("font-size:18px; color:white;")
        bottom_bar.addWidget(self.page_label, alignment=Qt.AlignmentFlag.AlignCenter)

        bottom_bar.addStretch(1)

        # Right side: close UI (again), settings, prev, next
        right_container = QHBoxLayout()

        # Close UI (redundant to stop_btn but placed per request left of settings)
        self.close_ui_btn = QPushButton("Close UI")
        self.close_ui_btn.setFixedSize(140, 64)
        self.close_ui_btn.setStyleSheet("font-size:16px; background-color:#7a7a7a; color:white; border-radius:8px;")
        self.close_ui_btn.clicked.connect(self.stop_launcher)
        right_container.addWidget(self.close_ui_btn)

        # Settings button
        self.settings_btn = QPushButton("Settings")
        self.settings_btn.setFixedSize(140, 64)
        self.settings_btn.setStyleSheet("font-size:16px; background-color:#3d6fb3; color:white; border-radius:8px;")
        self.settings_btn.clicked.connect(self.open_settings)
        right_container.addWidget(self.settings_btn)

        nav_style = "font-size:18px; background-color:#444; color:white; border-radius:8px; padding:8px 16px;"
        self.prev_btn = QPushButton("← Prev")
        self.prev_btn.setFixedSize(120, 64)
        self.prev_btn.setStyleSheet(nav_style)
        self.prev_btn.clicked.connect(self.prev_page)
        self.next_btn = QPushButton("Next →")
        self.next_btn.setFixedSize(120, 64)
        self.next_btn.setStyleSheet(nav_style)
        self.next_btn.clicked.connect(self.next_page)

        right_container.addWidget(self.prev_btn)
        right_container.addWidget(self.next_btn)

        bottom_bar.addLayout(right_container)

        ui_layout.addLayout(bottom_bar)

        # Floating close button (top-right ~75x75)
        self.close_btn = FloatingCloseButton(self.close_current, parent=self)
        self.close_btn.hide()
        self._position_close_btn()  # initial position

        # timer to raise the button above other windows
        self.raise_timer = QTimer(self)
        self.raise_timer.timeout.connect(self._raise_close_btn)

        self.show_page()

    def resizeEvent(self, ev):
        """Keep overlay and ui_container sized, reposition close button."""
        self.overlay.setGeometry(0, 0, self.width(), self.height())
        self.ui_container.setGeometry(0, 0, self.width(), self.height())
        self._position_close_btn()
        super().resizeEvent(ev)

    def _position_close_btn(self):
        padding = 15
        x = self.width() - padding - self.close_btn.width()
        y = padding
        self.close_btn.move(x, y)

    # ---------- Page Navigation ----------
    def show_page(self):
        for i in reversed(range(self.grid.count())):
            item = self.grid.itemAt(i)
            if item is None:
                continue
            w = item.widget()
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
                btn.setIconSize(QSize(64, 64))

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

    # ---------- Settings ----------
    def open_settings(self):
        dlg = SettingsDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            QMessageBox.information(self, "Settings", "Settings saved.")

    # ---------- Launch App (external process) ----------
    def launch_app(self, cfg):
        """Launch external command, then attempt to move/resize its window per cfg."""
        self.close_current()
        self.ui_container.hide()
        self.last_launch_cfg = cfg

        cmd = cfg["cmd"]

        # show overlay animation
        self.overlay.setWindowOpacity(0.0)
        self.overlay.show()
        self.overlay.raise_()
        try:
            self.overlay_anim.stop()
            self.overlay_anim.setDuration(200)
            self.overlay_anim.setStartValue(0.0)
            self.overlay_anim.setEndValue(0.9)
            self.overlay_anim.start()
        except Exception:
            pass

        try:
            # If user provided a list, use it, otherwise treat as shell command
            if isinstance(cmd, (list, tuple)):
                proc = subprocess.Popen(cmd, preexec_fn=os.setsid)
            else:
                # Use shell so commands like "flatpak run ..." work as written in JSON
                proc = subprocess.Popen(cmd, shell=True, preexec_fn=os.setsid,
                                        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            self.current_process = proc
            log(f"Launched PID {proc.pid}: {cmd}")
        except Exception as e:
            QMessageBox.warning(self, "Launch failed", f"Failed to start:\n{e}")
            self.overlay.hide()
            self.ui_container.show()
            self.current_process = None
            return

        # Attempt to arrange the window after it appears with retries
        attempts = 10
        delay_ms = 300

        def try_arrange(attempt=0):
            if self.current_process is None:
                return
            pid = self.current_process.pid
            try:
                arranged = self._arrange_window_by_pid(pid, cfg)
            except Exception as e:
                log(f"[ARRANGE] unexpected error: {e}")
                arranged = False

            if arranged:
                # success: show close button and stop attempts
                self.overlay.hide()
                self.close_btn.show()
                self.raise_timer.start(100)
            else:
                if attempt + 1 < attempts:
                    QTimer.singleShot(delay_ms, lambda: try_arrange(attempt + 1))
                else:
                    # final fallback: hide overlay, show close button anyway
                    # and leave app running even if not repositioned
                    self.overlay.hide()
                    self.close_btn.show()
                    self.raise_timer.start(100)
                    # log stderr if command likely failed (non-zero) - but do not crash
                    if self.current_process:
                        try:
                            out, err = self.current_process.communicate(timeout=0.1)
                            if err:
                                log(f"[PROC STDERR] {err.strip()}")
                        except Exception:
                            pass

        QTimer.singleShot(500, lambda: try_arrange(0))

    def _arrange_window_by_pid(self, pid, cfg):
        """
        Try to find windows belonging to pid and move/resize them using xdotool.
        Returns True if at least one window arranged.
        """
        width = int(cfg.get("width", 0)) if cfg.get("width") else 0
        height = int(cfg.get("height", 0)) if cfg.get("height") else 0
        x = int(cfg.get("x", 0)) if cfg.get("x") is not None else None
        y = int(cfg.get("y", 0)) if cfg.get("y") is not None else None

        arranged_any = False

        # Use xdotool if available
        if shutil.which("xdotool"):
            try:
                cmd = f"xdotool search --pid {pid}"
                proc = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=2)
                out = proc.stdout.strip()
                if out:
                    wids = [w for w in out.splitlines() if w.strip()]
                    for wid in wids:
                        try:
                            if width and height:
                                subprocess.run(f"xdotool windowsize {wid} {width} {height}", shell=True)
                            if x is not None and y is not None:
                                subprocess.run(f"xdotool windowmove {wid} {x} {y}", shell=True)
                            subprocess.run(f"xdotool windowactivate {wid}", shell=True)
                            arranged_any = True
                        except Exception as e:
                            log(f"[xdotool] per-window error: {e}")
            except Exception as e:
                log(f"[xdotool] error: {e}")

        # wmctrl fallback: activate by name and try to -e geometry
        if not arranged_any and shutil.which("wmctrl"):
            try:
                title = cfg.get("name", "")
                if title:
                    subprocess.run(f"wmctrl -a \"{title}\"", shell=True)
                if width and height:
                    geom_x = x if x is not None else 0
                    geom_y = y if y is not None else 0
                    # gravity 0: default
                    cmd = f"wmctrl -r :ACTIVE: -e 0,{geom_x},{geom_y},{width},{height}"
                    subprocess.run(cmd, shell=True)
                    arranged_any = True
            except Exception as e:
                log(f"[wmctrl] error: {e}")

        return arranged_any

    # ---------- Plugin Launch ----------
    def _start_plugin_safe(self, cfg):
        widget = load_plugin(cfg.get("name", "Unknown"), cfg, parent=self)
        if widget:
            self.launch_plugin(widget)
        else:
            self.ui_container.show()

    def launch_plugin(self, widget):
        cfg = getattr(widget, "cfg", {}) or {}
        default_w, default_h = 900, 700
        w = int(cfg.get("width", default_w)) if cfg.get("width") else default_w
        h = int(cfg.get("height", default_h)) if cfg.get("height") else default_h
        x = int(cfg.get("x", (self.SCREEN_W - w) // 2)) if cfg.get("x") is not None else (self.SCREEN_W - w) // 2
        y = int(cfg.get("y", (self.SCREEN_H - h) // 2)) if cfg.get("y") is not None else (self.SCREEN_H - h) // 2

        try:
            widget.setGeometry(x, y, w, h)
            widget.setWindowFlags(widget.windowFlags() | Qt.WindowType.Window)
            widget.show()
            widget.raise_()
            widget.activateWindow()
        except Exception as e:
            log(f"[PLUGIN] show error: {e}")

        self.overlay.hide()
        self.close_btn.show()
        self.raise_timer.start(100)
        self.current_plugin = widget

    # ---------- Close / Stop ----------
    def close_current(self):
        # Close plugin (call its on_close if present first)
        if self.current_plugin:
            try:
                if hasattr(self.current_plugin, "on_close"):
                    try:
                        self.current_plugin.on_close()
                    except Exception:
                        pass
                self.current_plugin.close()
            except Exception:
                pass
            self.current_plugin = None

        # Kill external process group
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
            try:
                self.close_btn.raise_()
            except Exception:
                pass
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
