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
    """Safely load plugin widgets."""
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

        plugin_widget.setWindowFlags(
            plugin_widget.windowFlags()
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
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
    """
    Top-level always-on-top floating close button.
    This is intentionally a top-level widget (no parent) so it can stay above apps/plugins.
    """
    def __init__(self, callback, screen_w=SCREEN_W, screen_h=SCREEN_H, margin=16):
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
        # Make it a top-level tool window that stays on top of other windows
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self._screen_w = screen_w
        self._screen_h = screen_h
        self._margin = margin
        # initial position (we'll move on show)
        self.move(self._screen_w - size - self._margin, self._screen_h - size - self._margin)

    def show(self):
        # Ensure positioned relative to screen size and then show
        size = self.width()
        x = self._screen_w - size - self._margin
        y = self._screen_h - size - self._margin
        try:
            super().move(x, y)
        except Exception:
            pass
        super().show()


# ---------- Main Launcher ----------
class OverlayLauncher(QWidget):
    def __init__(self, apps):
        super().__init__()
        # REMOVE WindowStaysOnTopHint from the main launcher so apps can appear above it
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setFixedSize(SCREEN_W, SCREEN_H)

        self.apps = apps
        self.page = 0
        self.apps_per_page = 9
        self.current_process = None
        self.current_plugin = None
        self.last_launch_cfg = None

        # Overlay background (child of launcher, dims the UI)
        self.overlay = QWidget(self)
        self.overlay.setGeometry(0, 0, SCREEN_W, SCREEN_H)
        self.overlay.setStyleSheet("background-color: rgba(0,0,0,220);")
        self.overlay.hide()
        self.overlay_anim = QPropertyAnimation(self.overlay, b"windowOpacity", self)

        # UI container (so we can easily show/hide UI)
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

        # Bottom bar
        bottom_bar = QHBoxLayout()
        bottom_bar.setContentsMargins(8, 0, 8, 8)

        # Stop Launcher (bottom-left)
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

        # Floating close button (top-level always-on-top)
        self.close_btn = FloatingCloseButton(self.close_current, screen_w=SCREEN_W, screen_h=SCREEN_H, margin=16)
        # don't setParent: it's intentionally top-level so it stays above launched apps
        # but we'll hide/show it from the launcher
        self.close_btn.hide()

        # Timer to keep the floating button on top (calls raise_)
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
        # close any previous
        self.close_current()

        cmd = cfg["cmd"]
        self.last_launch_cfg = cfg

        # show overlay (dims the launcher UI) but DO NOT set launcher always-on-top
        self.overlay.setWindowOpacity(0.0)
        self.overlay.show()
        self.overlay.raise_()
        self.overlay_anim.stop()
        self.overlay_anim.setDuration(300)
        self.overlay_anim.setStartValue(0.0)
        self.overlay_anim.setEndValue(0.9)
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

            proc = subprocess.Popen(cmd_str, shell=True, preexec_fn=os.setsid)
            self.current_process = proc
            log(f"Launched PID {proc.pid}: {cmd_str}")
        except Exception as e:
            QMessageBox.warning(self, "Launch failed", str(e))
            self.overlay.hide()
            self.ui_container.show()
            return

        # Try to focus launched app after short delay
        QTimer.singleShot(700, lambda: self._focus_launched_process(proc.pid, cfg))
        # Poll and fade overlay out after attempts
        QTimer.singleShot(500, self._poll_for_running)

    def _poll_for_running(self):
        if self.current_process and self.current_process.poll() is None:
            QTimer.singleShot(600, self._show_close_after_launch)
        else:
            QTimer.singleShot(500, self._poll_for_running)

    def _show_close_after_launch(self):
        # fade overlay out — apps should be above launcher now (launcher is NOT always-on-top)
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
            # show floating close button (top-level)
            try:
                self.close_btn.show()
                self.close_btn.raise_()
            except Exception:
                pass
            self.raise_timer.start(100)

        try:
            self.overlay_anim.finished.disconnect()
        except Exception:
            pass
        self.overlay_anim.finished.connect(_on_fade_done)
        self.overlay_anim.start()

    # ---------- Plugin Launch ----------
    def _start_plugin_safe(self, cfg):
        widget = load_plugin(cfg.get("name", "Unknown"), cfg, parent=self)
        if widget:
            self.launch_plugin(widget)
        else:
            self.ui_container.show()

    def launch_plugin(self, widget):
        try:
            w = int(getattr(widget, "cfg", {}).get("width", 900))
            h = int(getattr(widget, "cfg", {}).get("height", 700))
            x = int(getattr(widget, "cfg", {}).get("x", (SCREEN_W - w) // 2))
            y = int(getattr(widget, "cfg", {}).get("y", (SCREEN_H - h) // 2))
            widget.setGeometry(x, y, w, h)
            # ensure plugin is a top-level window and on top
            widget.setWindowFlags(widget.windowFlags() | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
            widget.show()
            widget.raise_()
            try:
                widget.activateWindow()
            except Exception:
                pass
            self.current_plugin = widget
            # hide overlay (plugin is top-level now)
            self.overlay.hide()
            # show floating close button (top-level)
            self.close_btn.show()
            self.close_btn.raise_()
            self.raise_timer.start(100)
            log(f"[PLUGIN] ▶ Running plugin window")
        except Exception as e:
            log(f"[PLUGIN] ⚠ Error running plugin: {e}")
            QMessageBox.critical(self, "Plugin Error", str(e))
            self.ui_container.show()

    # ---------- Focus Helper ----------
    def _focus_launched_process(self, pid, cfg):
        # try custom focus_command first
        focus_cmd = cfg.get("focus_command")
        if focus_cmd:
            try:
                r = subprocess.run(focus_cmd, shell=True)
                if r.returncode == 0:
                    return True
            except Exception:
                pass

        # xdotool
        if shutil.which("xdotool"):
            try:
                out = subprocess.run(["xdotool", "search", "--pid", str(pid)], capture_output=True, text=True)
                winids = [l.strip() for l in out.stdout.splitlines() if l.strip()]
                if not winids and cfg.get("name"):
                    out = subprocess.run(["xdotool", "search", "--name", cfg.get("name")], capture_output=True, text=True)
                    winids = [l.strip() for l in out.stdout.splitlines() if l.strip()]
                for wid in winids:
                    subprocess.run(["xdotool", "windowactivate", "--sync", wid])
                    return True
            except Exception as e:
                log("[FOCUS][xdotool] error:", e)

        # wmctrl
        if shutil.which("wmctrl"):
            try:
                out = subprocess.run(["wmctrl", "-lp"], capture_output=True, text=True)
                for line in out.stdout.splitlines():
                    parts = line.split()
                    if len(parts) >= 3:
                        winid = parts[0]
                        try:
                            win_pid = int(parts[2])
                        except Exception:
                            continue
                        if win_pid == pid or (cfg.get("name") and cfg.get("name").lower() in line.lower()):
                            subprocess.run(["wmctrl", "-ia", winid])
                            return True
            except Exception as e:
                log("[FOCUS][wmctrl] error:", e)
        # fallback: try focusing child processes in retries (handled by caller)
        return False

    # ---------- Close / Cleanup ----------
    def close_current(self):
        # close plugin
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
                try:
                    pgid = os.getpgid(pid)
                    os.killpg(pgid, signal.SIGTERM)
                except Exception:
                    try:
                        self.current_process.terminate()
                    except Exception:
                        pass
                time.sleep(0.4)
            except Exception:
                pass

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

            # last-resort token pkill (cautious)
            try:
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
                    if "firefox" in token:
                        subprocess.run("pkill -f firefox", shell=True)
                    else:
                        subprocess.run(f"pkill -f {token}", shell=True)
            except Exception as e:
                log("pkill fallback error:", e)

            self.current_process = None

        # hide overlay and show UI again
        try:
            self.overlay.hide()
        except Exception:
            pass

        # hide the top-level close button
        try:
            self.close_btn.hide()
        except Exception:
            pass
        self.raise_timer.stop()

        # ensure launcher UI visible
        try:
            self.ui_container.show()
        except Exception:
            pass

    def _raise_close_btn(self):
        try:
            if self.close_btn.isVisible():
                self.close_btn.raise_()
                self.close_btn.activateWindow()
            else:
                self.raise_timer.stop()
        except Exception:
            self.raise_timer.stop()

    def stop_launcher(self):
        self.close_current()
        QApplication.quit()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    launcher = OverlayLauncher(apps)
    launcher.show()
    sys.exit(app.exec())
