#!/usr/bin/env python3
import sys
import os
import json
import subprocess
import importlib
import signal
import traceback
import shutil
from time import sleep

from PyQt6.QtWidgets import (
    QApplication, QWidget, QPushButton, QGridLayout, QLabel,
    QHBoxLayout, QVBoxLayout, QSpacerItem, QSizePolicy, QMessageBox,
    QDialog, QComboBox, QFormLayout, QDialogButtonBox, QGraphicsOpacityEffect
)
from PyQt6.QtCore import Qt, QTimer, QPropertyAnimation, QSize, QEasingCurve
from PyQt6.QtGui import QPixmap, QIcon, QGuiApplication, QColor, QPalette

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

        try:
            plugin_widget = cls(None, apps=apps_dict, cfg=app_data)
        except TypeError:
            try:
                plugin_widget = cls(None)
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
        return None


# ---------- Floating Close Button ----------
class FloatingCloseButton(QPushButton):
    def __init__(self, callback):
        super().__init__("✕")
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
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        self.fade_effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.fade_effect)
        self.anim = QPropertyAnimation(self.fade_effect, b"opacity")
        self.anim.setDuration(300)
        self.anim.setEasingCurve(QEasingCurve.Type.InOutQuad)

    def fade_in(self):
        try:
            self.anim.finished.disconnect()
        except Exception:
            pass
        self.show()
        self.anim.stop()
        self.anim.setStartValue(0.0)
        self.anim.setEndValue(1.0)
        self.anim.start()
        try:
            self.raise_()
        except Exception:
            pass

    def fade_out(self):
        try:
            self.anim.finished.disconnect()
        except Exception:
            pass

        def hide_after():
            try:
                self.hide()
            except Exception:
                pass

        self.anim.stop()
        self.anim.setStartValue(1.0)
        self.anim.setEndValue(0.0)
        self.anim.finished.connect(hide_after)
        self.anim.start()


# ---------- Settings Dialog ----------
class SettingsDialog(QDialog):
    def __init__(self, parent=None, settings_path="launcher_settings.json"):
        super().__init__(parent)
        self.setWindowTitle("Launcher Settings")
        self.settings_path = settings_path
        self.resize(480, 260)

        layout = QFormLayout(self)

        self.theme_cb = QComboBox()
        self.theme_cb.addItems(["Dark", "Light"])
        layout.addRow("Theme:", self.theme_cb)

        self.sort_cb = QComboBox()
        self.sort_cb.addItems(["By name", "By category", "Manual"])
        layout.addRow("Sort:", self.sort_cb)

        self.view_cb = QComboBox()
        self.view_cb.addItems(["Grid 9x9", "Showcase 3"])
        layout.addRow("App layout:", self.view_cb)

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
                self.theme_cb.setCurrentText(s.get("theme", "Dark"))
                self.sort_cb.setCurrentText(s.get("sort", "By name"))
                self.view_cb.setCurrentText(s.get("view", "Grid 9x9"))
            except Exception:
                pass

    def save_settings(self):
        s = {
            "theme": self.theme_cb.currentText(),
            "sort": self.sort_cb.currentText(),
            "view": self.view_cb.currentText()
        }
        try:
            with open(self.settings_path, "w") as f:
                json.dump(s, f, indent=2)
        except Exception:
            pass

    def accept(self) -> None:
        self.save_settings()
        super().accept()


