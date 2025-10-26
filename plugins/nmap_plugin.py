# plugins/nmap_plugin.py
import os
import re
import shutil
import subprocess
import datetime
from typing import Optional, List

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QTextEdit,
    QMessageBox, QComboBox, QCheckBox
)
from PyQt6.QtCore import Qt, QProcess
from PyQt6.QtGui import QFont

IP_RE = re.compile(r"^([0-9]{1,3}\.){3}[0-9]{1,3}$")


def has_raw_privileges() -> bool:
    """Return True if current process can do raw sockets (root or nmap has capabilities)."""
    try:
        if os.geteuid() == 0:
            return True
    except Exception:
        pass
    getcap = shutil.which("getcap")
    nmap_path = shutil.which("nmap")
    if getcap and nmap_path:
        try:
            out = subprocess.run([getcap, nmap_path], capture_output=True, text=True, timeout=2)
            if "cap_net_raw" in out.stdout or "cap_net_admin" in out.stdout:
                return True
        except Exception:
            pass
    return False


class NmapPlugin(QWidget):
    """
    Touchscreen-friendly Nmap plugin.
    Constructor signature supports being called from the launcher:
        NmapPlugin(parent=None, apps=apps_dict, cfg=cfg)
    """

    name = "Nmap Scanner"
    description = "Run nmap scans (touchscreen)."

    def __init__(self, parent=None, apps: Optional[dict] = None, cfg: Optional[dict] = None):
        super().__init__(parent)
        # store references passed by launcher (optional)
        self.apps = apps or {}
        self.cfg = cfg or {}

        # process handling
        self.process: Optional[QProcess] = None
        self._has_retried = False
        self.allow_auto_fallback = True

        # UI
        self.setWindowTitle(self.name)
        layout = QVBoxLayout()
        layout.setSpacing(10)
        layout.setContentsMargins(16, 16, 16, 16)

        header = QLabel("Nmap Port Scanner")
        header.setFont(QFont("", 18, QFont.Weight.Bold))
        header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(header)

        # Target + ports (pre-fill from cfg if provided)
        row1 = QHBoxLayout()
        self.target_input = QLineEdit()
        self.target_input.setPlaceholderText("IP or hostname (e.g. 192.168.1.205)")
        self.target_input.setFixedHeight(56)
        self.target_input.setStyleSheet("font-size:16px;")
        # If launcher cfg provided a target, prefill
        pre_target = self.cfg.get("target") if isinstance(self.cfg, dict) else None
        if pre_target:
            self.target_input.setText(str(pre_target))
        row1.addWidget(self.target_input)

        self.port_input = QLineEdit()
        self.port_input.setPlaceholderText("Ports (e.g. 22 or 1-1024)")
        self.port_input.setFixedHeight(56)
        self.port_input.setFixedWidth(240)
        self.port_input.setStyleSheet("font-size:16px;")
        pre_ports = self.cfg.get("ports") if isinstance(self.cfg, dict) else None
        if pre_ports:
            self.port_input.setText(str(pre_ports))
        row1.addWidget(self.port_input)
        layout.addLayout(row1)

        # Options row
        row2 = QHBoxLayout()
        self.scan_type = QComboBox()
        self.scan_type.setFixedHeight(48)
        self.scan_type.addItems([
            "TCP Connect (-sT) — safe (no root)",
            "SYN Scan (-sS) — needs raw sockets",
            "UDP Scan (-sU) — needs raw sockets"
        ])
        row2.addWidget(self.scan_type)

        self.verbosity = QComboBox()
        self.verbosity.setFixedHeight(48)
        self.verbosity.addItems(["0", "1", "2"])
        row2.addWidget(QLabel("Verbosity:"))
        row2.addWidget(self.verbosity)

        self.timing = QComboBox()
        self.timing.setFixedHeight(48)
        self.timing.addItems([str(i) for i in range(0, 6)])
        row2.addWidget(QLabel("Timing:"))
        row2.addWidget(self.timing)

        layout.addLayout(row2)

        # Extra flags
        row3 = QHBoxLayout()
        self.os_detect_cb = QCheckBox("OS detect (-O)")
        self.service_version_cb = QCheckBox("Version (-sV)")
        self.ipv6_cb = QCheckBox("IPv6 (-6)")
        for cb in (self.os_detect_cb, self.service_version_cb, self.ipv6_cb):
            cb.setFixedHeight(36)
            row3.addWidget(cb)
        layout.addLayout(row3)

        # Fallback toggle (auto fallback to -sT)
        self.fallback_cb = QCheckBox("Auto-fallback to TCP Connect (-sT) if raw sockets fail")
        self.fallback_cb.setChecked(True)
        self.fallback_cb.setFixedHeight(36)
        layout.addWidget(self.fallback_cb)

        # Buttons row - Start / Stop / pkexec / Export
        btn_row = QHBoxLayout()
        self.start_btn = QPushButton("Start Scan")
        self.start_btn.setFixedHeight(72)
        self.start_btn.setStyleSheet("font-size:18px; background-color:#2e8b57; color:white;")
        self.start_btn.clicked.connect(self.on_start_scan)
        btn_row.addWidget(self.start_btn)

        self.stop_btn = QPushButton("Stop Scan")
        self.stop_btn.setFixedHeight(72)
        self.stop_btn.setStyleSheet("font-size:18px; background-color:#b22222; color:white;")
        self.stop_btn.clicked.connect(self.on_stop_scan)
        self.stop_btn.setEnabled(False)
        btn_row.addWidget(self.stop_btn)

        self.pkexec_btn = QPushButton("Run as root (pkexec)")
        self.pkexec_btn.setFixedHeight(72)
        self.pkexec_btn.setStyleSheet("font-size:16px; background-color:#ff8c00; color:white;")
        if shutil.which("pkexec") is None:
            self.pkexec_btn.setEnabled(False)
            self.pkexec_btn.setToolTip("pkexec not available")
        self.pkexec_btn.clicked.connect(self.on_start_pkexec_scan)
        btn_row.addWidget(self.pkexec_btn)

        # EXPORT button
        self.export_btn = QPushButton("Export Results")
        self.export_btn.setFixedHeight(72)
        self.export_btn.setStyleSheet("font-size:18px; background-color:#1e90ff; color:white;")
        self.export_btn.clicked.connect(self.on_export_results)
        self.export_btn.setEnabled(False)  # enabled after output appears
        btn_row.addWidget(self.export_btn)

        layout.addLayout(btn_row)

        # Output area
        self.output = QTextEdit()
        self.output.setReadOnly(True)
        self.output.setFixedHeight(320)
        self.output.setStyleSheet("font-size:14px;")
        layout.addWidget(self.output)

        # Back/Close (explicit close for launcher to use too)
        back_row = QHBoxLayout()
        self.back_btn = QPushButton("Back")
        self.back_btn.setFixedHeight(64)
        self.back_btn.setStyleSheet("font-size:16px;")
        self.back_btn.clicked.connect(self._on_back)
        back_row.addWidget(self.back_btn)
        layout.addLayout(back_row)

        self.setLayout(layout)

        # Show info about privileges if needed
        if not has_raw_privileges():
            self.append("Note: raw-socket scans (SYN/UDP, OS detection) not available to this user.\n"
                        "The plugin can run scans as root via pkexec when requested.\n\n")

    # ---------- helpers ----------
    def append(self, text: str):
        self.output.insertPlainText(text)
        self.output.verticalScrollBar().setValue(self.output.verticalScrollBar().maximum())

    def _build_args(self, force_sT: bool = False, strip_privileged: bool = False, skip_host_discovery: bool = False) -> Optional[List[str]]:
        target = self.target_input.text().strip()
        if not target:
            return None
        ports = self.port_input.text().strip() or "1-1024"

        mapping = {0: "-sT", 1: "-sS", 2: "-sU"}
        idx = self.scan_type.currentIndex()
        flag = mapping.get(idx, "-sT")
        if force_sT:
            flag = "-sT"

        args: List[str] = ["nmap", flag, "-p", ports, target]

        # verbosity & timing
        try:
            v = int(self.verbosity.currentText() or "0")
            if v > 0:
                args.insert(1, "-" + "v" * v)
        except Exception:
            pass
        t = self.timing.currentText()
        if t and t.isdigit():
            args.insert(1, f"-T{t}")

        # ipv6
        if self.ipv6_cb.isChecked():
            args.append("-6")

        if not strip_privileged:
            if self.service_version_cb.isChecked():
                args.insert(1, "-sV")
            if self.os_detect_cb.isChecked():
                args.insert(1, "-O")

        if skip_host_discovery:
            args.insert(1, "-Pn")

        return args

    def start_qprocess(self, program: str, args: List[str]):
        """
        Start a QProcess and hook up streaming handlers.
        """
        if self.process:
            try:
                self.process.kill()
            except Exception:
                pass
            self.process = None

        self.process = QProcess(self)
        self.process.setProcessChannelMode(QProcess.ProcessChannelMode.SeparateChannels)
        self.process.readyReadStandardOutput.connect(self.on_stdout)
        self.process.readyReadStandardError.connect(self.on_stderr)
        self.process.finished.connect(self.on_finished)
        self.process.start(program, args)
        started = self.process.waitForStarted(5000)
        return started

    # ---------- Start scan logic ----------
    def on_start_scan(self):
        if shutil.which("nmap") is None:
            QMessageBox.warning(self, "Missing dependency", "nmap is not installed.")
            return

        target = self.target_input.text().strip()
        if not target:
            QMessageBox.warning(self, "Input required", "Please enter a target IP or hostname.")
            return

        requested_idx = self.scan_type.currentIndex()
        requested_flag = {0: "-sT", 1: "-sS", 2: "-sU"}.get(requested_idx, "-sT")
        privileged_needed = requested_flag in ("-sS", "-sU") or self.os_detect_cb.isChecked()
        privileged_available = has_raw_privileges()

        if privileged_needed and not privileged_available:
            # Prompt to use pkexec or fallback to -sT
            if shutil.which("pkexec"):
                resp = QMessageBox.information(
                    self,
                    "Privileges required",
                    "Selected options require raw socket privileges.\n"
                    "Run with administrative privileges now (pkexec)?\n\n"
                    "Yes = run as root via pkexec\nNo = run a safer TCP Connect scan (-sT)",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                )
                if resp == QMessageBox.StandardButton.Yes:
                    args = self._build_args(force_sT=False, strip_privileged=False)
                    if args is None:
                        QMessageBox.warning(self, "Invalid input", "Please enter a valid target.")
                        return
                    self.output.clear()
                    self.append(f"Running as root via pkexec: {' '.join(args)}\n\n")
                    started = self.start_qprocess("pkexec", args)
                    if not started:
                        self.append("pkexec did not start (maybe cancelled). No scan started.\n")
                        self.process = None
                        return
                    self.start_btn.setEnabled(False)
                    self.stop_btn.setEnabled(True)
                    self.pkexec_btn.setEnabled(False)
                    return
            else:
                resp = QMessageBox.information(
                    self,
                    "Privileges required",
                    "Selected options require raw sockets but pkexec is not available.\nRun TCP Connect (-sT) instead?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                )
                if resp != QMessageBox.StandardButton.Yes:
                    return
            force_sT = True
        else:
            force_sT = False

        args = self._build_args(force_sT=force_sT, strip_privileged=False)
        if args is None:
            QMessageBox.warning(self, "Invalid input", "Please enter a valid target.")
            return

        # Start unprivileged nmap
        self.output.clear()
        self.append(f"Running: {' '.join(args)}\n\n")
        started = self.start_qprocess(args[0], args[1:])
        if not started:
            self.append("Failed to start nmap (unprivileged). Try 'Run as root' or check installation.\n")
            self.process = None
            return
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.pkexec_btn.setEnabled(False)

    def on_start_pkexec_scan(self):
        if shutil.which("nmap") is None:
            QMessageBox.warning(self, "Missing dependency", "nmap is not installed.")
            return
        if shutil.which("pkexec") is None:
            QMessageBox.warning(self, "Missing dependency", "pkexec is not available.")
            return

        args = self._build_args(force_sT=False, strip_privileged=False)
        if args is None:
            QMessageBox.warning(self, "Invalid input", "Please enter a valid target.")
            return

        resp = QMessageBox.information(
            self,
            "Run as root",
            "This will prompt for an administrative password (polkit). Proceed?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if resp != QMessageBox.StandardButton.Yes:
            return

        self.output.clear()
        self.append(f"Running as root via pkexec: {' '.join(args)}\n\n")
        self.append("Please authorize in the system authentication dialog.\n\n")
        started = self.start_qprocess("pkexec", args)
        if not started:
            self.append("pkexec did not start (maybe cancelled).\n")
            self.process = None
            return
        self.start_btn.setEnabled(False)
        self.pkexec_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)

    # ---------- QProcess handlers ----------
    def on_stdout(self):
        if not self.process:
            return
        raw = bytes(self.process.readAllStandardOutput()).decode("utf-8", errors="replace")
        if raw:
            self.append(raw)
            self.export_btn.setEnabled(True)

    def on_stderr(self):
        if not self.process:
            return
        raw = bytes(self.process.readAllStandardError()).decode("utf-8", errors="replace")
        if raw:
            self.append(raw)
            self.export_btn.setEnabled(True)

        # Only attempt auto-fallback for unprivileged runs (pkexec runs as root)
        if ("dnet: Failed to open device" in raw or "Failed to open device" in raw or "libdnet" in raw) \
                and not self._has_retried and self.allow_auto_fallback and self.fallback_cb.isChecked():
            self._has_retried = True
            self.append("\nDetected raw-socket failure. Retrying with TCP Connect (-sT) without privileged flags...\n")
            try:
                self.process.kill()
            except Exception:
                pass
            self.process = None

            args = self._build_args(force_sT=True, strip_privileged=True)
            if args is None:
                self.append("Failed to rebuild fallback args.\n")
                return
            self.append(f"Running: {' '.join(args)}\n\n")
            started = self.start_qprocess(args[0], args[1:])
            if not started:
                self.append("Failed to start fallback nmap command.\n")
                self.process = None
                self.start_btn.setEnabled(True)
                self.pkexec_btn.setEnabled(True)
                self.stop_btn.setEnabled(False)

    def on_finished(self):
        self.append("\nScan finished.\n")
        self.start_btn.setEnabled(True)
        if shutil.which("pkexec"):
            self.pkexec_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.process = None
        self.export_btn.setEnabled(True)
        # Auto-save result
        try:
            self.auto_export_results()
        except Exception:
            pass

    def on_stop_scan(self):
        if self.process and self.process.state() != QProcess.ProcessState.NotRunning:
            try:
                self.process.kill()
            except Exception:
                pass
            self.append("\nScan aborted by user.\n")
            self.start_btn.setEnabled(True)
            if shutil.which("pkexec"):
                self.pkexec_btn.setEnabled(True)
            self.stop_btn.setEnabled(False)
            self.process = None

    # ---------- Export results ----------
    def on_export_results(self):
        content = self.output.toPlainText().strip()
        if not content:
            QMessageBox.information(self, "No output", "No scan output to export.")
            return

        results_dir = os.path.join(os.path.dirname(__file__), "nmap_results")
        os.makedirs(results_dir, exist_ok=True)
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"nmap_{timestamp}.txt"
        filepath = os.path.join(results_dir, filename)
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(content)
            QMessageBox.information(self, "Exported", f"Results saved to:\n{filepath}")
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to save results: {e}")

    def auto_export_results(self):
        """Auto-save results at the end of a scan (called from on_finished)."""
        content = self.output.toPlainText().strip()
        if not content:
            return
        results_dir = os.path.join(os.path.dirname(__file__), "nmap_results")
        os.makedirs(results_dir, exist_ok=True)
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"nmap_{timestamp}.txt"
        filepath = os.path.join(results_dir, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)

    # ---------- hooks for the launcher ----------
    def on_start(self):
        """Optional hook called by launcher when the plugin is shown."""
        # Focus first field for convenience
        try:
            self.target_input.setFocus()
        except Exception:
            pass

    def on_close(self):
        """Called by launcher when plugin closes — ensure process is killed."""
        try:
            if self.process and self.process.state() != QProcess.ProcessState.NotRunning:
                self.process.kill()
        except Exception:
            pass

    def _on_back(self):
        """Close plugin (will call on_close then close)."""
        try:
            self.on_close()
        except Exception:
            pass
        try:
            self.close()
        except Exception:
            pass
