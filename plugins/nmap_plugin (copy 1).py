# plugins/nmap_plugin.py
import os
import re
import shutil
import subprocess
from typing import Optional

from PyQt6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QTextEdit, QWidget,
    QMessageBox, QComboBox, QCheckBox, QScrollBar
)
from PyQt6.QtCore import Qt, QProcess
from plugins.plugin_base import PluginBase

IP_RE = re.compile(r"^([0-9]{1,3}\.){3}[0-9]{1,3}$")


def has_raw_privileges() -> bool:
    """
    Return True if the current process can do raw socket operations:
    - running as root (euid 0), OR
    - nmap binary has cap_net_raw/cap_net_admin (detected via getcap, if available)
    """
    if os.geteuid() == 0:
        return True
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


class NmapPlugin(PluginBase):
    name = "Nmap Scanner (Touch)"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.process: Optional[QProcess] = None
        self._has_retried = False  # guard to avoid infinite retry loops
        self.allow_auto_fallback = True  # if True, auto-fallback to -sT on dnet error

        layout = QVBoxLayout()
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)

        header = QLabel("Nmap Port Scanner")
        header.setStyleSheet("font-size: 26px; font-weight: bold;")
        layout.addWidget(header, alignment=Qt.AlignmentFlag.AlignCenter)

        # Target + ports row
        trow = QHBoxLayout()
        self.target_input = QLineEdit()
        self.target_input.setPlaceholderText("IP or hostname (e.g. 192.168.1.10)")
        self.target_input.setFixedHeight(60)
        self.target_input.setStyleSheet("font-size: 20px;")
        trow.addWidget(self.target_input)

        self.port_input = QLineEdit()
        self.port_input.setPlaceholderText("Ports (e.g. 22 or 1-1024)")
        self.port_input.setFixedWidth(240)
        self.port_input.setFixedHeight(60)
        self.port_input.setStyleSheet("font-size: 20px;")
        trow.addWidget(self.port_input)

        layout.addLayout(trow)

        # Options row: scan type, verbosity, timing
        opts_row = QHBoxLayout()
        opts_row.setSpacing(12)

        self.scan_type = QComboBox()
        self.scan_type.addItems([
            "TCP Connect (-sT) — safe (no root)",
            "SYN Scan (-sS) — needs raw sockets",
            "UDP Scan (-sU) — needs raw sockets"
        ])
        self.scan_type.setFixedHeight(56)
        opts_row.addWidget(self.scan_type)

        self.verbosity = QComboBox()
        self.verbosity.addItems(["0", "1", "2"])
        self.verbosity.setFixedHeight(56)
        opts_row.addWidget(QLabel("Verbosity:"))
        opts_row.addWidget(self.verbosity)

        self.timing = QComboBox()
        self.timing.addItems([str(i) for i in range(0, 6)])
        self.timing.setFixedHeight(56)
        opts_row.addWidget(QLabel("Timing:"))
        opts_row.addWidget(self.timing)

        layout.addLayout(opts_row)

        # Extra options row (checkboxes)
        extra_row = QHBoxLayout()
        self.os_detect_cb = QCheckBox("OS detect (-O)")
        self.os_detect_cb.setFixedHeight(44)
        extra_row.addWidget(self.os_detect_cb)

        self.service_version_cb = QCheckBox("Version (-sV)")
        self.service_version_cb.setFixedHeight(44)
        extra_row.addWidget(self.service_version_cb)

        self.ipv6_cb = QCheckBox("IPv6")
        self.ipv6_cb.setFixedHeight(44)
        extra_row.addWidget(self.ipv6_cb)

        layout.addLayout(extra_row)

        # Fallback toggle
        fallback_row = QHBoxLayout()
        self.fallback_cb = QCheckBox("Auto-fallback to TCP Connect (-sT) if raw sockets fail")
        self.fallback_cb.setChecked(True)
        self.fallback_cb.setFixedHeight(44)
        fallback_row.addWidget(self.fallback_cb)
        layout.addLayout(fallback_row)

        # Buttons
        brow = QHBoxLayout()
        self.scan_btn = QPushButton("Start Scan (unprivileged)")
        self.scan_btn.setFixedHeight(88)
        self.scan_btn.setStyleSheet("font-size: 22px; background-color: #2e8b57; color: white;")
        self.scan_btn.clicked.connect(self.on_start_scan)
        brow.addWidget(self.scan_btn)

        self.pkexec_btn = QPushButton("Run as root (pkexec)")
        self.pkexec_btn.setFixedHeight(88)
        self.pkexec_btn.setStyleSheet("font-size: 20px; background-color: #ff8c00; color: white;")
        self.pkexec_btn.clicked.connect(self.on_start_pkexec_scan)
        # Only show/enable if pkexec exists
        if shutil.which("pkexec") is None:
            self.pkexec_btn.setEnabled(False)
            self.pkexec_btn.setToolTip("pkexec not available on this system")
        brow.addWidget(self.pkexec_btn)

        self.stop_btn = QPushButton("Stop Scan")
        self.stop_btn.setFixedHeight(88)
        self.stop_btn.setStyleSheet("font-size: 22px; background-color: #b22222; color: white;")
        self.stop_btn.clicked.connect(self.on_stop_scan)
        self.stop_btn.setEnabled(False)
        brow.addWidget(self.stop_btn)

        layout.addLayout(brow)

        # Output area
        self.output = QTextEdit()
        self.output.setReadOnly(True)
        self.output.setStyleSheet("font-size: 16px;")
        layout.addWidget(self.output)

        # Back button
        back_row = QHBoxLayout()
        self.back_btn = QPushButton("Back")
        self.back_btn.setFixedHeight(72)
        self.back_btn.setStyleSheet("font-size: 20px;")
        self.back_btn.clicked.connect(self.on_back)
        back_row.addWidget(self.back_btn)
        layout.addLayout(back_row)

        self.setLayout(layout)

        # On init, enable/disable privileged options based on environment
        self._configure_privileged_options()

    def _configure_privileged_options(self):
        """Disable SYN/UDP options unless raw privileges available."""
        privileged_available = has_raw_privileges()
        if not privileged_available:
            # Inform user in output
            self.append("Note: raw-socket scans (SYN/UDP, OS detection) are disabled/unavailable in this environment.\n")
            self.append("You can run as root via the 'Run as root (pkexec)' button or grant capabilities to /usr/bin/nmap.\n\n")

    def _scroll_to_bottom(self):
        sb: QScrollBar = self.output.verticalScrollBar()
        sb.setValue(sb.maximum())

    def append(self, text: str):
        """Insert text at the end and scroll to bottom."""
        self.output.insertPlainText(text)
        self._scroll_to_bottom()

    def _build_args(self, force_sT: bool = False, strip_privileged: bool = False, skip_host_discovery: bool = False):
        """Return the nmap argument list based on UI selections.
           force_sT: override scan type to -sT
           strip_privileged: remove options requiring raw sockets (like -O)
           skip_host_discovery: add -Pn
        """
        target = self.target_input.text().strip()
        ports = self.port_input.text().strip() or "1-1024"
        if not target:
            return None

        mapping = {0: "-sT", 1: "-sS", 2: "-sU"}
        idx = self.scan_type.currentIndex()
        flag = mapping.get(idx, "-sT")
        if force_sT:
            flag = "-sT"

        args = ["nmap", flag, "-p", ports, target]

        # Verbosity & timing are safe to include
        v = int(self.verbosity.currentText() or "0")
        if v > 0:
            args.insert(1, "-" + "v" * v)
        t = self.timing.currentText()
        if t and t.isdigit():
            args.insert(1, f"-T{t}")

        # Add ipv6 if requested
        if self.ipv6_cb.isChecked():
            args.append("-6")

        # Extra flags only if not stripping privileged options
        if not strip_privileged:
            if self.service_version_cb.isChecked():
                args.insert(1, "-sV")
            if self.os_detect_cb.isChecked():
                args.insert(1, "-O")

        if skip_host_discovery:
            args.insert(1, "-Pn")

        return args

    def on_start_scan(self):
        """Start an unprivileged scan (QProcess running nmap as current user)."""
        target = self.target_input.text().strip()
        if not target:
            QMessageBox.warning(self, "Input required", "Please enter a target IP or hostname.")
            return

        # Check nmap present
        if shutil.which("nmap") is None:
            QMessageBox.warning(self, "Missing dependency", "nmap is not installed on this system.")
            return

        # Build args, possibly warning about privileged options
        requested_idx = self.scan_type.currentIndex()
        requested_flag = {0: "-sT", 1: "-sS", 2: "-sU"}.get(requested_idx, "-sT")
        privileged_needed = requested_flag in ("-sS", "-sU")
        privileged_available = has_raw_privileges()

        if privileged_needed and not privileged_available:
            resp = QMessageBox.information(
                self,
                "Privileges required",
                "Selected scan type requires raw socket privileges (root or file capabilities).\n"
                "Proceed with TCP Connect (-sT) instead?",
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

        # Reset retry guard
        self._has_retried = False
        self.allow_auto_fallback = self.fallback_cb.isChecked()

        # Clear output and show command
        self.output.clear()
        self.append(f"Running: {' '.join(args)}\n\n")

        # Start QProcess
        self.process = QProcess(self)
        self.process.setProcessChannelMode(QProcess.ProcessChannelMode.SeparateChannels)
        self.process.readyReadStandardOutput.connect(self.on_stdout)
        self.process.readyReadStandardError.connect(self.on_stderr)
        self.process.finished.connect(self.on_finished)
        self.process.start(args[0], args[1:])
        started = self.process.waitForStarted(3000)
        if not started:
            self.append("Failed to start nmap. Check it is installed and executable.\n")
            self.process = None
            return

        self.scan_btn.setEnabled(False)
        self.pkexec_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)

    def on_start_pkexec_scan(self):
        """Run the chosen nmap command under pkexec (prompts for auth)."""
        target = self.target_input.text().strip()
        if not target:
            QMessageBox.warning(self, "Input required", "Please enter a target IP or hostname.")
            return

        if shutil.which("nmap") is None:
            QMessageBox.warning(self, "Missing dependency", "nmap is not installed on this system.")
            return

        if shutil.which("pkexec") is None:
            QMessageBox.warning(self, "Missing dependency", "pkexec is not available on this system.")
            return

        # Build args for pkexec (we'll run: pkexec nmap <args...>)
        args = self._build_args(force_sT=False, strip_privileged=False)
        if args is None:
            QMessageBox.warning(self, "Invalid input", "Please enter a valid target.")
            return

        # Confirm user knows an authentication dialog will appear
        resp = QMessageBox.information(
            self,
            "Run as root",
            "This will ask for administrative privileges using the system authentication dialog.\n"
            "Proceed?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if resp != QMessageBox.StandardButton.Yes:
            return

        # Clear output and show command (inform user pkexec will be used)
        self.output.clear()
        self.append(f"Running as root via pkexec: {' '.join(args)}\n\n")
        self.append("A system authentication dialog will appear. Please authorize to continue.\n\n")

        # Start pkexec nmap ...
        self.process = QProcess(self)
        self.process.setProcessChannelMode(QProcess.ProcessChannelMode.SeparateChannels)
        self.process.readyReadStandardOutput.connect(self.on_stdout)
        self.process.readyReadStandardError.connect(self.on_stderr)
        self.process.finished.connect(self.on_finished)

        # Start pkexec with nmap and its args: program = "pkexec", arguments = args (starting with "nmap")
        self.process.start("pkexec", args)
        started = self.process.waitForStarted(5000)  # pkexec may take a moment (auth)
        if not started:
            self.append("pkexec process did not start or was cancelled. No scan started.\n")
            self.process = None
            return

        self.scan_btn.setEnabled(False)
        self.pkexec_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)

    def on_stdout(self):
        if not self.process:
            return
        raw = bytes(self.process.readAllStandardOutput()).decode("utf-8", errors="replace")
        if raw:
            self.append(raw)

    def on_stderr(self):
        if not self.process:
            return
        raw = bytes(self.process.readAllStandardError()).decode("utf-8", errors="replace")
        if raw:
            self.append(raw)

        # Detect libdnet failure and fallback (only for unprivileged runs)
        if ("dnet: Failed to open device" in raw or "Failed to open device" in raw or "libdnet" in raw) and not self._has_retried and self.allow_auto_fallback:
            # retry once with -sT and strip privileged flags
            self._has_retried = True
            self.append("\nDetected inability to open raw sockets. Retrying with TCP Connect (-sT) without privileged flags...\n")
            try:
                self.process.kill()
            except Exception:
                pass
            self.process = None

            args = self._build_args(force_sT=True, strip_privileged=True)
            if args is None:
                self.append("Failed to rebuild nmap args for fallback.\n")
                return

            self.append(f"Running: {' '.join(args)}\n\n")
            self.process = QProcess(self)
            self.process.setProcessChannelMode(QProcess.ProcessChannelMode.SeparateChannels)
            self.process.readyReadStandardOutput.connect(self.on_stdout)
            self.process.readyReadStandardError.connect(self.on_stderr)
            self.process.finished.connect(self.on_finished)
            self.process.start(args[0], args[1:])
            started = self.process.waitForStarted(3000)
            if not started:
                self.append("Failed to start fallback nmap command.\n")
                self.process = None
                self.scan_btn.setEnabled(True)
                self.pkexec_btn.setEnabled(True)
                self.stop_btn.setEnabled(False)

    def on_finished(self):
        self.append("\nScan finished.\n")
        self.scan_btn.setEnabled(True)
        if shutil.which("pkexec") is not None:
            self.pkexec_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.process = None

    def on_stop_scan(self):
        if self.process and self.process.state() != QProcess.ProcessState.NotRunning:
            try:
                self.process.kill()
            except Exception:
                pass
            self.append("\nScan aborted by user.\n")
            self.scan_btn.setEnabled(True)
            if shutil.which("pkexec") is not None:
                self.pkexec_btn.setEnabled(True)
            self.stop_btn.setEnabled(False)
            self.process = None

    def on_back(self):
        # Signal the parent/launcher to close plugin view if possible
        if hasattr(self.parent(), "show_launcher"):
            try:
                self.parent().show_launcher()
            except Exception:
                pass
        else:
            # fallback: close this window if it's top-level
            try:
                self.close()
            except Exception:
                pass