# ---------- Splash Screen ----------
class SplashScreen(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        screen = QGuiApplication.primaryScreen()
        size = screen.size() if screen else QSize(1024, 800)
        self.setFixedSize(size)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setStyleSheet("background-color: black;")

        vbox = QVBoxLayout(self)
        vbox.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label = QLabel("Kali Touch Launcher", self)
        self.label.setStyleSheet("color: white; font-size: 32px; font-weight: bold;")
        vbox.addWidget(self.label)

        self.fade_effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.fade_effect)
        self.anim = QPropertyAnimation(self.fade_effect, b"opacity")
        self.anim.setDuration(1200)
        self.anim.setEasingCurve(QEasingCurve.Type.InOutQuad)

    def show_splash(self, duration=1200):
        self.show()
        self.anim.stop()
        self.anim.setStartValue(0.0)
        self.anim.setEndValue(1.0)
        self.anim.start()
        QTimer.singleShot(duration, self.fade_out)

    def fade_out(self):
        self.anim.stop()
        self.anim.setStartValue(1.0)
        self.anim.setEndValue(0.0)
        self.anim.start()
        QTimer.singleShot(1200, self.close)


# ---------- Main Launcher ----------
class OverlayLauncher(QWidget):
    def __init__(self, apps):
        super().__init__()

        screen = QGuiApplication.primaryScreen()
        ssz = screen.size() if screen else QSize(1024, 800)
        self.SCREEN_W, self.SCREEN_H = ssz.width(), ssz.height()

        self.move(0, 0)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setFixedSize(self.SCREEN_W, self.SCREEN_H)

        self.apps = apps
        self.page = 0
        self.apps_per_page = 9
        self.current_process = None
        self.current_plugin = None

        self.theme_file = "launcher_settings.json"
        self.theme = self.load_theme()
        self.apply_theme(self.theme)


        # Overlay background
        self.overlay = QWidget(self)
        self.overlay.setGeometry(0, 0, self.SCREEN_W, self.SCREEN_H)
        self.overlay.setStyleSheet("background-color: rgba(0,0,0,200);")
        self.overlay.hide()

        # Main UI container
        self.ui_container = QWidget(self)
        self.ui_container.setGeometry(0, 0, self.SCREEN_W, self.SCREEN_H)
        ui_layout = QVBoxLayout(self.ui_container)
        ui_layout.setSpacing(10)
        ui_layout.setContentsMargins(36, 20, 36, 18)

        # --- Add top spacer to push apps lower (≈50px) ---
        ui_layout.addSpacerItem(QSpacerItem(0, 80, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed))

        # App grid
        self.grid = QGridLayout()
        self.grid.setSpacing(12)
        ui_layout.addLayout(self.grid)
        ui_layout.addItem(QSpacerItem(0, 0, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding))
        # Add stretch below grid so bottom bar stays near the bottom
        ui_layout.addStretch(1)
        
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

        right_container = QHBoxLayout()
        self.theme_btn = QPushButton("Theme")
        self.theme_btn.setFixedSize(120, 64)
        self.theme_btn.setStyleSheet("font-size:16px; background-color:#2a82da; color:white; border-radius:8px;")
        self.theme_btn.clicked.connect(self.toggle_theme)
        right_container.addWidget(self.theme_btn)

        self.settings_btn = QPushButton("Settings")
        self.settings_btn.setFixedSize(120, 64)
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

        # Floating close button
        self.close_btn = FloatingCloseButton(self.close_current)
        self.close_btn.hide()
        self._position_close_btn()

        self.raise_timer = QTimer(self)
        self.raise_timer.timeout.connect(self._raise_close_btn)

        self.show_page()

    # ---------- Theme ----------
    def load_theme(self):
        if os.path.exists(self.theme_file):
            try:
                with open(self.theme_file, "r") as f:
                    data = json.load(f)
                    self.view_mode = data.get("view", "Grid 9x9")
                    return data.get("theme", "Dark")
            except Exception:
                pass
        self.view_mode = "Grid 9x9"
        return "Dark"

    def apply_theme(self, theme):
        palette = QPalette()
        if theme == "Light":
            palette.setColor(QPalette.ColorRole.Window, QColor("#f0f0f0"))
            palette.setColor(QPalette.ColorRole.WindowText, Qt.GlobalColor.black)
        else:
            palette.setColor(QPalette.ColorRole.Window, QColor("#1e1e1e"))
            palette.setColor(QPalette.ColorRole.WindowText, Qt.GlobalColor.white)
        QApplication.instance().setPalette(palette)

    def toggle_theme(self):
        self.theme = "Light" if self.theme == "Dark" else "Dark"
        self.apply_theme(self.theme)
        with open(self.theme_file, "w") as f:
            json.dump({"theme": self.theme, "view": self.view_mode}, f, indent=2)
    # ---------- Page Handling ----------
    def show_page(self):
        # Clear grid
        for i in reversed(range(self.grid.count())):
            w = self.grid.itemAt(i).widget()
            if w:
                w.setParent(None)

        # Determine layout type
        grid_mode = (self.view_mode == "Grid 9x9")
        self.apps_per_page = 9 if grid_mode else 3

        start = self.page * self.apps_per_page
        end = start + self.apps_per_page
        page_items = self.apps[start:end]

        for idx, cfg in enumerate(page_items):
            if grid_mode:
                row, col = divmod(idx, 3)
            else:
                row, col = (0, idx)  # ← 1 row, 3 tiles side by side

            name = cfg.get("name", "App")
            icon_path = cfg.get("touch_icon")

            if grid_mode:
                # Normal grid layout
                btn = QPushButton()
                btn.setFixedSize(220, 116)
                btn.setStyleSheet("""
                    QPushButton {
                        font-size: 20px;
                        background-color: #2f2f2f;
                        color: white;
                        border-radius: 10px;
                    }
                    QPushButton:hover { background-color: #3a3a3a; }
                """)
                btn.setText(name)
                if icon_path and os.path.exists(icon_path):
                    pix = QPixmap(icon_path).scaled(64, 64, Qt.AspectRatioMode.KeepAspectRatio)
                    btn.setIcon(QIcon(pix))
                    btn.setIconSize(QSize(64, 64))

            else:
                # Showcase 3 layout: big tile, icon on top, text below
                tile = QWidget()
                vbox = QVBoxLayout(tile)
                vbox.setSpacing(12)
                vbox.setContentsMargins(8, 18, 8, 8)
                tile.setFixedSize(250, 200)
                tile.setStyleSheet("""
                    QWidget {
                        background-color: #3a3a3a;
                        border-radius: 16px;
                    }
                    QWidget:hover {
                        background-color: #4a4a4a;
                    }
                """)

                icon_label = QLabel()
                icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                if icon_path and os.path.exists(icon_path):
                    pix = QPixmap(icon_path).scaled(150, 150, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                    icon_label.setPixmap(pix)
                else:
                    icon_label.setText("📦")
                    icon_label.setStyleSheet("font-size: 72px; color: white;")

                text_label = QLabel(name)
                text_label.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
                text_label.setStyleSheet("font-size: 24px; color: white; font-weight: 500;")

                vbox.addWidget(icon_label, alignment=Qt.AlignmentFlag.AlignCenter)
                vbox.addWidget(text_label, alignment=Qt.AlignmentFlag.AlignTop)

                # Clickable overlay button
                btn = QPushButton(tile)
                btn.setCursor(Qt.CursorShape.PointingHandCursor)
                btn.setStyleSheet("""
                    QPushButton {
                        background-color: rgba(0,0,0,0);
                        border: none;
                    }
                    QPushButton:hover {
                        background-color: rgba(255,255,255,40);
                        border-radius: 16px;
                    }
                """)
                btn.setGeometry(0, 0, 360, 360)

            if "cmd" in cfg:
                btn.clicked.connect(lambda _, c=cfg: self.launch_app(c))
            elif "plugin" in cfg:
                btn.clicked.connect(lambda _, c=cfg: self._start_plugin_safe(c))

            # Add the correct widget to the grid
            self.grid.addWidget(tile if not grid_mode else btn, row, col, alignment=Qt.AlignmentFlag.AlignCenter)

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
            self.theme = dlg.theme_cb.currentText()
            self.view_mode = dlg.view_cb.currentText()
            self.apply_theme(self.theme)
            with open(self.theme_file, "w") as f:
                json.dump({"theme": self.theme, "view": self.view_mode}, f, indent=2)
            self.show_page()

    # ---------- App launching ----------
    def launch_app(self, cfg):
        self.move(0, 0)
        self.ui_container.move(0, 0)
        self.overlay.move(0, 0)
        self.overlay.raise_()
        self.close_btn.hide()
        self.ui_container.hide()
        self.overlay.show()

        try:
            cmd = cfg["cmd"]
            if isinstance(cmd, (list, tuple)):
                proc = subprocess.Popen(cmd, preexec_fn=os.setsid)
            else:
                proc = subprocess.Popen(cmd, shell=True, preexec_fn=os.setsid)
            self.current_process = proc
            log(f"Launched PID {proc.pid}: {cmd}")
            QTimer.singleShot(200, self.wait_for_window)
        except Exception as e:
            QMessageBox.warning(self, "Launch failed", str(e))
            self.overlay.hide()
            self.ui_container.show()
            return

    def wait_for_window(self):
        try:
            if shutil.which("xdotool") and self.current_process:
                pid = self.current_process.pid
                out = subprocess.getoutput(f"xdotool search --pid {pid}")
                if out.strip():
                    log(f"[LAUNCH] Window for PID {pid} detected → showing close button.")
                    self._finish_launch()
                    return
            if not hasattr(self, "_wait_tries"):
                self._wait_tries = 0
            self._wait_tries += 1
            if self._wait_tries < 25:
                QTimer.singleShot(200, self.wait_for_window)
            else:
                log("[LAUNCH] Timeout waiting for window; continuing anyway.")
                self._finish_launch()
        except Exception as e:
            log(f"[LAUNCH] wait_for_window error: {e}")
            self._finish_launch()

    def _finish_launch(self):
        self.overlay.hide()
        self.ensure_close_btn()
        self._position_close_btn()
        if self.close_btn:
            self.close_btn.fade_in()
        self.raise_timer.start(100)

    # ---------- Plugin ----------
    def _start_plugin_safe(self, cfg):
        widget = load_plugin(cfg.get("name", "Unknown"), cfg, parent=self)
        if widget:
            self.launch_plugin(widget)
        else:
            self.ui_container.show()

    def launch_plugin(self, widget):
        w, h = 900, 700
        x = (self.SCREEN_W - w) // 2
        y = (self.SCREEN_H - h) // 2
        widget.setGeometry(x, y, w, h)
        widget.show()
        widget.raise_()
        self.ensure_close_btn()
        self._position_close_btn()
        if self.close_btn:
            self.close_btn.fade_in()
        self.raise_timer.start(100)
        self.current_plugin = widget

    # ---------- Close ----------
    def close_current(self):
        if self.current_plugin:
            try:
                if hasattr(self.current_plugin, "on_close"):
                    self.current_plugin.on_close()
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
        self._position_close_btn()
        self.close_btn.fade_out()

    def _position_close_btn(self):
        pad = 15
        geo = self.geometry()
        x = geo.x() + geo.width() - pad - self.close_btn.width()
        y = geo.y() + pad
        try:
            self.close_btn.move(x, y)
        except Exception:
            pass

    def ensure_close_btn(self):
        if not getattr(self, "close_btn", None) or not isinstance(self.close_btn, QWidget):
            self.close_btn = FloatingCloseButton(self.close_current)
        self._position_close_btn()
        self.close_btn.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.close_btn.raise_()

    def _raise_close_btn(self):
        if self.close_btn and self.close_btn.isVisible():
            self.close_btn.raise_()
        else:
            self.raise_timer.stop()

    def stop_launcher(self):
        self.close_current()
        QApplication.quit()


# ---------- Main entry ----------
if __name__ == "__main__":
    app = QApplication(sys.argv)
    splash = SplashScreen()
    splash.show_splash()

    launcher = OverlayLauncher(apps)
    QTimer.singleShot(1800, launcher.show)

    sys.exit(app.exec())
