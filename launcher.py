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
        # instantiate plugin passing apps mapping + cfg if plugin supports it
        # many plugins (like your nmap) accept parent only; try both
        try:
            plugin_widget = cls(parent=None, apps=apps_dict, cfg=app_data)
        except TypeError:
            # fallback to legacy signature
            plugin_widget = cls(parent=None)
            # attach cfg for later use if missing
            try:
                plugin_widget.cfg = app_data
            except Exception:
                pass

        # ensure plugin is on top
        plugin_widget.setWindowFlags(plugin_widget.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
        # don't show here — caller may reposition; returning the widget gives caller control
        if hasattr(plugin_widget, "on_start"):
            try:
                plugin_widget.on_start()
            except Exception as e:
                log(f"[PLUGIN] on_start() error in {app_name}: {e}")

        log(f"[PLUGIN] ✅ Instantiated '{app_name}' ({plugin_path})")
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
        # remember last launched cfg for focus attempts
        self.last_launch_cfg = None

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

        # Close Button (top-right)
        self.close_btn = FloatingCloseButton(self.close_current, screen_w=screen_width, margin=16)
        self.close_btn.set_parent_parent(self)
        self.close_btn.hide()

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

    # ---------- launch handling ----------
    def launch_app(self, cfg):
        self.close_current()
        cmd = cfg["cmd"]
        self.last_launch_cfg = cfg  # remember for focus attempts
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

        try:
            cmd_str = cmd if isinstance(cmd, str) else " ".join(cmd)
            primary = cmd_str.split()[0]
            if shutil.which(primary) is None:
                lower_primary = primary.lower()
                if shutil.which(lower_primary):
                    rest = " ".join(cmd_str.split()[1:])
                    cmd_str = f"{lower_primary} {rest}".strip()
                    log(f"Auto-corrected command → {cmd_str}")

            # Start the process. Keep shell=True so existing config works.
            proc = subprocess.Popen(cmd_str, shell=True, preexec_fn=os.setsid)
            self.current_process = proc
            log(f"Launched PID {proc.pid}: {cmd_str}")
        except Exception as e:
            log("Launch failed:", e)
            self.overlay.hide()
            self.ui_container.show()
            QMessageBox.warning(self, "Launch failed", str(e))
            return

        # Try to focus the launched app after a short delay.
        QTimer.singleShot(700, lambda pid=proc.pid, c=cfg: self._focus_launched_process(pid, c))

        # Poll for app windows then fade overlay out (but only hide overlay after focus attempt)
        QTimer.singleShot(500, self._poll_for_running)

    def _poll_for_running(self):
        if self.current_process and self.current_process.poll() is None:
            QTimer.singleShot(600, self._show_close_after_app_ready)
        else:
            QTimer.singleShot(500, self._poll_for_running)

    def _show_close_after_app_ready(self):
        if not (self.current_process and self.current_process.poll() is None):
            # process died — restore UI
            self.overlay.hide()
            self.ui_container.show()
            return

        # Try one final focus attempt before fading overlay out
        try:
            pid = self.current_process.pid if self.current_process else None
            if pid and self.last_launch_cfg:
                log("[FOCUS] final focus attempt before removing overlay")
                self._focus_launched_process(pid, self.last_launch_cfg, tries=4, interval_ms=300)
        except Exception:
            pass

        # fade overlay out and then hide it — the focus calls should have raised the app above overlay
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
            self.close_btn.show()
            self.raise_timer.start(100)

        try:
            self.overlay_anim.finished.disconnect()
        except Exception:
            pass
        self.overlay_anim.finished.connect(_on_fade_done)
        self.overlay_anim.start()

    # ---------------- FOCUS HELPERS ---------------- #
    def _focus_launched_process(self, pid, cfg, tries=6, interval_ms=400):
        """
        Attempt to focus the window of the launched process.
        Strategy:
         - If cfg defines "focus_command", run that first (highest priority).
         - Then try xdotool/wmctrl when available (works on X11).
         - Retry looking for child PIDs if needed.
        """
        focus_cmd = cfg.get("focus_command")
        if focus_cmd:
            try:
                log(f"[FOCUS] Running custom focus_command for '{cfg.get('name')}' -> {focus_cmd}")
                r = subprocess.run(focus_cmd, shell=True)
                if r.returncode == 0:
                    log("[FOCUS] focus_command succeeded")
                    return True
                else:
                    log(f"[FOCUS] focus_command returned {r.returncode}, falling back")
            except Exception as e:
                log(f"[FOCUS] focus_command error: {e}")

        # Try to focus pid or window name directly
        success = self._focus_window_for_pid(pid, cfg.get("name"))
        if success:
            log(f"[FOCUS] Focused pid {pid}")
            return True

        # If focusing failed, try several times (app might still be starting, or spawn a child)
        attempt_count = {"n": 0}

        def _retry():
            attempt_count["n"] += 1
            found = False
            try:
                root_proc = psutil.Process(pid)
                for p in root_proc.children(recursive=True):
                    if self._focus_window_for_pid(p.pid, cfg.get("name")):
                        found = True
                        break
            except Exception:
                pass

            if found:
                log(f"[FOCUS] Focused child window for pid {pid}")
                return True

            if attempt_count["n"] < tries:
                QTimer.singleShot(interval_ms, _retry)
            else:
                log(f"[FOCUS] Giving up focusing pid {pid} after {tries} tries.")
                return False

        QTimer.singleShot(interval_ms, _retry)
        return False

    def _focus_window_for_pid(self, pid, name_hint=None):
        """Try multiple external tools to focus a window belonging to pid (or matching name_hint)."""
        # Strategy 1: xdotool (best option on X11)
        if shutil.which("xdotool"):
            try:
                out = subprocess.run(["xdotool", "search", "--pid", str(pid)], capture_output=True, text=True)
                winids = [l.strip() for l in out.stdout.splitlines() if l.strip()]
                if not winids and name_hint:
                    out = subprocess.run(["xdotool", "search", "--name", name_hint], capture_output=True, text=True)
                    winids = [l.strip() for l in out.stdout.splitlines() if l.strip()]

                for wid in winids:
                    subprocess.run(["xdotool", "windowactivate", "--sync", wid])
                    return True
            except Exception as e:
                log("[FOCUS][xdotool] error:", e)

        # Strategy 2: wmctrl
        if shutil.which("wmctrl"):
            try:
                out = subprocess.run(["wmctrl", "-lp"], capture_output=True, text=True)
                lines = out.stdout.splitlines()
                for line in lines:
                    parts = line.split()
                    if len(parts) >= 3:
                        winid = parts[0]
                        try:
                            win_pid = int(parts[2])
                        except Exception:
                            continue
                        if win_pid == pid or (name_hint and name_hint.lower() in line.lower()):
                            subprocess.run(["wmctrl", "-ia", winid])
                            return True
            except Exception as e:
                log("[FOCUS][wmctrl] error:", e)

        return False

    # ---------------- PLUGIN LAUNCH ---------------- #
    def _start_plugin_safe(self, cfg):
        app_name = cfg.get("name", "Unknown Plugin")
        widget = load_plugin(app_name, cfg, parent=self)
        if widget:
            self.launch_plugin(app_name, widget)
        else:
            self.ui_container.show()

    def launch_plugin(self, app_name, widget):
        try:
            widget.setWindowTitle(app_name)
            # ensure plugin has cfg attribute (some plugins read widget.cfg)
            if not hasattr(widget, "cfg"):
                try:
                    widget.cfg = {}
                except Exception:
                    pass
            # size & pos
            w = int(widget.cfg.get("width", 900)) if hasattr(widget, "cfg") else int(900)
            h = int(widget.cfg.get("height", 700)) if hasattr(widget, "cfg") else int(700)
            x = int(widget.cfg.get("x", (self.screen_width - w) // 2)) if hasattr(widget, "cfg") else (self.screen_width - w) // 2
            y = int(widget.cfg.get("y", (self.screen_height - h) // 2)) if hasattr(widget, "cfg") else (self.screen_height - h) // 2
            widget.setGeometry(x, y, w, h)
            widget.setWindowFlags(widget.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
            widget.show()
            widget.raise_()
            try:
                widget.activateWindow()
            except Exception:
                pass
            self.current_plugin = widget
            self.overlay.hide()
            self.close_btn.show()
            self.raise_timer.start(100)
            log(f"[PLUGIN] ▶ Running '{app_name}'")
        except Exception as e:
            log(f"[PLUGIN] ⚠ Error running '{app_name}': {e}")
            QMessageBox.critical(self, "Plugin Error", str(e))
            self.ui_container.show()

    # ---------- close / cleanup ----------
    def close_current(self):
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

        if self.current_process:
            try:
                pid = self.current_process.pid
                # Try to terminate the whole process group first
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

            # best-effort fallback by token
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
