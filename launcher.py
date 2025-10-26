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


# Load apps from JSON (keeps duplicates by turning mapping into list of dicts)
with open(CONFIG_FILE, "r") as f:
    raw_apps = json.load(f)

# Keep both a dict and an ordered list
apps_dict = dict(raw_apps)  # original mapping (for plugins that may want it)
apps = []
for name, cfg in raw_apps.items():
    cfg = dict(cfg)  # shallow copy to avoid mutating raw_apps
    cfg["name"] = name
    apps.append(cfg)


class FloatingCloseButton(QPushButton):
    """Fixed top-right always-on-top close button (not draggable)."""
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
        # main window frameless and always on top
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setFixedSize(screen_width, screen_height)

        self.screen_width = screen_width
        self.screen_height = screen_height

        self.apps = apps
        self.page = 0
        self.apps_per_page = 9
        self.current_process = None
        self.current_plugin = None

        # --- overlay that will appear above the UI and fade ---
        self.overlay = QWidget(self)
        self.overlay.setGeometry(0, 0, screen_width, screen_height)
        self.overlay.setStyleSheet("background-color: rgba(0,0,0,230);")
        self.overlay.hide()
        self.overlay_anim = QPropertyAnimation(self.overlay, b"windowOpacity", self)

        # --- UI container (all launcher UI lives here so we can hide/show easily) ---
        self.ui_container = QWidget(self)
        self.ui_container.setGeometry(0, 0, screen_width, screen_height)
        ui_layout = QVBoxLayout(self.ui_container)
        ui_layout.setSpacing(10)
        ui_layout.setContentsMargins(36, 20, 36, 18)  # tuned margins to fit 1024x800

        # Grid area (3x3)
        self.grid = QGridLayout()
        self.grid.setSpacing(12)
        ui_layout.addLayout(self.grid)

        # spacer to push bottom bar to bottom
        ui_layout.addItem(QSpacerItem(0, 0, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding))

        # bottom bar layout (left: Stop, center: page label, right: nav)
        bottom_bar = QHBoxLayout()
        bottom_bar.setContentsMargins(8, 0, 8, 8)

        # Stop launcher (bottom-left)
        self.stop_btn = QPushButton("Stop Launcher")
        self.stop_btn.setFixedSize(180, 64)
        self.stop_btn.setStyleSheet("font-size:18px; background-color: #5a5a5a; color: white; border-radius: 8px;")
        self.stop_btn.clicked.connect(self.stop_launcher)
        bottom_bar.addWidget(self.stop_btn, alignment=Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom)

        # center label spacer
        bottom_bar.addStretch(1)

        self.page_label = QLabel()
        self.page_label.setStyleSheet("font-size:18px; color: white;")
        bottom_bar.addWidget(self.page_label, alignment=Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)

        bottom_bar.addStretch(1)

        # Prev/Next on bottom-right
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

        # --- Close button (top-right) ---
        self.close_btn = FloatingCloseButton(self.close_current, screen_w=screen_width, margin=16)
        self.close_btn.set_parent_parent(self)  # set parent & position
        self.close_btn.hide()

        # keep it on top if visible
        self.raise_timer = QTimer(self)
        self.raise_timer.timeout.connect(self._raise_close_btn)

        # initial population
        self.show_page()

    # ---------- pages / grid ----------
    def show_page(self):
        # clear grid
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
            # icon support
            icon_path = cfg.get("touch_icon")
            if icon_path and os.path.exists(icon_path):
                pix = QPixmap(icon_path).scaled(64, 64, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                btn.setIcon(QIcon(pix))
                btn.setIconSize(pix.size())
            # connect
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
        # close any previous
        self.close_current()

        cmd = cfg["cmd"]
        self.current_process = None
        self.current_plugin = None

        # hide UI so overlay sits above it
        self.ui_container.hide()

        # show overlay with fade-in
        self.overlay.setWindowOpacity(0.0)
        self.overlay.show()
        self.overlay.raise_()
        self.overlay_anim.stop()
        self.overlay_anim.setDuration(360)
        self.overlay_anim.setStartValue(0.0)
        self.overlay_anim.setEndValue(0.88)
        self.overlay_anim.setEasingCurve(QEasingCurve.Type.InOutQuad)
        self.overlay_anim.start()

        # prepare command string and try to auto-correct common case issues
        try:
            cmd_str = cmd if isinstance(cmd, str) else " ".join(cmd)
            primary = cmd_str.split()[0]
            if shutil.which(primary) is None:
                # try lowercased binary name (helps when JSON used "Mousepad" instead of "mousepad")
                lower_primary = primary.lower()
                if shutil.which(lower_primary):
                    rest = " ".join(cmd_str.split()[1:])
                    cmd_str = f"{lower_primary} {rest}".strip()
                    log(f"Auto-corrected command to: {cmd_str}")
            # launch
            proc = subprocess.Popen(cmd_str, shell=True, preexec_fn=os.setsid,
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self.current_process = proc
            log(f"Launched PID {proc.pid} -> {cmd_str}")
        except Exception as e:
            log("Launch failed:", e)
            self.overlay.hide()
            self.ui_container.show()
            QMessageBox.warning(self, "Launch failed", f"Failed to start:\n{e}")
            return

        # poll for started process and then fade overlay out
        QTimer.singleShot(500, self._poll_for_running)

    def _poll_for_running(self):
        if self.current_process and self.current_process.poll() is None:
            QTimer.singleShot(600, self._show_close_after_app_ready)
        else:
            # try again, app may be slow
            QTimer.singleShot(500, self._poll_for_running)

    def _show_close_after_app_ready(self):
        """Fade overlay out, show close button and restore small UI elements if needed."""
        if not (self.current_process and self.current_process.poll() is None):
            # process died — restore UI
            self.overlay.hide()
            self.ui_container.show()
            return

        # prepare fade-out
        self.overlay_anim.stop()
        self.overlay_anim.setDuration(300)
        self.overlay_anim.setStartValue(self.overlay.windowOpacity())
        self.overlay_anim.setEndValue(0.0)
        self.overlay_anim.setEasingCurve(QEasingCurve.Type.InOutQuad)

        def _on_fade_done():
            try:
                self.overlay.hide()
            except Exception:
                pass
            # keep UI hidden while app is visible; only show close button
            self.close_btn.show()
            self.raise_timer.start(100)

        # safely connect the finished handler (disconnect previous if present)
        try:
            self.overlay_anim.finished.disconnect()
        except Exception:
            pass
        self.overlay_anim.finished.connect(_on_fade_done)
        self.overlay_anim.start()

    # ---------- plugin support ----------
    def launch_plugin(self, plugin_path, cfg):
        self.close_current()
        self.ui_container.hide()
        try:
            module_name, class_name = [s.strip() for s in plugin_path.split(":")]
            module = importlib.import_module(module_name)
            cls = getattr(module, class_name)
            # pass apps mapping and cfg into plugin so it doesn't rely on globals
            # plugin signature should be: __init__(self, parent=None, apps=None, cfg=None)
            plugin_widget = cls(parent=None, apps=apps_dict, cfg=cfg)
            # call on_start if plugin implements it
            try:
                if hasattr(plugin_widget, "on_start"):
                    plugin_widget.on_start()
            except Exception as e:
                log("plugin.on_start error:", e)
            plugin_widget.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
            # plugin size or defaults
            w = int(cfg.get("width", 900))
            h = int(cfg.get("height", 700))
            x = int(cfg.get("x", (self.screen_width - w) // 2))
            y = int(cfg.get("y", (self.screen_height - h) // 2))
            plugin_widget.setGeometry(x, y, w, h)
            plugin_widget.show()
            self.current_plugin = plugin_widget
            # no overlay needed above plugin; keep plugin top and show close button
            self.overlay.hide()
            self.close_btn.show()
            self.raise_timer.start(100)
            log("Plugin launched:", plugin_path)
        except Exception as e:
            log("Plugin load error:", e)
            QMessageBox.critical(self, "Plugin Error", f"Failed to load plugin:\n{e}")
            self.ui_container.show()

    # ---------- close / cleanup ----------
    def close_current(self):
        # close plugin (call on_close if present)
        if self.current_plugin:
            try:
                if hasattr(self.current_plugin, "on_close"):
                    try:
                        self.current_plugin.on_close()
                    except Exception as e:
                        log("plugin.on_close error:", e)
                self.current_plugin.close()
            except Exception as e:
                log("Error closing plugin:", e)
            self.current_plugin = None

        # kill process group + children (best-effort)
        if self.current_process:
            try:
                pid = self.current_process.pid
                log("Attempting to terminate pgid for PID", pid)
                pgid = os.getpgid(pid)
                os.killpg(pgid, signal.SIGTERM)
                time.sleep(0.45)
            except Exception as e:
                log("Close error (pgid):", e)

            # psutil fallback
            try:
                parent = psutil.Process(pid)
                children = parent.children(recursive=True)
                for c in children:
                    try:
                        c.kill()
                    except Exception:
                        pass
                try:
                    parent.kill()
                except Exception:
                    pass
                gone, alive = psutil.wait_procs([parent] + children, timeout=2)
                for p in alive:
                    try:
                        p.kill()
                    except Exception:
                        pass
            except psutil.NoSuchProcess:
                pass
            except Exception as e:
                log("psutil cleanup error:", e)

            # last-resort: pkill by token (useful for firefox/flatpak wrappers)
            try:
                # try to find a meaningful token from the command line
                try:
                    cmdline = self.current_process.args if hasattr(self.current_process, "args") else ""
                except Exception:
                    cmdline = ""
                if isinstance(cmdline, (list, tuple)):
                    cmd_str = " ".join(cmdline)
                else:
                    cmd_str = str(cmdline)
                token = ""
                if cmd_str:
                    token = os.path.basename(cmd_str.split()[0]).lower()
                if token:
                    # specific fallback for firefox
                    if "firefox" in token:
                        subprocess.run("pkill -f firefox", shell=True)
                    else:
                        # general fallback (cautious)
                        subprocess.run(f"pkill -f {token}", shell=True)
            except Exception as e:
                log("pkill fallback error:", e)

            self.current_process = None

        # restore UI & hide overlay/close button
        try:
            self.overlay.hide()
        except Exception:
            pass
        self.ui_container.show()
        self.close_btn.hide()
        self.raise_timer.stop()

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
