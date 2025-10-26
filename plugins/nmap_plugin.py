import os
import subprocess
import tempfile
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QLineEdit, QPushButton, QTextEdit, QFileDialog, QMessageBox
)


class NmapWorker(QThread):
    output_signal = pyqtSignal(str)
    finished_signal = pyqtSignal(bool)

    def __init__(self, target, use_sudo=False):
        super().__init__()
        self.target = target
        self.use_sudo = use_sudo
        self._process = None
        self._running = True

    def run(self):
        cmd = ["nmap", "-A", self.target]
        if self.use_sudo:
            cmd.insert(0, "pkexec")

        try:
            self._process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True,
                bufsize=1
            )
            for line in self._process.stdout:
                if not self._running:
                    break
                self.output_signal.emit(line)
            self._process.wait()
            self.finished_signal.emit(True)
        except Exception as e:
            self.output_signal.emit(f"[!] Error running nmap: {e}\n")
            self.finished_signal.emit(False)

    def stop(self):
        self._running = False
        if self._process:
            self._process.terminate()


class NmapPlugin(QWidget):
    def __init__(self, parent=None, app_launcher=None):
        super().__init__(parent)
        self.app_launcher = app_launcher
        self.worker = None
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)

        title = QLabel("🕵️‍♂️ Nmap Scanner", self)
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-size: 20px; font-weight: bold; color: #00ffcc;")

        self.target_input = QLineEdit(self)
        self.target_input.setPlaceholderText("Enter target (e.g. 192.168.1.1 or scanme.nmap.org)")

        self.output_area = QTextEdit(self)
        self.output_area.setReadOnly(True)
        self.output_area.setStyleSheet("background-color: #000; color: #0f0; font-family: monospace;")

        self.start_button = QPushButton("▶ Start Scan")
        self.start_button.clicked.connect(self.start_scan)

        self.stop_button = QPushButton("⛔ Stop Scan")
        self.stop_button.setEnabled(False)
        self.stop_button.clicked.connect(self.stop_scan)

        self.export_button = QPushButton("💾 Export Results")
        self.export_button.setEnabled(False)
        self.export_button.clicked.connect(self.export_results)

        layout.addWidget(title)
        layout.addWidget(self.target_input)
        layout.addWidget(self.output_area)
        layout.addWidget(self.start_button)
        layout.addWidget(self.stop_button)
        layout.addWidget(self.export_button)

        self.setLayout(layout)

    def start_scan(self):
        target = self.target_input.text().strip()
        if not target:
            QMessageBox.warning(self, "Error", "Please enter a valid target.")
            return

        self.output_area.clear()
        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.export_button.setEnabled(False)

        # Detect if pkexec (sudo) is available
        use_sudo = os.geteuid() != 0 and shutil.which("pkexec")

        self.worker = NmapWorker(target, use_sudo=use_sudo)
        self.worker.output_signal.connect(self._update_output)
        self.worker.finished_signal.connect(self._scan_finished)
        self.worker.start()

    def stop_scan(self):
        if self.worker:
            self.worker.stop()
            self.output_area.append("\n[!] Scan stopped by user.")
            self._scan_finished(False)

    def _scan_finished(self, success):
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.export_button.setEnabled(True)
        self.worker = None
        if success:
            self.output_area.append("\n✅ Scan finished.")

    def _update_output(self, text):
        self.output_area.moveCursor(Qt.TextCursor.End)
        self.output_area.insertPlainText(text)
        self.output_area.moveCursor(Qt.TextCursor.End)

    def export_results(self):
        filename, _ = QFileDialog.getSaveFileName(self, "Export Nmap Results", "", "Text Files (*.txt)")
        if filename:
            try:
                with open(filename, "w") as f:
                    f.write(self.output_area.toPlainText())
                QMessageBox.information(self, "Export Complete", f"Results saved to:\n{filename}")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to save results:\n{e}")

